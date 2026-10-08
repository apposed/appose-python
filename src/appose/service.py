# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
The appose.service package contains classes for services and tasks.
"""

from __future__ import annotations

import atexit
import os
import re
import subprocess
import tempfile
import threading
import time
import weakref
from enum import Enum
from pathlib import Path
from traceback import format_exc
from typing import TYPE_CHECKING, Any, Callable, overload
from uuid import uuid4

from ._version import __version__
from .syntax import ScriptSyntax
from .syntax import get as syntax_from_name
from .util import process
from .util.message import Args, decode, encode, proxify_worker_objects

if TYPE_CHECKING:
    from typing import Self


class TaskException(Exception):
    """
    Exception raised when a Task fails to complete successfully.

    This exception is raised by Task.wait_for() when the task finishes
    in a non-successful state (FAILED, CANCELED, or CRASHED).
    """

    def __init__(self, message: str, task: Task) -> None:
        super().__init__(message)
        self.task: Task = task


class Service:
    """
    An Appose *service* provides access to a linked Appose *worker* running
    in a different process. Using the service, programs create Appose *tasks*
    that run asynchronously in the worker process, which notifies the
    service of updates via communication over pipes (stdin and stdout).

    A service still running when the program exits is shut down
    automatically: it is closed, and killed if its worker has not exited
    within exit_timeout seconds.
    """

    _service_count: int = 0

    exit_timeout: float | None = 5.0
    """
    Seconds to wait at program exit for the worker to shut down gracefully,
    before killing it. None waits indefinitely. Set this on the Service
    class to change the default, or on an instance to override it.
    """

    def __init__(
        self, cwd: str | Path, env_vars: dict[str, str | None] | None = None, *args: str
    ) -> None:
        self._cwd: Path = Path(cwd)
        self._env_vars: dict[str, str | None] = (
            env_vars.copy() if env_vars is not None else {}
        )
        self._args: list[str] = list(args)
        self._tasks: dict[str, Task] = {}
        self._service_id: int = Service._service_count
        Service._service_count += 1
        self._invalid_lines: list[str] = []
        self._error_lines: list[str] = []
        self._worker_info: Args | None = None
        self._incompatibility: str | None = None
        self._process: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._debug_callback: Callable[[str], Any] | None = None
        self._init_script: str | None = None
        self._libraries: list[str] = []
        self._syntax: ScriptSyntax | None = None
        self._exports: dict[str, Any] = {}
        self._export_count: int = 0
        self._exports_lock: threading.Lock = threading.Lock()
        self._stdin_lock: threading.Lock = threading.Lock()

    def debug(self, debug_callback: Callable[[str], Any]) -> Service:
        """
        Register a callback function to receive messages describing current
        service/worker activity.

        Args:
            debug_callback: A function that accepts a single string argument.
        """
        self._debug_callback = debug_callback
        return self

    def init(self, script: str) -> Service:
        """
        Register a script to be executed when the worker process first starts up,
        before any tasks are processed. This is useful for early initialization that
        must happen before the worker's main loop begins, such as importing libraries
        that may interfere with I/O operations.

        Example: On Windows, importing numpy can hang when stdin is open for reading
        (described at https://github.com/numpy/numpy/issues/24290).
        Using service.init("import numpy") works around this by importing
        numpy before the worker's I/O loop starts.

        Args:
            script: The script code to execute during worker initialization.

        Returns:
            This service object, for chaining method calls.

        Raises:
            RuntimeError: If the service has already started.
        """
        if self._process is not None:
            raise RuntimeError("Service already started")
        self._init_script = script
        return self

    def import_library(
        self,
        name: str,
        *,
        path: str | Path | None = None,
        source: str | dict[str, str] | None = None,
    ) -> Service:
        """
        Register library code with the worker, so that tasks can import it
        by name with a normal import statement, e.g. `import mylib`.

        The library is given either as a path on disk, or directly as source
        code (e.g. for tests, or code generated on the fly), but not both.
        Both are keyword-only, so that each call states which it means.

        The library is ordinary Python source, which can be developed and
        type-checked in an IDE like any other module, with no reference to
        Appose's task variable. Because an imported module lives in the
        worker's sys.modules, its module-level state persists across tasks:
        e.g., a cache of expensive-to-load models stays "warm" for all
        subsequent tasks, without the need for task.export.

        The library's source is read now and sent to the worker, so later
        changes to the files on disk are not seen unless the library is
        registered again. Package resources (via importlib.resources), on the
        other hand, are read from the directory on disk when accessed, as for
        any installed package; so they are available only to libraries given
        by path, on the same filesystem as the worker. Registering changed source evicts the previously
        imported module (and its state); registering unchanged source is a
        no-op. Registration alone does not import the library: the first
        task to import it does, and pays any initialization cost.

        If called before the service starts, registration happens during
        worker startup, before the init script (see init()) runs, which may
        then import the library itself. Otherwise, registration happens via a
        task, and this method blocks until it completes.

        Args:
            name: The top-level module name to import the library as.
            path: A single source file (imported as a module), or a directory
                of source files (imported as a package, with subdirectories
                as subpackages).
            source: The library's source code, as a string (imported as a
                module), or as a dict mapping relative POSIX paths such as
                "__init__.py" and "sub/mod.py" to source code (imported as a
                package).

        Returns:
            This service object, for chaining method calls.

        Raises:
            ValueError: If the name is not a valid module name, or not
                exactly one of path and source is given, or the path is
                neither a file nor a directory, or no script syntax has
                been configured for this service.
            NotImplementedError: If this service's script syntax does not
                support libraries.
            TaskException: If the worker fails to register the library.
        """
        if not name.isidentifier():
            raise ValueError(f"Invalid library name: {name}")
        if self._syntax is None:
            raise ValueError("No script syntax configured for this service")
        if (path is None) == (source is None):
            raise ValueError("Exactly one of path or source must be given")
        if source is not None:
            # NB: Not wrapped in <...>, which linecache would refuse to
            # resolve via the loader, leaving tracebacks without source lines.
            origin = f"<appose>/{name}"
            if isinstance(source, str):
                suffix = self._syntax.library_suffix()
                files = {f"{name}{suffix}": source}
                origin += suffix
                package = False
            else:
                files = dict(source)
                package = True
            script = self._syntax.import_library(name, files, origin, package)
            return self._register_library(script)
        path = Path(path).resolve()
        if path.is_file():
            files = {path.name: path.read_text(encoding="utf-8")}
            package = False
        elif path.is_dir():
            files = {
                f.relative_to(path).as_posix(): f.read_text(encoding="utf-8")
                for f in sorted(path.rglob(f"*{self._syntax.library_suffix()}"))
                if "__pycache__" not in f.parts
            }
            package = True
        else:
            raise ValueError(f"No such file or directory: {path}")
        script = self._syntax.import_library(name, files, path.as_posix(), package)
        return self._register_library(script)

    def _write_startup_script(
        self, script: str | None, prefix: str, env_var: str
    ) -> None:
        if not script:
            return
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=prefix, suffix=".txt", delete=False
        ) as f:
            f.write(script)
            self._env_vars[env_var] = f.name

    def _register_library(self, script: str) -> Service:
        if self._process is None:
            self._libraries.append(script)
        else:
            self.task(script).wait_for()
        return self

    def env(self, **vars: str | None) -> Service:
        """
        Set environment variables to pass to the worker process.

        Args:
            **vars: Key/value pairs to add to the worker's environment.
                A value of None causes the variable to be unset in the worker.

        Returns:
            This service object, for chaining method calls.
        """
        self._env_vars.update(vars)
        return self

    def start(self) -> Service:
        """
        Explicitly launch the worker process associated with this service.

        This method is called automatically the first time a task is launched.
        But you can call it yourself if you want to let the worker process
        get going asynchronously before running the first task, or if you
        want to register a debug callback before the process starts to ensure
        you don't miss any events that occur early in the worker execution.

        Returns:
            This service object, for chaining method calls.
        """
        if self._process is not None:
            # Already started.
            return self

        prefix = f"Appose-Service-{self._service_id}"

        # If libraries or an init script are provided, write them to temporary
        # files and pass their paths via environment variables. The worker
        # registers the libraries first, so that the init script can use them.
        self._write_startup_script(
            "".join(self._libraries), "appose-libraries-", "APPOSE_LIBRARY_SCRIPT"
        )
        self._write_startup_script(
            self._init_script, "appose-init-", "APPOSE_INIT_SCRIPT"
        )

        self._process = process.builder(self._cwd, self._env_vars, *self._args)
        _track(self)

        # NB: These threads block until the worker's output streams close, so
        # they must be daemon threads. Interpreter shutdown waits for every
        # non-daemon thread before running atexit hooks, so it would wait
        # forever on a worker that only an atexit hook (e.g. ours) shuts down.
        self._stdout_thread = threading.Thread(
            target=self._stdout_loop, name=f"{prefix}-Stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop, name=f"{prefix}-Stderr", daemon=True
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name=f"{prefix}-Monitor", daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._monitor_thread.start()
        return self

    def task(
        self, script: str, inputs: Args | None = None, queue: str | None = None
    ) -> Task:
        """
        Create a new task, passing the given script to the worker for execution.

        Args:
            script: The script for the worker to execute in its environment.
            inputs: Optional list of key/value pairs to feed into the script as inputs.
            queue: Optional queue target. Pass "main" to queue to worker's main thread.
        """
        self.start()
        return Task(self, script, inputs, queue)

    @overload
    def syntax(self) -> ScriptSyntax | None: ...

    @overload
    def syntax(self, syntax: str | ScriptSyntax) -> Service: ...

    def syntax(
        self, syntax: str | ScriptSyntax | None = None
    ) -> Service | ScriptSyntax | None:
        """
        Get or declare the script syntax of this service.

        Called with no argument, returns the current script syntax strategy
        (or None if not set). Called with an argument, declares the syntax and
        returns this service for chaining.

        This value determines which ScriptSyntax implementation is used
        for generating language-specific scripts.

        This method is called directly by Environment.python() and
        Environment.groovy() when creating services of those types.
        It can also be called manually to support custom languages with
        registered ScriptSyntax plugins.

        Args:
            syntax: The type identifier (e.g., "python", "groovy"), a
                ScriptSyntax instance, or None to retrieve the current syntax.

        Returns:
            The current script syntax when called with no argument; otherwise
            this service object, for chaining method calls.

        Raises:
            ValueError: If no syntax plugin is found for the given type.
        """
        if syntax is None:
            return self._syntax
        self._syntax = (
            syntax if isinstance(syntax, ScriptSyntax) else syntax_from_name(syntax)
        )
        return self

    def get_var(self, name: str) -> Any:
        """
        Retrieve a variable's value from the worker process's global scope.

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
        Set a variable in the worker process's global scope and export it
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
        Call a function in the worker process with the given arguments and
        return the result.

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

    def proxy(self, var: str, queue: str | None = None) -> Any:
        """
        Create a proxy object providing access to a remote object in this
        service's worker process.

        Method calls on the proxy are transparently forwarded to the remote
        object via Tasks.

        Important: The variable must be explicitly exported using
        task.export(varName=value) in a previous task. Only exported variables
        are accessible across tasks within the same service.

        Args:
            var: The name of the exported variable in the worker process
                 referencing the remote object.
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

    def close(self, timeout: float | None = None) -> int | None:
        """
        Close the worker process's input stream, in order to shut it down.
        The worker finishes any pending tasks, and then exits.

        Without a timeout, this method only begins the shutdown, returning
        immediately. With a timeout, it waits up to that many seconds for
        the worker to exit, then kills it (see kill()) if it has not.

        Args:
            timeout: Seconds to wait for the worker to exit before killing
                it, or None to return without waiting. Zero kills it at once.

        Returns:
            Exit code of the worker process, or None if no timeout was given.

        Raises:
            RuntimeError: If the service has not been started.
        """
        self._require_process()
        self._process.stdin.close()
        if timeout is None:
            return None
        try:
            return self.wait_for(timeout)
        except subprocess.TimeoutExpired:
            self.kill()
        # NB: The killed worker dies promptly, but the threads processing its
        # output may not: a descendant that left the process group could keep
        # the streams open, or a listener could be stuck. Do not wait forever.
        self._process.wait()
        self._join_threads(time.monotonic() + timeout)
        return self._process.returncode

    def kill(self) -> None:
        """
        Force the service's worker process to begin shutting down. Any tasks still
        pending completion will be interrupted, reporting TaskStatus.CRASHED.

        This kills the worker's whole process tree, not only the process
        launched directly; e.g. `pixi run` launches the actual worker process
        as its child.

        To shut down the service more gently, allowing any pending tasks to run to
        completion, use close() instead.

        To wait until the service's worker process has completely shut down
        and all output has been reported, call wait_for() afterward.

        Raises:
            RuntimeError: If the service has not been started.
        """
        self._require_process()
        process.kill_tree(self._process)

    def wait_for(self, timeout: float | None = None) -> int:
        """
        Wait for the service's worker process to terminate, and for all its
        output to be reported.

        Args:
            timeout: Maximum seconds to wait, or None to wait indefinitely.

        Returns:
            Exit code of the worker process.

        Raises:
            RuntimeError: If the service has not been started.
            subprocess.TimeoutExpired: If the timeout expires first.
        """
        self._require_process()
        deadline = None if timeout is None else time.monotonic() + timeout
        self._process.wait(timeout)
        if not self._join_threads(deadline):
            raise subprocess.TimeoutExpired(self._process.args, timeout)
        return self._process.returncode

    @property
    def returncode(self) -> int | None:
        """
        Exit code of the worker process, or None if it has not yet exited
        (or has not been started).
        """
        return None if self._process is None else self._process.poll()

    def is_alive(self) -> bool:
        """
        Return true if the service's worker process is currently running,
        or false if it has not yet started or has already shut down or crashed.

        Returns:
            Whether the service's worker process is currently running.
        """
        return self._process is not None and self._process.poll() is None

    def worker_info(self) -> Args | None:
        """
        Get the worker's self-description, from the HELLO message it sends
        upon startup: its "implementation" (e.g. "appose-python") and the
        "version" of Appose it implements. None if not yet received.
        """
        return self._worker_info

    def invalid_lines(self) -> list[str]:
        """
        Unparseable lines emitted by the worker process on its stdout stream,
        collected over the lifetime of the service.
        Can be useful for analyzing why a worker process has crashed.
        """
        return self._invalid_lines

    def error_lines(self) -> list[str]:
        """
        Lines emitted by the worker process on its stderr stream,
        collected over the lifetime of the service.
        Can be useful for analyzing why a worker process has crashed.
        """
        return self._error_lines

    def _stdout_loop(self) -> None:
        """
        Input loop processing lines from the worker's stdout stream.
        """
        while True:
            stdout = self._process.stdout
            # noinspection PyBroadException
            try:
                line = None if stdout is None else stdout.readline()
            except Exception:  # noqa: BLE001 -- reader thread must never die; log and stop instead
                # Something went wrong reading the stdout line. Panic!
                self._debug_service(format_exc())
                break

            if not line:  # readline returns empty string upon EOF
                self._debug_service("<worker stdout closed>")
                return

            # noinspection PyBroadException
            try:
                response = decode(line)
                self._debug_service(line)  # Echo the line to the debug listener.
                if response.get("responseType") == ResponseType.HELLO.value:
                    self._handle_hello(response)
                    continue
                if self._worker_info is None and self._incompatibility is None:
                    # NB: Workers predating the HELLO handshake begin with
                    # some other message, e.g. LAUNCH for the first task.
                    self._reject_worker(
                        "Worker did not identify itself, so it probably "
                        f"predates Appose {_minor(__version__)}; "
                        f"this service requires Appose {_minor(__version__)}.x."
                    )
                if self._incompatibility is not None:
                    continue
                if response.get("responseType") == ResponseType.CALL.value:
                    # The worker is calling back into a service object.
                    # Handle it on its own thread, so that this loop stays
                    # free to process other responses in the meantime.
                    threading.Thread(
                        target=self._handle_call,
                        args=(response,),
                        name=f"Appose-Service-{self._service_id}-Call",
                        daemon=True,
                    ).start()
                    continue
                uuid = response.get("task")
                if uuid is None:
                    self._debug_service(f"Invalid service message: {line}")
                    continue
                task = self._tasks.get(uuid)
                if task is None:
                    self._debug_service(f"No such task: {uuid}")
                    continue
                # noinspection PyProtectedMember
                task._handle(response)
            except Exception:  # noqa: BLE001 -- reader thread must never die; log and skip the bad line
                # Something went wrong decoding the line of JSON.
                # Skip it and keep going, but log it first.
                self._debug_service(f"<INVALID> {line}")
                self._invalid_lines.append(line.rstrip("\n\r"))

    def _stderr_loop(self) -> None:
        """
        Input loop processing lines from the worker's stderr stream.
        """
        while True:
            stderr = self._process.stderr
            # noinspection PyBroadException
            try:
                line = None if stderr is None else stderr.readline()
            except Exception:  # noqa: BLE001 -- reader thread must never die; log and stop instead
                # Something went wrong reading the stderr line. Panic!
                self._debug_service(format_exc())
                break
            if not line:  # readline returns empty string upon EOF
                self._debug_service("<worker stderr closed>")
                break
            self._debug_worker(line)
            self._error_lines.append(line.rstrip("\n\r"))

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
        if task_count == 0:
            # No hanging tasks to clean up.
            return

        self._debug_service(
            "<worker process terminated with "
            + f"{task_count} pending task{'' if task_count == 1 else 's'}>"
        )

        # Notify any remaining tasks about the process crash.
        nl = os.linesep
        error_parts = []
        if self._incompatibility is not None:
            error_parts.extend([self._incompatibility, ""])
        error_parts.append(f"Worker crashed with exit code {exit_code}.")
        error_parts.append("")
        error_parts.append("[stdout]")
        if len(self._invalid_lines) == 0:
            error_parts.append("<none>")
        else:
            error_parts.extend(self._invalid_lines)
        error_parts.append("")
        error_parts.append("[stderr]")
        if len(self._error_lines) == 0:
            error_parts.append("<none>")
        else:
            error_parts.extend(self._error_lines)
        error = nl.join(error_parts) + nl
        for task in self._tasks.values():
            task._crash(error)
        self._tasks.clear()

    def _handle_hello(self, hello: Args) -> None:
        """
        Check that the worker is compatible with this service: both must
        implement the same major.minor version of Appose.
        """
        self._worker_info = hello
        worker_version = str(hello.get("version"))
        if _minor(worker_version) == _minor(__version__):
            return
        implementation = hello.get("implementation", "worker")
        self._reject_worker(
            f"{implementation} {worker_version} is incompatible with "
            f"appose-python {__version__}: the worker must also implement "
            f"Appose {_minor(__version__)}.x."
        )

    def _reject_worker(self, reason: str) -> None:
        """
        Shut down an incompatible worker, crashing its tasks with the reason.
        """
        if os.environ.get("APPOSE_SKIP_VERSION_CHECK"):
            self._debug_service(f"<ignoring incompatible worker> {reason}")
            return
        self._incompatibility = (
            reason + " Set APPOSE_SKIP_VERSION_CHECK=1 to skip this check."
        )
        self._debug_service(f"<incompatible worker> {self._incompatibility}")
        process.kill_tree(self._process)

    def _export(self, obj: Any) -> Args:
        """
        Export a non-JSON-serializable object, so that the worker
        can access it remotely via a ServiceProxy.

        Returns:
            A service_object reference to the exported object.
        """
        with self._exports_lock:
            var_name = f"_appose_service_{self._export_count}"
            self._export_count += 1
            self._exports[var_name] = obj
        return {"appose_type": "service_object", "var_name": var_name}

    def _send(self, request: Args) -> None:
        """
        Send a request to the worker process.
        """
        encoded = encode(request, self._export)
        # NB: Requests may be sent from multiple threads, and must not interleave.
        with self._stdin_lock:
            # NB: Flush is necessary to ensure worker receives the data!
            print(encoded, file=self._process.stdin, flush=True)
        self._debug_service(encoded)

    def _handle_call(self, request: Args) -> None:
        """
        Perform an operation requested by the worker on an exported service
        object, then send the outcome back to the worker as a REPLY.
        """
        reply: Args = {
            "requestType": RequestType.REPLY.value,
            "call": request.get("call"),
        }
        # noinspection PyBroadException
        try:
            obj = self._exports[request.get("var")]
            op = request.get("op")
            if op == "get":
                result = getattr(obj, request.get("name"))
            elif op == "call":
                args = proxify_worker_objects(request.get("args") or [], self)
                result = obj(*args)
            elif op == "dir":
                result = dir(obj)
            else:
                raise ValueError(f"Invalid call operation: {op}")
            reply["result"] = result
            self._send(reply)
        except Exception:  # noqa: BLE001 -- any failure must be reported back to the waiting worker
            reply.pop("result", None)
            reply["error"] = format_exc()
            try:
                self._send(reply)
            except Exception:  # noqa: BLE001 -- the worker is unreachable; nothing more to do
                self._debug_service(format_exc())

    def _require_process(self) -> None:
        if self._process is None:
            raise RuntimeError("Service has not been started")

    def _join_threads(self, deadline: float | None) -> bool:
        """
        Wait for the worker output processing threads to finish up.

        Args:
            deadline: time.monotonic() value by which to give up,
                or None to wait indefinitely.

        Returns:
            Whether all the threads finished.
        """
        threads = (self._stdout_thread, self._stderr_thread, self._monitor_thread)
        for thread in threads:
            thread.join(
                None if deadline is None else max(0, deadline - time.monotonic())
            )
        return not any(thread.is_alive() for thread in threads)

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

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.close()


_started_services: weakref.WeakSet[Service] = weakref.WeakSet()
_started_services_lock = threading.Lock()
_exit_hook_registered = False


def _track(service: Service) -> None:
    """
    Remember a started service, so that it can be shut down at program exit.
    """
    global _exit_hook_registered
    with _started_services_lock:
        if not _exit_hook_registered:
            # NB: Registering upon first start, rather than at import, means
            # atexit hooks registered after starting a service, e.g. to close
            # it, still run before this one; atexit runs hooks in reverse.
            atexit.register(_shut_down_services)
            _exit_hook_registered = True
        _started_services.add(service)


def _shut_down_services() -> None:
    """
    Shut down all services still running, giving each worker up to its
    service's exit_timeout to exit gracefully before killing it.
    """
    with _started_services_lock:
        services = [s for s in _started_services if s.is_alive()]
    # Close every service first, so that their timeouts elapse concurrently.
    start = time.monotonic()
    for service in services:
        try:
            service.close()
        except Exception:  # noqa: BLE001 -- must still shut down the others
            service._debug_service(format_exc())
    for service in services:
        timeout = service.exit_timeout
        if timeout is not None:
            timeout = max(0, start + timeout - time.monotonic())
        try:
            service.close(timeout)
        except Exception:  # noqa: BLE001 -- must still shut down the others
            service._debug_service(format_exc())


def _minor(version: str) -> str | None:
    """
    Extract the major.minor part of a version string, e.g. "1.1" from
    "1.1.2", "1.1.0.dev0" or "1.1.3-SNAPSHOT"; or None if unparseable.
    """
    m = re.match(r"(\d+)\.(\d+)", version)
    return None if m is None else f"{m.group(1)}.{m.group(2)}"


class TaskStatus(Enum):
    INITIAL = "INITIAL"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    CANCELED = "CANCELED"
    FAILED = "FAILED"
    CRASHED = "CRASHED"

    def is_finished(self) -> bool:
        """
        True iff status is COMPLETE, CANCELED, FAILED, or CRASHED.
        """
        return self == TaskStatus.COMPLETE or self.is_error()

    def is_error(self) -> bool:
        """
        True iff status is CANCELED, FAILED, or CRASHED.
        """
        return self in (
            TaskStatus.CANCELED,
            TaskStatus.FAILED,
            TaskStatus.CRASHED,
        )


class RequestType(Enum):
    EXECUTE = "EXECUTE"
    REPLY = "REPLY"
    CANCEL = "CANCEL"


class ResponseType(Enum):
    HELLO = "HELLO"
    LAUNCH = "LAUNCH"
    UPDATE = "UPDATE"
    CALL = "CALL"
    COMPLETION = "COMPLETION"
    CANCELATION = "CANCELATION"
    FAILURE = "FAILURE"
    CRASH = "CRASH"

    """
    True iff response type is COMPLETE, CANCELED, FAILED, or CRASHED.
    """

    def is_terminal(self) -> bool:
        return self in (
            ResponseType.COMPLETION,
            ResponseType.CANCELATION,
            ResponseType.FAILURE,
            ResponseType.CRASH,
        )


class TaskEvent:
    def __init__(
        self,
        task: Task,
        response_type: ResponseType,
        message: str | None = None,
        current: int | None = None,
        maximum: int | None = None,
        info: Args | None = None,
    ) -> None:
        self.task: Task = task
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
        self.error: str | None = None
        self.listeners: list[Callable[[TaskEvent], None]] = []
        self.cv: threading.Condition = threading.Condition()
        self.service._tasks[self.uuid] = self

    def start(self) -> Task:
        with self.cv:
            if self.status != TaskStatus.INITIAL:
                raise RuntimeError("Task is not in the INITIAL state")

            self.status = TaskStatus.QUEUED

        if self.service._incompatibility is not None:
            self.service._tasks.pop(self.uuid, None)
            self._crash(self.service._incompatibility)
            return self
        args = {"script": self.script, "inputs": self.inputs, "queue": self.queue}
        self._request(RequestType.EXECUTE, args)

        return self

    def listen(self, listener: Callable[[TaskEvent], None]) -> Task:
        """
        Register a callback function to be notified of updates to the task.

        Returns:
            This task, for chaining method calls.
        """
        with self.cv:
            if self.status != TaskStatus.INITIAL:
                raise RuntimeError("Task is not in the INITIAL state")

            self.listeners.append(listener)
        return self

    def wait_for(self) -> Task:
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
        Return the result of this task.

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
        self.service._send(request)

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
                # Convert any worker_object references to ProxyObject instances.
                proxified_outputs = proxify_worker_objects(outputs, self.service)
                self.outputs.update(proxified_outputs)
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

    def _crash(self, error: str):
        event = TaskEvent(self, ResponseType.CRASH)
        self.status = TaskStatus.CRASHED
        self.error = error
        for listener in self.listeners:
            listener(event)
        with self.cv:
            self.cv.notify_all()

    def __str__(self):
        return f"{self.uuid=}, {self.status=}, {self.error=}"
