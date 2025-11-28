# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


import appose
from appose.service import ResponseType, TaskException, TaskStatus
from tests.test_base import execute_and_assert, maybe_debug
from pathlib import Path
import time
import os
import re

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


def test_task_failure_python():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        script = "whee\n"
        try:
            service.task(script).wait_for()
            raise AssertionError("Expected TaskException for failed script")
        except TaskException as e:
            expected_error = "NameError: name 'whee' is not defined"
            assert expected_error in str(e)


def test_startup_crash():
    env = appose.system()
    python_exes = ["python", "python3", "python.exe"]
    service = env.service(python_exes, "-c", "import nonexistentpackage").start()
    # Wait up to 500ms for the crash.
    for i in range(100):
        if not service.is_alive():
            break
        time.sleep(0.005)
    assert not service.is_alive()
    # Check that the crash happened and was recorded correctly.
    error_lines = service.error_lines()
    assert error_lines is not None
    assert len(error_lines) > 0
    error = error_lines[-1]
    assert error == "ModuleNotFoundError: No module named 'nonexistentpackage'"


def test_python_sys_exit():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Launch a task that calls sys.exit. This is a nasty thing to do
        # because Python does not exit the worker process when sys.exit is
        # called within a dedicated threading.Thread; the thread just dies.
        # So in addition to testing the Python code here, we are also testing
        # that Appose's python_worker handles this situation well.
        try:
            service.task("import sys\nsys.exit(123)").wait_for()
            raise AssertionError("Expected TaskException for sys.exit")
        except TaskException as e:
            # The failure should be either "thread death" or a "SystemExit" message.
            assert "thread death" in str(e) or "SystemExit: 123" in str(e)


def test_crash_with_active_task():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        # Create a "long-running" task.
        script = (
            "import sys\n"
            "sys.stderr.write('one\\n')\n"
            "sys.stderr.flush()\n"
            "print('two')\n"
            "sys.stdout.flush()\n"
            "sys.stderr.write('three\\n')\n"
            "sys.stderr.flush()\n"
            "task.update('halfway')\n"
            "print('four')\n"
            "sys.stdout.flush()\n"
            "sys.stderr.write('five\\n')\n"
            "sys.stderr.flush()\n"
            "print('six')\n"
            "sys.stdout.flush()\n"
            "sys.stderr.write('seven\\n')\n"
            "task.update('crash-me')\n"
            "import time; time.sleep(999)\n"
        )
        ready = [False]

        def on_crash_me(event):
            if event.message == "crash-me":
                ready[0] = True

        task = service.task(script)
        task.listen(on_crash_me)

        # Record any crash reported in the task notifications.
        reported_error = [None]

        def on_crash(event):
            if event.response_type == ResponseType.CRASH:
                reported_error[0] = task.error

        task.listen(on_crash)

        # Launch the task.
        task.start()

        # Simulate a crash after the script has emitted its output.
        while not ready[0]:
            time.sleep(0.005)
        service.kill()

        # Wait for the service to fully shut down after the crash.
        exit_code = service.wait_for()
        assert exit_code != 0

        # Is the task flagged as crashed?
        assert TaskStatus.CRASHED == task.status

        # Was the crash error successfully and consistently recorded?
        assert reported_error[0] is not None
        nl = os.linesep
        assert service.invalid_lines() == ["two", "four", "six"]
        assert service.error_lines() == ["one", "three", "five", "seven"]
        expected = (
            f"Worker crashed with exit code ###.{nl}"
            f"{nl}"
            f"[stdout]{nl}"
            f"two{nl}"
            f"four{nl}"
            f"six{nl}"
            f"{nl}"
            f"[stderr]{nl}"
            f"one{nl}"
            f"three{nl}"
            f"five{nl}"
            f"seven{nl}"
        )
        generalized_error = re.sub(r"exit code -?[0-9]+", "exit code ###", task.error)
        assert expected == generalized_error


def test_task_result():
    """Tests Task.result() convenience method."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Create a task that produces a result.
        task = service.task("'success'").wait_for()
        assert TaskStatus.COMPLETE == task.status

        # Test the result() convenience method.
        result = task.result()
        assert result == "success"

        # Verify it's the same as directly accessing outputs.
        assert task.outputs.get("result") == result


def test_task_result_null():
    """Tests Task.result() returns None when no result is set."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Create a task that doesn't set a result.
        task = service.task("print('no result')").wait_for()
        assert TaskStatus.COMPLETE == task.status

        # result() should return None.
        assert task.result() is None
