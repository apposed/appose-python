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
Script syntax generation for different languages.

This module provides classes for generating language-specific script syntax.
Different scripting languages have different syntax for common operations
like exporting variables, calling functions, and invoking methods on objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .service import Service


class ScriptSyntax(ABC):
    """
    Strategy base class for generating language-specific script syntax.

    Different scripting languages have different syntax for common operations
    like exporting variables, calling functions, and invoking methods on objects.
    This interface allows Service to generate correct scripts for any
    supported language.
    """

    @abstractmethod
    def name(self) -> str:
        """
        The name of this script syntax (e.g. "python", "groovy").
        """
        ...

    @abstractmethod
    def get_var(self, name: str) -> str:
        """
        Generates a script expression to retrieve a variable's value.

        The variable must have been previously exported using task.export()
        to be accessible across tasks.

        Args:
            name: The name of the variable to retrieve.

        Returns:
            A script expression that evaluates to the variable's value.
        """
        ...

    @abstractmethod
    def put_var(self, name: str, value_var_name: str) -> str:
        """
        Generates a script to set a variable and export it for future tasks.

        The value is provided via a task input variable (typically named "_value").
        The generated script should assign the value to the named variable and
        export it using task.export().

        Args:
            name: The name of the variable to set.
            value_var_name: The name of the input variable containing the value.

        Returns:
            A script that sets and exports the variable.
        """
        ...

    @abstractmethod
    def call(self, function: str, arg_var_names: list[str]) -> str:
        """
        Generates a script expression to call a function with arguments.

        The function must be accessible in the worker's global scope (either
        built-in or previously defined/imported). Arguments are provided via
        task input variables.

        Args:
            function: The name of the function to call.
            arg_var_names: The names of input variables containing the arguments.

        Returns:
            A script expression that calls the function and evaluates to its result.
        """
        ...

    @abstractmethod
    def invoke_method(
        self, object_var_name: str, method_name: str, arg_var_names: list[str]
    ) -> str:
        """
        Generates a script expression to invoke a method on an object.

        The object must have been previously exported using task.export().
        This is used by the proxy mechanism to forward method calls to remote objects.

        Args:
            object_var_name: The name of the variable referencing the object.
            method_name: The name of the method to invoke.
            arg_var_names: The names of input variables containing the arguments.

        Returns:
            A script expression that invokes the method and evaluates to its result.
        """
        ...


class PythonSyntax(ScriptSyntax):
    """
    Python-specific script syntax implementation.

    Generates Python code for common operations like variable export,
    function calls, and method invocation. This is automatically used
    when creating Python services via Environment.python().
    """

    def name(self) -> str:
        return "python"

    def get_var(self, name: str) -> str:
        # In Python, just reference the variable name.
        return name

    def put_var(self, name: str, value_var_name: str) -> str:
        # Assign the value and export using Python keyword argument syntax.
        return f"{name} = {value_var_name}\ntask.export({name}={name})"

    def call(self, function: str, arg_var_names: list[str]) -> str:
        # Python function call syntax: function(arg0, arg1, ...)
        return f"{function}({', '.join(arg_var_names)})"

    def invoke_method(
        self, object_var_name: str, method_name: str, arg_var_names: list[str]
    ) -> str:
        # Python method invocation: object.method(arg0, arg1, ...)
        return f"{object_var_name}.{method_name}({', '.join(arg_var_names)})"


class GroovySyntax(ScriptSyntax):
    """
    Groovy-specific script syntax implementation.

    Generates Groovy code for common operations like variable export,
    function calls, and method invocation. This is automatically used
    when creating Groovy services via Environment.groovy().
    """

    def name(self) -> str:
        return "groovy"

    def get_var(self, name: str) -> str:
        # In Groovy, just reference the variable name.
        return name

    def put_var(self, name: str, value_var_name: str) -> str:
        # Assign the value and export using Groovy map syntax.
        # Using explicit map literal [name: value] which is then passed to export(Map).
        return f"{name} = {value_var_name}\ntask.export([{name}: {name}])"

    def call(self, function: str, arg_var_names: list[str]) -> str:
        # Groovy function call syntax: function(arg0, arg1, ...)
        return f"{function}({', '.join(arg_var_names)})"

    def invoke_method(
        self, object_var_name: str, method_name: str, arg_var_names: list[str]
    ) -> str:
        # Groovy method invocation: object.method(arg0, arg1, ...)
        return f"{object_var_name}.{method_name}({', '.join(arg_var_names)})"


# All known script syntax implementations.
_SYNTAXES: list[ScriptSyntax] = [
    PythonSyntax(),
    GroovySyntax(),
]


def get(name: str) -> ScriptSyntax | None:
    """
    Detects and returns the script syntax with the given name.

    Args:
        name: Name of the script syntax

    Returns:
        The matching script syntax object, or None if no syntax with the given name
    """
    for syntax in _SYNTAXES:
        if syntax.name() == name:
            return syntax
    return None


def validate(service: Service) -> None:
    """
    Verifies that the given service has an assigned script syntax.

    Args:
        service: The service to ensure valid script syntax assignment

    Raises:
        ValueError: If no script syntax is configured
    """
    if service._syntax is None:
        raise ValueError("No script syntax configured for this service")
