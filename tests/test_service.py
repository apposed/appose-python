###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2025 Appose developers.
# %%
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# #L%
###


import appose
from appose.service import TaskStatus
from tests.test_base import execute_and_assert, maybe_debug

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
    env = appose.base("no-java-to-be-found-here").build()
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
