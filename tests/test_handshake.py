# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


"""Tests for the HELLO handshake, and for worker robustness to bad requests."""

from __future__ import annotations

import sys
import time
from textwrap import dedent

import pytest

import appose
from appose import TaskException
from appose._version import __version__
from appose.service import Service, TaskStatus
from tests.test_base import maybe_debug

# A fake worker, which completes every task immediately with result 42.
# It sends the given HELLO message first, if any.
FAKE_WORKER = dedent(
    """
    import json, sys
    hello = {hello!r}
    if hello is not None:
        print(json.dumps(hello), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("requestType") != "EXECUTE":
            continue
        uuid = request["task"]
        print(json.dumps({{"task": uuid, "responseType": "LAUNCH"}}), flush=True)
        print(json.dumps({{"task": uuid, "responseType": "COMPLETION",
            "outputs": {{"result": 42}}}}), flush=True)
    """
)


def fake_worker(hello: dict | None) -> Service:
    script = FAKE_WORKER.format(hello=hello)
    return Service(".", None, sys.executable, "-c", script)


def test_hello():
    with appose.system().python() as service:
        maybe_debug(service)
        service.task("1").wait_for()
        info = service.worker_info()
        assert info is not None
        assert info["implementation"] == "appose-python"
        assert info["version"] == __version__


def test_compatible_fake_worker():
    hello = {"responseType": "HELLO", "implementation": "fake", "version": __version__}
    with fake_worker(hello) as service:
        maybe_debug(service)
        assert service.task("x").wait_for().result() == 42


def test_incompatible_worker():
    hello = {"responseType": "HELLO", "implementation": "fake", "version": "0.0.1"}
    with fake_worker(hello) as service:
        maybe_debug(service)
        with pytest.raises(TaskException) as e:
            service.task("x").wait_for()
        assert "fake 0.0.1 is incompatible" in e.value.task.error
        # Subsequent tasks fail fast, with the same reason.
        with pytest.raises(TaskException) as e:
            service.task("y").wait_for()
        assert "fake 0.0.1 is incompatible" in e.value.task.error


def test_worker_without_hello():
    with fake_worker(None) as service:
        maybe_debug(service)
        with pytest.raises(TaskException) as e:
            service.task("x").wait_for()
        assert "Worker did not identify itself" in e.value.task.error


def test_skip_version_check(monkeypatch):
    monkeypatch.setenv("APPOSE_SKIP_VERSION_CHECK", "1")
    with fake_worker(None) as service:
        maybe_debug(service)
        assert service.task("x").wait_for().result() == 42


def test_bad_request():
    """Tests that a bad request fails its task, and the worker carries on."""
    with appose.system().python() as service:
        maybe_debug(service)
        service.start()

        # A request of unknown type, for a new task: the task fails.
        task = service.task("1")
        task.status = TaskStatus.QUEUED
        service._send({"task": task.uuid, "requestType": "BOGUS"})
        deadline = time.monotonic() + 10
        while task.status == TaskStatus.QUEUED and time.monotonic() < deadline:
            time.sleep(0.01)
        assert task.status == TaskStatus.FAILED
        assert "BOGUS" in task.error

        # A request that is not even JSON: reported on stderr only.
        service._process.stdin.write("this is not JSON\n")
        service._process.stdin.flush()

        # Either way, the worker is still alive and well.
        assert service.task("6 * 7").wait_for().result() == 42
        deadline = time.monotonic() + 10
        while not any("Invalid request" in line for line in service.error_lines()):
            assert time.monotonic() < deadline
            time.sleep(0.01)
