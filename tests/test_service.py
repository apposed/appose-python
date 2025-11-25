# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


import appose
from appose.service import TaskStatus
from tests.test_base import execute_and_assert, maybe_debug
from pathlib import Path

collatz_groovy = """
// Computes the stopping time of a given value
// according to the Collatz conjecture sequence.
time = 0
BigInteger v = 9999
while (v != 1) {
  v = v%2==0 ? v/2 : 3*v+1
  task.update("[${time}] -> ${v}", time, null)
  time++
}
return time
"""

collatz_python = """
# Computes the stopping time of a given value
# according to the Collatz conjecture sequence.
time = 0
v = 9999
while v != 1:
    v = v//2 if v%2==0 else 3*v+1
    task.update(f"[{time}] -> {v}", current=time)
    time += 1
task.outputs["result"] = time
"""

calc_sqrt_python = """
from math import sqrt
def sqrt_age(age):
    return sqrt(age)
task.export(sqrt_age=sqrt_age)
task.outputs["result"] = sqrt_age(age)
"""

main_thread_check_groovy = """
task.outputs["thread"] = Thread.currentThread().getName()
"""

main_thread_check_python = """
import threading
task.outputs["thread"] = threading.current_thread().name
"""


def test_groovy():
    env = appose.system()
    # NB: For now, use bin/test.sh to copy the needed JARs.
    class_path = ["target/dependency/*"]
    with env.groovy(class_path=class_path) as service:
        maybe_debug(service)
        execute_and_assert(service, collatz_groovy)


def test_python():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        execute_and_assert(service, collatz_python)


def test_service_startup_failure():
    env = appose.custom().base(Path("target") / "no-java-to-be-found-here").build()
    try:
        with env.groovy():
            raise AssertionError("Groovy worker process started successfully!?")
    except ValueError as e:
        assert (
            "No executables found amongst candidates: "
            "['java', 'java.exe', 'bin/java', 'bin/java.exe', "
            "'jre/bin/java', 'jre/bin/java.exe']"
        ) == str(e)


def test_scope_python():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        task = service.task(calc_sqrt_python, {"age": 100})
        task.wait_for()
        assert TaskStatus.COMPLETE == task.status
        result = round(task.outputs.get("result"))
        assert result == 10

        task = service.task("task.outputs['result'] = sqrt_age(age)", {"age": 81})
        task.wait_for()
        assert TaskStatus.COMPLETE == task.status
        result = round(task.outputs.get("result"))
        assert result == 9


def test_main_thread_queue_groovy():
    env = appose.system()
    # NB: For now, use bin/test.sh to copy the needed JARs.
    class_path = ["target/dependency/*"]
    with env.groovy(class_path=class_path) as service:
        maybe_debug(service)

        task = service.task(main_thread_check_groovy, queue="main")
        task.wait_for()
        assert TaskStatus.COMPLETE == task.status
        thread = task.outputs.get("thread")
        assert thread == "main"

        task = service.task(main_thread_check_groovy)
        task.wait_for()
        assert TaskStatus.COMPLETE == task.status
        thread = task.outputs.get("thread")
        assert thread != "main"


def test_main_thread_queue_python():
    env = appose.system()
    with env.python() as service:
        task = service.task(main_thread_check_python, queue="main")
        task.wait_for()
        assert TaskStatus.COMPLETE == task.status
        thread = task.outputs.get("thread")
        assert thread == "MainThread"

        task = service.task(main_thread_check_python)
        task.wait_for()
        assert TaskStatus.COMPLETE == task.status
        thread = task.outputs.get("thread")
        assert thread != "MainThread"


def test_init():
    """Tests that init script is executed before tasks run."""
    env = appose.system()
    with env.python().init("init_value = 'initialized'") as service:
        maybe_debug(service)

        # Verify that the init script was executed and the variable is accessible.
        task = service.task("init_value").wait_for()
        assert TaskStatus.COMPLETE == task.status

        result = task.result()
        assert result == "initialized", "Init script should set init_value variable"


def test_init_numpy():
    """Tests that NumPy works on every platform, even Windows."""
    env = (
        appose.pixi()
        .base("target/envs/test-init-numpy")
        .conda("numpy=2.3.4")
        .pypi("appose==0.7.2")
        .log_debug()
        .build()
    )
    with env.python().init("import numpy") as service:
        maybe_debug(service)

        task = service.task(
            "import numpy\n"
            "narr = numpy.random.default_rng(seed=1337).random([3, 5])\n"
            "[float(v) for v in narr.flatten()]"
        ).wait_for()
        assert TaskStatus.COMPLETE == task.status

        result = task.outputs.get("result")
        assert isinstance(result, list)
        expected = [
            0.8781019003,
            0.1855279616,
            0.9209004548,
            0.9465658637,
            0.8745080903,
            0.1157427629,
            0.1937316623,
            0.3417371975,
            0.4957909002,
            0.8983712328,
            0.0064586191,
            0.2274114670,
            0.7936549524,
            0.4142867178,
            0.0838144031,
        ]
        for i, expected_val in enumerate(expected):
            actual_val = result[i]
            assert isinstance(actual_val, (int, float))
            assert abs(actual_val - expected_val) < 1e-10
