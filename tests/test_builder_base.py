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

"""Base helper functions for Appose builder unit testing."""

from __future__ import annotations

import os

from appose import Environment
from appose.service import ResponseType, Task, TaskStatus


# Test scripts

COLLATZ_PYTHON = """# Computes the stopping time of a given value
# according to the Collatz conjecture sequence.
time = 0
v = 9999
while v != 1:
    v = v//2 if v%2==0 else 3*v+1
    task.update(f"[{time}] -> {v}", current=time)
    time += 1
task.outputs["result"] = time
"""

THREAD_CHECK_PYTHON = """import threading
task.outputs["thread"] = threading.current_thread().name
"""


# Helper functions


def execute_and_assert(service, script: str):
    """
    Execute a script and validate the Collatz sequence execution.

    Args:
        service: The service to execute on
        script: The script to execute
    """
    task = service.task(script)

    # Record the state of the task for each event that occurs
    class TaskState:
        def __init__(self, event):
            self.response_type = event.response_type
            self.message = event.message
            self.current = event.current
            self.maximum = event.maximum
            self.status = event.task.status
            self.error = event.task.error

    events: list[TaskState] = []
    task.listen(lambda event: events.append(TaskState(event)))

    # Wait for task to finish
    task.wait_for()

    # Validate the execution result
    assert_complete(task)
    result = task.outputs.get("result")
    assert result == 91, f"Expected result 91, got {result}"

    # Validate the events received
    assert len(events) == 93, f"Expected 93 events, got {len(events)}"

    launch = events[0]
    assert launch.response_type == ResponseType.LAUNCH
    assert launch.status == TaskStatus.RUNNING
    assert launch.error is None

    v = 9999
    for i in range(91):
        v = v // 2 if v % 2 == 0 else 3 * v + 1
        update = events[i + 1]
        assert update.response_type == ResponseType.UPDATE
        assert update.status == TaskStatus.RUNNING
        assert update.message == f"[{i}] -> {v}"
        assert update.current == i
        assert update.maximum == 0
        assert update.error is None

    completion = events[92]
    assert completion.response_type == ResponseType.COMPLETION
    assert completion.message is None  # no message from non-UPDATE response
    assert completion.current == 0  # no current from non-UPDATE response
    assert completion.maximum == 0  # no maximum from non-UPDATE response
    assert completion.error is None


def cowsay_and_assert(env: Environment, greeting: str):
    """
    Execute a cowsay script and validate the output.

    Args:
        env: The environment to execute in
        greeting: The greeting to pass to cowsay
    """
    with env.python() as service:
        maybe_debug(service)
        task = service.task(
            f"import cowsay\ncowsay.get_output_string('cow', '{greeting}')\n"
        )
        task.wait_for()
        assert_complete(task)

        # Verify cowsay output contains the greeting and key elements
        # (exact spacing can vary between cowsay versions)
        actual = task.outputs.get("result")
        assert actual is not None, "Cowsay output should not be null"
        assert greeting in actual, f"Output should contain the greeting: {greeting}"
        assert "^__^" in actual, "Output should contain cow face"
        assert "(oo)" in actual, "Output should contain cow eyes"
        assert "||----w |" in actual, "Output should contain cow legs"


def maybe_debug(service):
    """
    Enable debug output if DEBUG or appose.debug is set.

    Args:
        service: The service to enable debug on
    """
    debug1 = os.environ.get("DEBUG")
    debug2 = os.environ.get("appose.debug")
    if not falsy(debug1) or not falsy(debug2):
        import sys

        service.debug(lambda msg: print(msg, file=sys.stderr, end=""))


def falsy(value: str) -> bool:
    """
    Check if a string value is falsy.

    Args:
        value: The value to check

    Returns:
        True if the value is None, empty, "false", or "0"
    """
    if value is None:
        return True
    t_value = value.strip()
    return not t_value or t_value.lower() == "false" or t_value == "0"


def assert_complete(task: Task):
    """
    Assert that a task completed successfully.

    Args:
        task: The task to check
    """
    error_message = ""
    if task.status != TaskStatus.COMPLETE:
        # Get caller method name from stack
        import traceback

        caller = traceback.extract_stack()[-2].name
        error_message = f"TASK ERROR in method {caller}:\n{task.error}"
    assert task.status == TaskStatus.COMPLETE, error_message
