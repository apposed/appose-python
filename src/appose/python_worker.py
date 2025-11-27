# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
The Appose worker for running Python scripts.

Like all Appose workers, this program conforms to the Appose worker process
contract, meaning it accepts requests on stdin and produces responses on
stdout, both formatted according to Appose's assumptions.

For details, see the Appose README:
https://github.com/apposed/appose/blob/-/README.md#workers
"""

from __future__ import annotations

import ast
import os
import sys
import traceback
from threading import Thread
from time import sleep
from typing import Any

# NB: Avoid relative imports so that this script can be run standalone.
from appose.service import RequestType, ResponseType
from appose.util import message
from appose.util.message import Args


class Task:
    def __init__(
        self,
        worker: "Worker" | None = None,
        uuid: str | None = None,
        script: str | None = None,
        inputs: Args | None = None,
    ) -> None:
        self._worker: Worker = worker or Worker()
        self._uuid: str | None = uuid
        self._script: str | None = script
        self._inputs: Args | None = inputs
        self._finished = False
        self._thread: Thread | None = None

        # Public-facing fields for use within the task script.
        self.outputs: Args = {}
        self.cancel_requested = False

    def export(self, **kwargs):
        self._worker.exports.update(kwargs)

    def update(
        self,
        message: str | None = None,
        current: int | None = None,
        maximum: int | None = None,
        info: Args | None = None,
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
        args["info"] = info
        self._respond(ResponseType.UPDATE, args)

    def cancel(self) -> None:
        self._respond(ResponseType.CANCELATION, None)

    def fail(self, error: str | None = None) -> None:
        args = None if error is None else {"error": error}
        self._respond(ResponseType.FAILURE, args)

    def _run(self) -> None:
        try:
            # Populate script bindings.
            binding = {"task": self}
            binding.update(self._worker.exports)
            if self._inputs is not None:
                binding.update(self._inputs)

            # Inform the calling process that the script is launching.
            self._report_launch()

            # Execute the script.
            # result = exec(script, locals=binding)
            result = None

            # NB: Execute the block, except for the last statement,
            # which we evaluate instead to get its return value.
            # Credit: https://stackoverflow.com/a/39381428/1207769

            block = ast.parse(self._script, mode="exec")
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
                result = eval(compile(last, "<string>", mode="eval"), _globals, binding)

            # Report the results to the Appose calling process.
            if isinstance(result, dict):
                # Script produced a dict; add all entries to the outputs.
                self.outputs.update(result)
            elif result is not None:
                # Script produced a non-dict; add it alone to the outputs.
                self.outputs["result"] = result
            self._report_completion()
        except BaseException:
            self.fail(traceback.format_exc())

    def _report_launch(self) -> None:
        self._respond(ResponseType.LAUNCH, None)

    def _report_completion(self) -> None:
        args = None if self.outputs is None else {"outputs": self.outputs}
        self._respond(ResponseType.COMPLETION, args)

    def _respond(self, response_type: ResponseType, args: Args | None) -> None:
        already_terminated = False
        if response_type.is_terminal():
            if self._finished:
                # This is not the first terminal response. Let's
                # remember, in case an exception is generated below,
                # so that we can avoid infinite recursion loops.
                already_terminated = True
            self._finished = True

        response = {}
        if args is not None:
            response.update(args)
        response.update({"task": self._uuid, "responseType": response_type.value})
        # NB: Flush is necessary to ensure service receives the data!
        try:
            print(message.encode(response), flush=True)
        except BaseException:
            if already_terminated:
                # An exception triggered a failure response which
                # then triggered another exception. Let's stop here
                # to avoid the risk of infinite recursion loops.
                return
            # Encoding can fail due to unsupported types, when the
            # response or its elements are not supported by JSON encoding.
            # No matter what goes wrong, we want to tell the caller.
            self.fail(traceback.format_exc())


class Worker:
    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.queue: list[Task] = []
        self.exports: dict[str, Any] = {}

        # Flag this process as a worker, not a service.
        message._worker_mode = True
        # Store reference to this worker for auto-export functionality.
        message._worker_instance = self

    def run(self) -> None:
        """
        Process tasks from the task queue.
        """
        self.running = True
        Thread(target=self._process_input, name="Appose-Receiver").start()
        Thread(target=self._cleanup_threads, name="Appose-Janitor").start()

        while self.running:
            if len(self.queue) == 0:
                # Nothing queued, so wait a bit.
                sleep(0.05)
                continue
            task = self.queue.pop()
            task._run()

    def _process_input(self) -> None:
        while True:
            try:
                line = input().strip()
            except EOFError:
                line = None
            if not line:
                self.running = False
                return

            request = message.decode(line)
            uuid = request.get("task")
            request_type = RequestType(request.get("requestType"))

            if request_type == RequestType.EXECUTE:
                script = request.get("script")
                inputs = request.get("inputs")
                queue = request.get("queue")
                task = Task(self, uuid, script, inputs)
                self.tasks[uuid] = task
                if queue == "main":
                    # Add the task to the main thread queue.
                    self.queue.append(task)
                else:
                    # Create a thread and save a reference to it, in case its script
                    # kills the thread. This happens e.g. if it calls sys.exit.
                    task._thread = Thread(target=task._run, name=f"Appose-{uuid}")
                    task._thread.start()

            elif request_type == RequestType.CANCEL:
                task = self.tasks.get(uuid)
                if task is None:
                    print(f"No such task: {uuid}", file=sys.stderr)
                    continue
                task.cancel_requested = True

    def _cleanup_threads(self) -> None:
        while self.running:
            sleep(0.05)
            dead = {
                uuid: task
                for uuid, task in self.tasks.items()
                if task._thread is not None and not task._thread.is_alive()
            }
            for uuid, task in dead.items():
                self.tasks.pop(uuid)
                if not task._finished:
                    # The task died before reporting a terminal status.
                    # We report this situation as failure by thread death.
                    task.fail("thread death")


def main() -> None:
    worker = Worker()

    # Execute init script if provided via environment variable.
    # This happens before the worker's I/O loop starts, which is useful
    # for imports that may interfere with stdin/stdout operations.
    init_script_path = os.environ.get("APPOSE_INIT_SCRIPT")
    if init_script_path and os.path.exists(init_script_path):
        try:
            # Execute init script in its own namespace.
            init_namespace = {}
            with open(init_script_path, "r", encoding="utf-8") as f:
                init_code = f.read()
            exec(init_code, init_namespace)

            # Export all public (non-underscore) attributes to worker.
            for key, value in init_namespace.items():
                if not key.startswith("_"):
                    worker.exports[key] = value

            # Clean up the temp file.
            os.remove(init_script_path)
        except BaseException as e:
            print(f"[WARNING] Init script failed: {e}", file=sys.stderr)

    # On Windows, we must import numpy here on the main thread before opening stdin.
    # Otherwise, the import will hang, even if run as part of a task with queue="main".
    # See: https://github.com/numpy/numpy/issues/24290.
    # The best way to do that is by creating the Python service like:
    #
    #     env.python().init("import numpy")
    #
    # or similar `init` script invocation.
    #
    # We check here whether the hanging conditions might be met: NumPy installed,
    # but not imported yet. And if so, issue a stern warning, as a kindness.
    try:
        from importlib.metadata import distributions

        numpy_installed = any(
            dist.metadata["Name"] == "numpy" for dist in distributions()
        )
        if numpy_installed and "numpy" not in globals():
            print(
                "[WARNING] This environment includes numpy, but numpy was not imported via a service init script.",
                file=sys.stderr,
            )
            print(
                "[WARNING] If you attempt to `import numpy` in a task on Windows, the task will hang!",
                file=sys.stderr,
            )
            print(
                "[WARNING] See https://github.com/apposed/appose/issues/23 for details.",
                file=sys.stderr,
            )
    except Exception:
        pass

    worker.run()


if __name__ == "__main__":
    main()
