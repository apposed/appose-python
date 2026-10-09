# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for shutting down services: closing, killing, and exiting the program.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

import appose
from appose.service import TaskStatus

# Launches the worker as a child of an intermediate process, as `pixi run` does.
WRAPPED_WORKER = (
    "import subprocess, sys; sys.exit(subprocess.call([sys.executable, '-c', "
    "'import appose.python_worker; appose.python_worker.main()']))"
)

WORKER_PID = "import os\ntask.outputs['pid'] = os.getpid()"

SLEEP = "import time\ntime.sleep(60)"


def wrapped_service():
    return appose.system().python("-c", WRAPPED_WORKER)


def start_sleeping(service):
    task = service.task(SLEEP).start()
    while task.status != TaskStatus.RUNNING:
        time.sleep(0.01)
    return task


def assert_dead(pid: int) -> None:
    if os.name == "nt":
        return
    # Give the orphaned worker's new parent a moment to reap it.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"Worker process {pid} is still alive")


def test_kill_wrapped_worker():
    service = wrapped_service()
    pid = service.task(WORKER_PID).wait_for().outputs["pid"]
    # noinspection PyProtectedMember
    assert pid != service._process.pid

    task = start_sleeping(service)
    start = time.monotonic()
    service.kill()
    exit_code = service.wait_for(timeout=10)

    assert time.monotonic() - start < 10
    assert exit_code != 0
    assert service.returncode == exit_code
    assert task.status == TaskStatus.CRASHED
    assert_dead(pid)


def test_close_with_timeout_graceful():
    service = appose.system().python()
    service.task("1 + 1").wait_for()

    assert service.close(timeout=10) == 0
    assert service.returncode == 0
    assert not service.is_alive()


def test_close_with_timeout_kills_busy_worker():
    service = wrapped_service()
    pid = service.task(WORKER_PID).wait_for().outputs["pid"]
    task = start_sleeping(service)

    start = time.monotonic()
    exit_code = service.close(timeout=0.5)

    assert time.monotonic() - start < 10
    assert exit_code != 0
    assert task.status == TaskStatus.CRASHED
    assert_dead(pid)


def test_close_without_timeout_returns_at_once():
    service = appose.system().python()
    task = start_sleeping(service)

    assert service.close() is None
    assert service.is_alive()
    assert task.status == TaskStatus.RUNNING

    service.kill()
    service.wait_for(timeout=10)


def test_close_lets_started_tasks_finish():
    """Tasks started before closing can still call into service objects."""

    class Source:
        def get(self):
            return 42

    service = appose.system().python()
    task = service.task(
        "import time\ntime.sleep(0.5)\nsource.get()", {"source": Source()}
    ).start()
    service.close()
    with pytest.raises(RuntimeError, match="closing"):
        service.task("1 + 1").start()
    assert task.wait_for().result() == 42
    assert service.wait_for(timeout=10) == 0


def test_wait_for_timeout():
    service = appose.system().python()
    start_sleeping(service)

    with pytest.raises(subprocess.TimeoutExpired):
        service.wait_for(timeout=0.1)

    service.kill()
    assert service.wait_for(timeout=10) != 0


def test_not_started():
    service = appose.system().python()

    assert service.returncode is None
    assert not service.is_alive()
    with pytest.raises(RuntimeError):
        service.close()
    with pytest.raises(RuntimeError):
        service.kill()
    with pytest.raises(RuntimeError):
        service.wait_for()


def run_program(script: str) -> subprocess.CompletedProcess:
    """
    Run the given script as a program of its own, which must exit by itself.
    """
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_atexit_cleanup_runs():
    """
    A program that leaves a busy service running, relying on an atexit hook
    to clean it up, must still exit: see apposed/appose#37.
    """
    result = run_program(f"""
        import atexit
        import appose

        service = appose.system().python("-c", {WRAPPED_WORKER!r})
        print(service.task({WORKER_PID!r}).wait_for().outputs["pid"])
        service.task({SLEEP!r}).start()

        def cleanup():
            print("cleanup ran")
            print(service.close(timeout=0))

        atexit.register(cleanup)
        """)

    assert result.returncode == 0, result.stderr
    pid, cleanup, exit_code = result.stdout.splitlines()
    assert cleanup == "cleanup ran"
    assert exit_code != "0"
    assert_dead(int(pid))


def test_exit_shuts_down_services():
    """
    A program that leaves a busy service running must exit,
    killing the worker once its exit timeout elapses.
    """
    result = run_program(f"""
        import appose

        service = appose.system().python("-c", {WRAPPED_WORKER!r})
        service.exit_timeout = 0.5
        print(service.task({WORKER_PID!r}).wait_for().outputs["pid"])
        service.task({SLEEP!r}).start()
        """)

    assert result.returncode == 0, result.stderr
    assert_dead(int(result.stdout))
