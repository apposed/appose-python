# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for worker-side proxies of service objects (worker -> service calls)."""

from __future__ import annotations

import numpy
import pytest

import appose
from appose import TaskException
from appose.shm import NDArray
from tests.test_base import assert_complete, maybe_debug


class Counter:
    def __init__(self):
        self.count = 0
        self.label = "clicks"

    def increment(self, amount=1):
        self.count += amount
        return self.count

    def fail(self):
        raise ValueError("Counter malfunction")


class Weather:
    def forecast(self):
        return Forecast("sunny", 23)


class Forecast:
    def __init__(self, sky, temp):
        self.sky = sky
        self.temp = temp


def test_service_proxy():
    """Test attribute access and method calls on a service object."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        counter = Counter()

        task = service.task(
            """
counter.increment()
counter.increment(5)
task.outputs["label"] = counter.label
task.outputs["count"] = counter.count
""",
            {"counter": counter},
        ).wait_for()
        assert_complete(task)

        assert task.outputs["label"] == "clicks"
        assert task.outputs["count"] == 6
        # The calls mutated the actual service-side object.
        assert counter.count == 6


def test_service_proxy_dir():
    """Test that dir() works on service proxies."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        task = service.task("dir(counter)", {"counter": Counter()}).wait_for()
        names = task.result()
        assert "increment" in names
        assert "label" in names


def test_service_proxy_chaining():
    """Test that non-serializable results come back as further proxies."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        task = service.task(
            """
forecast = weather.forecast()
f"{forecast.sky}, {forecast.temp} degrees"
""",
            {"weather": Weather()},
        ).wait_for()
        assert task.result() == "sunny, 23 degrees"


def test_service_proxy_round_trip():
    """Test that a service proxy sent back to the service is the original object."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        counter = Counter()
        task = service.task("counter", {"counter": counter}).wait_for()
        assert task.result() is counter


def test_service_proxy_error():
    """Test that service-side exceptions propagate to the worker."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        task = service.task("counter.fail()", {"counter": Counter()})
        with pytest.raises(TaskException):
            task.wait_for()
        assert "Counter malfunction" in task.error


def test_service_proxy_reentrant():
    """Test a service object calling back into a worker object mid-call."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        class Doubler:
            def apply(self, worker_obj):
                # worker_obj is a (forward) proxy to an object in the worker,
                # which is blocked waiting for this very call to return.
                return worker_obj.value * 2

        task = service.task(
            """
class Box:
    def __init__(self, value):
        self.value = value

doubler.apply(Box(21))
""",
            {"doubler": Doubler()},
        ).wait_for()
        assert task.result() == 42


def test_service_proxy_shm():
    """Test a service object filling shared memory on behalf of the worker."""
    env = appose.system()
    with env.python().init("import numpy") as service:
        maybe_debug(service)

        class Source:
            def __init__(self):
                self.reads = 0

            def read(self, index, buffer):
                numpy.asarray(buffer)[:] = index
                self.reads += 1

        source = Source()
        with NDArray("int32", [4, 4]) as buffer:
            task = service.task(
                """
import numpy
total = 0
for i in range(10):
    source.read(i, buffer)
    total += int(numpy.asarray(buffer).sum())
total
""",
                {"source": source, "buffer": buffer},
            ).wait_for()
            assert task.result() == 16 * sum(range(10))
            assert source.reads == 10
