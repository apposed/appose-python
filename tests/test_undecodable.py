# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests that messages which cannot be decoded fail whatever awaits them,
rather than leaving it hanging, and do not break the connection.
"""

from __future__ import annotations

import time

import appose
from appose.service import TaskStatus
from tests.test_base import maybe_debug

# A reference to a shared memory block that does not exist, which no
# Appose implementation can decode.
BOGUS = {"appose_type": "shm", "name": "psm_bogus", "rsize": 8}


def finish(task, timeout: float = 10):
    """Runs the task, and waits for it to finish, without hanging forever."""
    task.start()
    deadline = time.monotonic() + timeout
    while not task.status.is_finished():
        assert time.monotonic() < deadline, "task never finished"
        time.sleep(0.02)
    return task


def assert_alive(service):
    assert finish(service.task("6 * 7")).result() == 42


def test_undecodable_task_request():
    """The worker fails a task whose request it cannot decode."""
    with appose.system().python() as service:
        maybe_debug(service)
        task = finish(service.task("x", {"x": BOGUS}))
        assert task.status == TaskStatus.FAILED
        assert "Worker could not decode the task request" in task.error
        assert "psm_bogus" in task.error
        assert_alive(service)


def test_undecodable_reply():
    """The worker fails a call into a service object whose reply it cannot decode."""

    class Source:
        def get(self):
            return BOGUS

    with appose.system().python() as service:
        maybe_debug(service)
        task = finish(service.task("source.get()", {"source": Source()}))
        assert task.status == TaskStatus.FAILED
        assert "Worker could not decode the service's reply" in task.error
        assert_alive(service)


def test_undecodable_completion():
    """The service fails a task whose completion it cannot decode."""
    with appose.system().python() as service:
        maybe_debug(service)
        task = finish(service.task(f"task.outputs['x'] = {BOGUS!r}"))
        assert task.status == TaskStatus.FAILED
        assert "Service could not decode the task's COMPLETION response" in task.error
        assert_alive(service)


def test_undecodable_call():
    """The service fails a call from the worker which it cannot decode."""

    class Sink:
        def take(self, value):
            return value

    with appose.system().python() as service:
        maybe_debug(service)
        task = finish(service.task(f"sink.take({BOGUS!r})", {"sink": Sink()}))
        assert task.status == TaskStatus.FAILED
        assert "Service could not decode the call" in task.error
        assert_alive(service)
