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
Utility functions for creating local proxy objects that provide strongly typed
access to remote objects living in Appose worker processes.

A proxy object forwards method calls to a corresponding object in the worker
process by generating and executing scripts via Tasks. This provides a more
natural, object-oriented API compared to manually constructing script strings
for each method invocation.

Type safety is honor-system based: The interface you provide must match the
actual methods and signatures of the remote object. If there's a mismatch,
you'll get runtime errors from the worker process.

Usage pattern: First, create and export the remote object via a task,
then create a proxy to interact with it:

    service = env.python()
    service.task("task.export(my_obj=MyClass())").wait_for()
    proxy = service.proxy("my_obj", MyInterface)
    result = proxy.some_method(42)  # Executes remotely

Important: Variables must be explicitly exported using task.export(varName=value)
in a previous task before they can be proxied. Exported variables persist across
tasks within the same service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..service import Service


def create(service: Service, var: str, queue: str | None = None) -> Any:
    """
    Creates a proxy object providing typed access to a remote object in a worker process.

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
    from ..syntax import Syntaxes

    class ProxyHandler:
        def __init__(self, service: Service, var: str, queue: str | None):
            self._service = service
            self._var = var
            self._queue = queue

        def __getattr__(self, name: str):
            def method(*args):
                # Construct map of input arguments.
                inputs = {}
                arg_names = []
                for i, arg in enumerate(args):
                    arg_name = f"arg{i}"
                    inputs[arg_name] = arg
                    arg_names.append(arg_name)

                # Use the service's ScriptSyntax to generate the method invocation script.
                # This allows support for different languages with varying syntax.
                Syntaxes.validate(self._service)
                script = self._service.syntax().invoke_method(
                    self._var, name, arg_names
                )

                try:
                    task = self._service.task(script, inputs, self._queue)
                    task.wait_for()
                    return task.result()
                except Exception as e:
                    raise RuntimeError(str(e)) from e

            return method

    return ProxyHandler(service, var, queue)  # type: ignore
