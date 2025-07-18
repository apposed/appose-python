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

import subprocess
import threading
from enum import Enum
from pathlib import Path
from traceback import format_exc
from typing import Any, Callable
from uuid import uuid4

from .types import Args, decode, encode


class Service:
    """
    An Appose *service* provides access to a linked Appose *worker* running
    in a different process. Using the service, programs create Appose *tasks*
    that run asynchronously in the worker process, which notifies the
    service of updates via communication over pipes (stdin and stdout).
    """

    _service_count = 0

    def __init__(self, cwd: str | Path, args: list[str]) -> None:
        self._cwd = cwd
        self._args = args[:]
        self._tasks: dict[str, "Task"] = {}
        self._service_id = Service._service_count
        Service._service_count += 1
        self._process: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._debug_callback: Callable[[Any], Any] | None = None

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
        info: dict[str, Any] | None = None,
    ) -> None:
        self.task: "Task" = task
        self.response_type: ResponseType = response_type
        self.message: str | None = message
        self.current: int | None = current
        self.maximum: int | None = maximum
        self.info: dict[str, Any] | None = info

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
        self.uuid = uuid4().hex
        self.service = service
        self.script = script
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
        self.cv = threading.Condition()
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

    def wait_for(self) -> None:
        with self.cv:
            if self.status == TaskStatus.INITIAL:
                self.start()

            if self.status not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                return

            self.cv.wait()

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

        match response_type:
            case ResponseType.LAUNCH:
                self.status = TaskStatus.RUNNING
            case ResponseType.UPDATE:
                # No extra action needed.
                pass
            case ResponseType.COMPLETION:
                self.service._tasks.pop(self.uuid, None)
                self.status = TaskStatus.COMPLETE
                outputs = response.get("outputs")
                if outputs is not None:
                    self.outputs.update(outputs)
            case ResponseType.CANCELATION:
                self.service._tasks.pop(self.uuid, None)
                self.status = TaskStatus.CANCELED
            case ResponseType.FAILURE:
                self.service._tasks.pop(self.uuid, None)
                self.status = TaskStatus.FAILED
                self.error = response.get("error")
            case _:
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
