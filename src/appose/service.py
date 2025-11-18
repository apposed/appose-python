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

"""
The appose.service package contains classes for services and tasks.
"""

from __future__ import annotations

import subprocess
import threading
from enum import Enum
from pathlib import Path
from traceback import format_exc
from typing import Any, Callable
from uuid import uuid4

from .syntax import ScriptSyntax
from .util.types import Args, decode, encode


class TaskException(Exception):
    """
    Exception raised when a Task fails to complete successfully.

    This exception is raised by Task.wait_for() when the task finishes
    in a non-successful state (FAILED, CANCELED, or CRASHED).
    """

    def __init__(self, message: str, task: "Task") -> None:
        super().__init__(message)
        self.task = task

    @property
    def status(self) -> "TaskStatus":
        """Returns the status of the failed task."""
        return self.task.status

    @property
    def task_error(self) -> str | None:
        """Returns the error message from the task, if available."""
        return self.task.error


class Service:
    """
    An Appose *service* provides access to a linked Appose *worker* running
    in a different process. Using the service, programs create Appose *tasks*
    that run asynchronously in the worker process, which notifies the
    service of updates via communication over pipes (stdin and stdout).
    """

    _service_count: int = 0

    def __init__(
        self, cwd: str | Path, args: list[str], syntax: ScriptSyntax | None = None
    ) -> None:
        self._cwd: Path = Path(cwd)
        self._args: list[str] = args[:]
        self._tasks: dict[str, "Task"] = {}
        self._service_id: int = Service._service_count
        Service._service_count += 1
        self._process: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._debug_callback: Callable[[Any], Any] | None = None
        self._syntax: ScriptSyntax | None = syntax

    def syntax(self) -> ScriptSyntax | None:
        """
        Returns the script syntax associated with this service.

        Returns:
            The script syntax, or None if not configured.
        """
        return self._syntax

    def debug(self, debug_callback: Callable[[Any], Any]) -> None:
        """
        Register a callback function to receive messages
        describing current service/worker activity.

        :param debug_callback:
            A function that accepts a single string argument.
        """
        self._debug_callback = debug_callback

    def start(self) -> None:
        """
        Explicitly launch the worker process associated with this service.

        This method is called automatically the first time a task is launched.
        But you can call it yourself if you want to let the worker process
        get going asynchronously before running the first task, or if you
        want to register a debug callback before the process starts to ensure
        you don't miss any events that occur early in the worker execution.
        """
        if self._process is not None:
            # Already started.
            return

        prefix = f"Appose-Service-{self._service_id}"
        self._process = subprocess.Popen(
            self._args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=self._cwd,
            text=True,
        )
        self._stdout_thread = threading.Thread(
            target=self._stdout_loop, name=f"{prefix}-Stdout"
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop, name=f"{prefix}-Stderr"
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name=f"{prefix}-Monitor"
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._monitor_thread.start()

    def task(
        self, script: str, inputs: Args | None = None, queue: str | None = None
    ) -> "Task":
        """
        Create a new task, passing the given script to the worker for execution.
        :param script:
            The script for the worker to execute in its environment.
        :param inputs:
            Optional list of key/value pairs to feed into the script as inputs.
        :param queue:
            Optional queue target. Pass "main" to queue to worker's main thread.
        """
        self.start()
        return Task(self, script, inputs, queue)

    def get_var(self, name: str) -> Any:
        """
        Retrieves a variable's value from the worker process's global scope.

        The variable must have been previously exported using task.export()
        to be accessible across tasks.

        Args:
            name: The name of the variable to retrieve.

        Returns:
            The value of the variable.

        Raises:
            TaskException: If the variable retrieval fails.
            ValueError: If no script syntax has been configured for this service.
        """
        if self._syntax is None:
            raise ValueError("No script syntax configured for this service")
        script = self._syntax.get_var(name)
        task = self.task(script).wait_for()
        return task.outputs.get("result")

    def put_var(self, name: str, value: Any) -> None:
        """
        Sets a variable in the worker process's global scope and exports it
        for future use across tasks.

        Args:
            name: The name of the variable to set in the worker process.
            value: The value to assign to the variable.

        Raises:
            TaskException: If the variable assignment fails.
            ValueError: If no script syntax has been configured for this service.
        """
        if self._syntax is None:
            raise ValueError("No script syntax configured for this service")
        inputs = {"_value": value}
        script = self._syntax.put_var(name, "_value")
        self.task(script, inputs).wait_for()

    def call(self, function: str, *args: Any) -> Any:
        """
        Calls a function in the worker process with the given arguments and
        returns the result.

        The function must be accessible in the worker's global scope (either
        built-in or previously defined/imported).

        Args:
            function: The name of the function to call in the worker process.
            *args: The arguments to pass to the function.

        Returns:
            The result of the function call.

        Raises:
            TaskException: If the function call fails.
            ValueError: If no script syntax has been configured for this service.
        """
        if self._syntax is None:
            raise ValueError("No script syntax configured for this service")
        inputs = {}
        var_names = []
        for i, arg in enumerate(args):
            var_name = f"arg{i}"
            inputs[var_name] = arg
            var_names.append(var_name)
        script = self._syntax.call(function, var_names)
        task = self.task(script, inputs).wait_for()
        return task.outputs.get("result")

    def proxy(self, var: str, api: type, queue: str | None = None) -> Any:
        """
        Creates a proxy object providing strongly typed access to a remote
        object in this service's worker process.

        Method calls on the proxy are transparently forwarded to the remote
        object via Tasks.

        Important: The variable must be explicitly exported using
        task.export(varName=value) in a previous task. Only exported variables
        are accessible across tasks within the same service.

        Args:
            var: The name of the exported variable in the worker process
                 referencing the remote object.
            api: The interface/protocol class that the proxy should implement.
            queue: Optional queue identifier for task execution. Pass "main" to
                   ensure execution on the worker's main thread.

        Returns:
            A proxy object that forwards method calls to the remote object.

        Raises:
            ValueError: If no script syntax has been configured for this service.
        """
        if self._syntax is None:
            raise ValueError("No script syntax configured for this service")
        from .util.proxy import create

        return create(self, var, queue)

    def close(self) -> None:
        """
        Close the worker process's input stream, in order to shut it down.
        """
        self._process.stdin.close()

    def __enter__(self) -> "Service":
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.close()

    def _stdout_loop(self) -> None:
        """
        Input loop processing lines from the worker's stdout stream.
        """
        while True:
            stdout = self._process.stdout
            # noinspection PyBroadException
            try:
                line = None if stdout is None else stdout.readline()
            except Exception:
                # Something went wrong reading the line. Panic!
                self._debug_service(format_exc())
                break

            if not line:  # readline returns empty string upon EOF
                self._debug_service("<worker stdout closed>")
                return

            # noinspection PyBroadException
            try:
                response = decode(line)
                self._debug_service(line)  # Echo the line to the debug listener.
                uuid = response.get("task")
                if uuid is None:
                    self._debug_service("Invalid service message: {line}")
                    continue
                task = self._tasks.get(uuid)
                if task is None:
                    self._debug_service(f"No such task: {uuid}")
                    continue
                # noinspection PyProtectedMember
                task._handle(response)
            except Exception:
                # Something went wrong decoding the line of JSON.
                # Skip it and keep going, but log it first.
                self._debug_service(f"<INVALID> {line}")

    def _stderr_loop(self) -> None:
        """
        Input loop processing lines from the worker's stderr stream.
        """
        # noinspection PyBroadException
        try:
            while True:
                stderr = self._process.stderr
                line = None if stderr is None else stderr.readline()
                if not line:  # readline returns empty string upon EOF
                    self._debug_service("<worker stderr closed>")
                    return
                self._debug_worker(line)
        except Exception:
            self._debug_service(format_exc())

    def _monitor_loop(self) -> None:
        # Wait until the worker process terminates.
        self._process.wait()

        # Do some sanity checks.
        exit_code = self._process.returncode
        if exit_code != 0:
            self._debug_service(
                f"<worker process terminated with exit code {exit_code}>"
            )
        task_count = len(self._tasks)
        if task_count > 0:
            self._debug_service(
                f"<worker process terminated with {task_count} pending tasks>"
            )

        # Notify any remaining tasks about the process crash.
        for task in self._tasks.values():
            task._crash()

        self._tasks.clear()

    def _debug_service(self, message: str) -> None:
        self._debug("SERVICE", message)

    def _debug_worker(self, message: str) -> None:
        self._debug("WORKER", message)

    def _debug(self, prefix: str, message: str) -> None:
        """
        Pass a message to the callback registered via the debug method.
        """
        if self._debug_callback is None:
            return
        self._debug_callback(f"[{prefix}-{self._service_id}] {message}")


class TaskStatus(Enum):
    INITIAL = "INITIAL"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    CANCELED = "CANCELED"
    FAILED = "FAILED"
    CRASHED = "CRASHED"

    def is_finished(self):
        """
        True iff status is COMPLETE, CANCELED, FAILED, or CRASHED.
        """
        return self in (
            TaskStatus.COMPLETE,
            TaskStatus.CANCELED,
            TaskStatus.FAILED,
            TaskStatus.CRASHED,
        )


class RequestType(Enum):
    EXECUTE = "EXECUTE"
    CANCEL = "CANCEL"


class ResponseType(Enum):
    LAUNCH = "LAUNCH"
    UPDATE = "UPDATE"
    COMPLETION = "COMPLETION"
    CANCELATION = "CANCELATION"
    FAILURE = "FAILURE"
    CRASH = "CRASH"

    """
    True iff response type is COMPLETE, CANCELED, FAILED, or CRASHED.
    """

    def is_terminal(self):
        return self in (
            ResponseType.COMPLETION,
            ResponseType.CANCELATION,
            ResponseType.FAILURE,
            ResponseType.CRASH,
        )


class TaskEvent:
    def __init__(
        self,
        task: "Task",
        response_type: ResponseType,
        message: str | None = None,
        current: int | None = None,
        maximum: int | None = None,
        info: Args | None = None,
    ) -> None:
        self.task: "Task" = task
        self.response_type: ResponseType = response_type
        self.message: str | None = message
        self.current: int | None = current
        self.maximum: int | None = maximum
        self.info: Args | None = info

    def __str__(self):
        return f"[{self.response_type}] {self.task}"


# noinspection PyProtectedMember
class Task:
    """
    An Appose *task* is an asynchronous operation performed by its
    associated Appose *service*. It is analogous to an asyncio.Future.
    """

    def __init__(
        self,
        service: Service,
        script: str,
        inputs: Args | None = None,
        queue: str | None = None,
    ) -> None:
        self.uuid: str = uuid4().hex
        self.service: Service = service
        self.script: str = script
        self.inputs: Args = {}
        self.queue: str | None = queue
        if inputs is not None:
            self.inputs.update(inputs)
        self.outputs: Args = {}
        self.status: TaskStatus = TaskStatus.INITIAL
        self.message: str | None = None
        self.current: int = 0
        self.maximum: int = 1
        self.error: str | None = None
        self.listeners: list[Callable[["TaskEvent"], None]] = []
        self.cv: threading.Condition = threading.Condition()
        self.service._tasks[self.uuid] = self

    def start(self) -> "Task":
        with self.cv:
            if self.status != TaskStatus.INITIAL:
                raise RuntimeError("Task is not in the INITIAL state")

            self.status = TaskStatus.QUEUED

        args = {"script": self.script, "inputs": self.inputs, "queue": self.queue}
        self._request(RequestType.EXECUTE, args)

        return self

    def listen(self, listener: Callable[["TaskEvent"], None]) -> None:
        """
        Register a callback function to be notified of updates to the task.
        """
        with self.cv:
            if self.status != TaskStatus.INITIAL:
                raise RuntimeError("Task is not in the INITIAL state")

            self.listeners.append(listener)

    def wait_for(self) -> "Task":
        """
        Wait for this task to complete.

        Returns:
            This task (for method chaining).

        Raises:
            TaskException: If the task fails, is canceled, or crashes.
        """
        with self.cv:
            if self.status == TaskStatus.INITIAL:
                self.start()

            if self.status not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                # Task already finished - check if we need to raise
                if self.status != TaskStatus.COMPLETE:
                    self._raise_if_failed()
                return self

            self.cv.wait()

        # After waiting, check if task failed
        self._raise_if_failed()
        return self

    def result(self) -> Any:
        """
        Returns the result of this task.

        This is a convenience method that returns outputs["result"].
        For tasks that return a single value (e.g., from an expression),
        that value is stored in outputs["result"].

        Returns:
            The task's result value.
        """
        return self.outputs.get("result")

    def _raise_if_failed(self) -> None:
        """Raise TaskException if this task is in a failed state."""
        if self.status == TaskStatus.FAILED:
            error_msg = self.error if self.error else "Unknown error"
            raise TaskException(f"Task failed: {error_msg}", self)
        elif self.status == TaskStatus.CANCELED:
            raise TaskException("Task was canceled", self)
        elif self.status == TaskStatus.CRASHED:
            error_msg = self.error if self.error else "Worker process crashed"
            raise TaskException(f"Task crashed: {error_msg}", self)

    def cancel(self) -> None:
        """
        Send a task cancelation request to the worker process.
        """
        self._request(RequestType.CANCEL, {})

    def _request(self, request_type: RequestType, args: Args) -> None:
        """
        Send a request to the worker process.
        """
        request = {"task": self.uuid, "requestType": request_type.value}
        if args is not None:
            request.update(args)

        encoded = encode(request)
        # NB: Flush is necessary to ensure worker receives the data!
        print(encoded, file=self.service._process.stdin, flush=True)
        self.service._debug_service(encoded)

    def _handle(self, response: Args) -> None:
        maybe_response_type = response.get("responseType")
        if maybe_response_type is None:
            self.service._debug_service("Message type not specified")
            return
        response_type = ResponseType(maybe_response_type)

        if response_type == ResponseType.LAUNCH:
            self.status = TaskStatus.RUNNING
        elif response_type == ResponseType.UPDATE:
            # No extra action needed.
            pass
        elif response_type == ResponseType.COMPLETION:
            self.service._tasks.pop(self.uuid, None)
            self.status = TaskStatus.COMPLETE
            outputs = response.get("outputs")
            if outputs is not None:
                self.outputs.update(outputs)
        elif response_type == ResponseType.CANCELATION:
            self.service._tasks.pop(self.uuid, None)
            self.status = TaskStatus.CANCELED
        elif response_type == ResponseType.FAILURE:
            self.service._tasks.pop(self.uuid, None)
            self.status = TaskStatus.FAILED
            self.error = response.get("error")
        else:
            self.service._debug_service(
                f"Invalid service message type: {response_type}"
            )
            return

        message = response.get("message")
        current = response.get("current")
        maximum = response.get("maximum")
        info = response.get("info")
        event = TaskEvent(self, response_type, message, current, maximum, info)
        for listener in self.listeners:
            listener(event)

        if self.status.is_finished():
            with self.cv:
                self.cv.notify_all()

    def _crash(self):
        event = TaskEvent(self, ResponseType.CRASH)
        self.status = TaskStatus.CRASHED
        for listener in self.listeners:
            listener(event)
        with self.cv:
            self.cv.notify_all()

    def __str__(self):
        return f"{self.uuid=}, {self.status=}, {self.error=}"
