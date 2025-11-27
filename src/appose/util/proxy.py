# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions for creating local proxy objects that provide access to
remote objects living in Appose worker processes.

A proxy object forwards attribute accesses and method calls to a corresponding
object in the worker process by generating and executing scripts via Tasks.
This provides a natural, object-oriented API compared to manually constructing
script strings for each operation.

Proxy objects support:
- Attribute access: proxy.field returns the field value (or another proxy)
- Method calls: proxy.method(args) invokes the method remotely
- Chaining: proxy.obj.method(args) works naturally
- Callables: proxy() invokes the proxied object if it's callable

Usage pattern: First, create and export the remote object via a task,
then create a proxy to interact with it:

    service = env.python()
    service.task("task.export(my_obj=MyClass())").wait_for()
    proxy = service.proxy("my_obj")
    result = proxy.some_method(42)  # Executes remotely

Automatic proxying: When a task returns a non-JSON-serializable object, it's
automatically exported and returned as a proxy object:

    counter = service.task("import collections; collections.Counter('abbc')").wait_for().result()
    # counter is now a ProxyObject wrapping the remote Counter
    total = counter.total()  # Access the total method and call it

Important: Variables must be explicitly exported using task.export(varName=value)
in a previous task before they can be proxied. Exported variables persist across
tasks within the same service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import syntax

if TYPE_CHECKING:
    from ..service import Service


def create(service: Service, var: str, queue: str | None = None) -> Any:
    """
    Create a proxy object providing typed access to a remote object in a worker process.

    Each method invocation on the returned proxy generates a script of the form
    var.methodName(arg0, arg1, ...) and submits it as a task to the worker.
    Arguments are provided via the task's inputs map, and the return value
    is retrieved from task.result().

    Variable export requirement: The variable must have been previously
    exported using task.export(varName=value) in a prior task. Only exported
    variables are accessible across tasks. For example:

        service.task("task.export(calc=Calculator())").wait_for()
        calc = service.proxy("calc", Calculator)

    Blocking behavior: Method calls block the calling thread until
    the remote execution completes. If you need asynchronous execution, create tasks
    manually using service.task(script).

    Error handling: If the remote execution fails, a
    RuntimeError is thrown containing the error message from the worker.

    Args:
        service: The service managing the worker process containing the remote object.
        var: The name of the exported variable in the worker process referencing the remote object.
        api: The interface class that the proxy should implement. Method calls on this
            interface will be forwarded to the remote object.
        queue: Optional queue identifier for task execution. Pass "main" to ensure
            execution on the worker's main thread, or None for default behavior.

    Returns:
        A proxy object implementing the specified interface. Method calls block until
        the remote execution completes and return the value from task.result().

    Raises:
        RuntimeError: If a proxied method call fails in the worker process.
    """

    class ProxyObject:
        def __init__(self, service: Service, var: str, queue: str | None):
            self._service = service
            self._var = var
            self._queue = queue

        def __getattr__(self, name: str):
            # Use the service's ScriptSyntax to generate the attribute access script.
            # This allows language-specific handling (e.g., Groovy's field vs method).
            syntax.validate(self._service)
            script = self._service._syntax.get_attribute(self._var, name)

            try:
                task = self._service.task(script, queue=self._queue)
                task.wait_for()
                result = task.result()
                # If result is a worker_object, it will already be a ProxyObject
                # thanks to proxify_worker_objects() in Task._handle().
                return result
            except Exception as e:
                raise RuntimeError(str(e)) from e

        def __call__(self, *args):
            # Invoke the proxied object as a callable.
            # Construct map of input arguments.
            inputs = {}
            arg_names = []
            for i, arg in enumerate(args):
                arg_name = f"arg{i}"
                inputs[arg_name] = arg
                arg_names.append(arg_name)

            # Use the service's ScriptSyntax to generate the call script.
            syntax.validate(self._service)
            script = self._service._syntax.call(self._var, arg_names)

            try:
                task = self._service.task(script, inputs, self._queue)
                task.wait_for()
                return task.result()
            except Exception as e:
                raise RuntimeError(str(e)) from e

        def __dir__(self):
            # Query the remote object for its attributes via introspection.
            syntax.validate(self._service)
            script = self._service._syntax.get_attributes(self._var)

            try:
                task = self._service.task(script, queue=self._queue)
                task.wait_for()
                return task.result()
            except Exception as e:
                raise RuntimeError(str(e)) from e

    return ProxyObject(service, var, queue)  # type: ignore
