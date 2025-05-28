###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2024 Appose developers.
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

"""
The Appose worker for running Python scripts.

Like all Appose workers, this program conforms to the Appose worker process
contract, meaning it accepts requests on stdin and produces responses on
stdout, both formatted according to Appose's assumptions.

For details, see the Appose README:
https://github.com/apposed/appose/blob/-/README.md#workers
"""

import ast
import sys
import traceback
from threading import Thread
from time import sleep
from typing import Optional

# NB: Avoid relative imports so that this script can be run standalone.
from appose.service import RequestType, ResponseType
from appose.types import Args, _set_worker, decode, encode


class Task:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid
        self.outputs = {}
        self.finished = False
        self.cancel_requested = False
        self.thread = None  # Initialize thread attribute

    def update(
        self,
        message: Optional[str] = None,
        current: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> None:
        args = {}
        if message is not None:
            args["message"] = str(message)
        if current is not None:
            try:
                args["current"] = int(current)
            except ValueError:
                pass
        if maximum is not None:
            try:
                args["maximum"] = int(maximum)
            except ValueError:
                pass
        self._respond(ResponseType.UPDATE, args)

    def cancel(self) -> None:
        self._respond(ResponseType.CANCELATION, None)

    def fail(self, error: Optional[str] = None) -> None:
        args = None if error is None else {"error": error}
        self._respond(ResponseType.FAILURE, args)

    def _start(self, script: str, inputs: Optional[Args]) -> None:
        def execute_script():
            # Populate script bindings.
            binding = {"task": self}
            if inputs is not None:
                binding.update(inputs)

            # Inform the calling process that the script is launching.
            self._report_launch()

            # Execute the script.
            # result = exec(script, locals=binding)
            result = None
            try:
                # NB: Execute the block, except for the last statement,
                # which we evaluate instead to get its return value.
                # Credit: https://stackoverflow.com/a/39381428/1207769

                block = ast.parse(script, mode="exec")
                last = None
                if (
                    len(block.body) > 0
                    and hasattr(block.body[-1], "value")
                    and not isinstance(block.body[-1], ast.Assign)
                ):
                    # Last statement of the script looks like an expression. Evaluate!
                    last = ast.Expression(block.body.pop().value)

                # NB: When `exec` gets two separate objects as *globals* and
                # *locals*, the code will be executed as if it were embedded in
                # a class definition. This means functions and classes defined
                # in the executed code will not be able to access variables
                # assigned at the top level, because the "top level" variables
                # are treated as class variables in a class definition.
                # See: https://docs.python.org/3/library/functions.html#exec
                _globals = binding
                exec(compile(block, "<string>", mode="exec"), _globals, binding)
                if last is not None:
                    result = eval(
                        compile(last, "<string>", mode="eval"), _globals, binding
                    )
            except Exception:
                self.fail(traceback.format_exc())
                return

            # Report the results to the Appose calling process.
            if isinstance(result, dict):
                # Script produced a dict; add all entries to the outputs.
                self.outputs.update(result)
            elif result is not None:
                # Script produced a non-dict; add it alone to the outputs.
                self.outputs["result"] = result

            self._report_completion()

        # Create a thread and save a reference to it, in case its script
        # ends up killing the thread. This happens e.g. if it calls sys.exit.
        self.thread = Thread(target=execute_script, name=f"Appose-{self.uuid}")
        self.thread.start()

    def _report_launch(self) -> None:
        self._respond(ResponseType.LAUNCH, None)

    def _report_completion(self) -> None:
        args = None if self.outputs is None else {"outputs": self.outputs}
        self._respond(ResponseType.COMPLETION, args)

    def _respond(self, response_type: ResponseType, args: Optional[Args]) -> None:
        already_terminated = False
        if response_type.is_terminal():
            if self.finished:
                # This is not the first terminal response. Let's
                # remember, in case an exception is generated below,
                # so that we can avoid infinite recursion loops.
                already_terminated = True
            self.finished = True

        response = {"task": self.uuid, "responseType": response_type.value}
        if args is not None:
            response.update(args)
        # NB: Flush is necessary to ensure service receives the data!
        try:
            print(encode(response), flush=True)
        except Exception:
            if already_terminated:
                # An exception triggered a failure response which
                # then triggered another exception. Let's stop here
                # to avoid the risk of infinite recursion loops.
                return
            # Encoding can fail due to unsupported types, when the
            # response or its elements are not supported by JSON encoding.
            # No matter what goes wrong, we want to tell the caller.
            self.fail(traceback.format_exc())


def main() -> None:
    _set_worker(True)

    tasks = {}
    running = True

    def cleanup_threads():
        while running:
            sleep(0.05)
            dead = {
                uuid: task for uuid, task in tasks.items() if task.thread is not None and not task.thread.is_alive()
            }
            for uuid, task in dead.items():
                tasks.pop(uuid)
                if not task.finished:
                    # The task died before reporting a terminal status.
                    # We report this situation as failure by thread death.
                    task.fail("thread death")

    Thread(target=cleanup_threads, name="Appose-Janitor").start()

    while True:
        try:
            line = input().strip()
        except EOFError:
            break
        if not line:
            break

        request = decode(line)
        uuid = request.get("task")
        request_type = request.get("requestType")

        match RequestType(request_type):
            case RequestType.EXECUTE:
                script = request.get("script")
                inputs = request.get("inputs")
                task = Task(uuid)
                tasks[uuid] = task
                task._start(script, inputs)

            case RequestType.CANCEL:
                task = tasks.get(uuid)
                if task is None:
                    print(f"No such task: {uuid}", file=sys.stderr)
                    continue
                task.cancel_requested = True

    running = False


if __name__ == "__main__":
    main()
