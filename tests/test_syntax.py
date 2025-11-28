# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for Service functions related to ScriptSyntax."""

from __future__ import annotations

import pytest

import appose
from appose import TaskException
from tests.test_base import assert_complete, maybe_debug


def test_get_var_python():
    """Test getting a variable from worker's global scope using Service.get_var."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Set up a variable in the worker using a task and export it
        service.task("test_var = 42\ntask.export(test_var=test_var)").wait_for()

        # Retrieve the variable using get_var
        result = service.get_var("test_var")
        assert isinstance(result, (int, float))
        assert result == 42


def test_get_var_failure():
    """
    Test that Service.get_var raises TaskException for non-existent variables.
    """
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        with pytest.raises(TaskException) as exc_info:
            service.get_var("nonexistent_variable")

        assert "failed" in str(exc_info.value).lower()


def test_put_var_python():
    """Test setting a variable in worker's global scope using Service.put_var."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Set a variable using put_var
        service.put_var("my_number", 123)

        # Verify the variable is accessible in subsequent tasks
        task = service.task("my_number * 2").wait_for()
        assert_complete(task)
        result = task.outputs.get("result")
        assert result == 246


def test_put_var_list():
    """Test that Service.put_var with a list works correctly."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Set a list using put_var
        values = [1, 2, 3, 4, 5]
        service.put_var("my_list", values)

        # Verify the list is accessible and can be manipulated
        task = service.task("sum(my_list)").wait_for()
        assert_complete(task)
        result = task.outputs.get("result")
        assert result == 15


def test_call_builtin_python():
    """Test calling a built-in function using Service.call."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Call Python's built-in max function
        result = service.call("max", 5, 10, 3, 8)
        assert isinstance(result, (int, float))
        assert result == 10


def test_call_custom_function_python():
    """Test calling a custom function using Service.call."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Define a custom function in the worker
        service.task(
            "def multiply(a, b):\n    return a * b\ntask.export(multiply=multiply)"
        ).wait_for()

        # Call the custom function
        result = service.call("multiply", 6, 7)
        assert isinstance(result, (int, float))
        assert result == 42


def test_call_nonexistent_function():
    """
    Test that Service.call raises TaskException when function doesn't exist.
    """
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        with pytest.raises(TaskException) as exc_info:
            service.call("nonexistent_function", 1, 2, 3)

        assert "failed" in str(exc_info.value).lower()


def test_proxy():
    """Test Service.proxy functionality."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Set up test classes in Python
        setup = service.task(
            """
class Bird:
    def fly(self, rate, altitude):
        return True

    def walk(self, rate):
        return "Too fast for birds!" if rate > 1 else f"Hopped at rate: {rate}"

    def dive(self, depth):
        return "Too deep for birds!" if depth > 2 else f"Dove down {depth} deep"

class Fish:
    def dive(self, depth):
        return f"Swam down {depth} deep"

    def fly(self, rate, altitude):
        return rate < 3 and altitude < 5

    def walk(self, rate):
        return "Nope! Only the Darwin fish can do that."

task.export(bird=Bird(), fish=Fish())
"""
        )
        setup.wait_for()
        assert_complete(setup)

        # Validate bird behavior
        bird = service.proxy("bird")
        assert bird.walk(1) == "Hopped at rate: 1"
        assert bird.walk(2) == "Too fast for birds!"
        assert bird.fly(5, 100) is True
        assert (
            bird.dive(2) == "Dove down 2 deep" or bird.dive(2) == "Dove down 2.0 deep"
        )
        assert bird.dive(3) == "Too deep for birds!"

        # Validate fish behavior
        fish = service.proxy("fish")
        assert fish.walk(1) == "Nope! Only the Darwin fish can do that."
        assert fish.fly(2, 4) is True
        assert fish.fly(2, 10) is False
        assert (
            fish.dive(100) == "Swam down 100 deep"
            or fish.dive(100) == "Swam down 100.0 deep"
        )


def test_auto_proxy():
    """Test automatic proxying of non-serializable task outputs."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Return a non-serializable object from a task - should auto-proxy
        # datetime is not JSON-serializable
        dt = (
            service.task("import datetime\ndatetime.datetime(2024, 1, 15, 10, 30, 45)")
            .wait_for()
            .result()
        )

        # dt should be a proxy object now
        assert dt is not None

        # Access attributes on the proxied datetime
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

        # Call a method
        iso_str = dt.isoformat()
        assert "2024-01-15T10:30:45" == iso_str

        # Access a field that returns a primitive type
        # Counter doesn't have simple fields, so let's create a custom class
        custom = (
            service.task("""
class CustomClass:
    def __init__(self):
        self.value = 42
        self.name = "test"

    def get_double(self):
        return self.value * 2

CustomClass()
""")
            .wait_for()
            .result()
        )

        # Access primitive fields
        assert custom.value == 42
        assert custom.name == "test"

        # Call a method
        assert custom.get_double() == 84

        # Test nested object access
        nested = (
            service.task("""
class Inner:
    def __init__(self):
        self.data = "inner_data"

    def process(self, x):
        return f"processed: {x}"

class Outer:
    def __init__(self):
        self.inner = Inner()
        self.label = "outer"

Outer()
""")
            .wait_for()
            .result()
        )

        # Access nested object
        assert nested.label == "outer"
        inner = nested.inner
        assert inner.data == "inner_data"
        assert inner.process("test") == "processed: test"

        # Or chain it all together
        result = nested.inner.process("chained")
        assert result == "processed: chained"


def test_callable_proxy():
    """Test that proxied callable objects work correctly."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Create a lambda function
        func = service.task("lambda x, y: x + y").wait_for().result()

        # Call it
        result = func(10, 32)
        assert result == 42

        # Create a custom callable class
        callable_obj = (
            service.task("""
class Adder:
    def __init__(self, offset):
        self.offset = offset

    def __call__(self, x):
        return x + self.offset

Adder(100)
""")
            .wait_for()
            .result()
        )

        # Call the callable object
        result = callable_obj(23)
        assert result == 123

        # Access a field on the callable object
        assert callable_obj.offset == 100


def test_proxy_dir():
    """Test that dir() works on proxy objects."""
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Create a custom class with known attributes
        obj = (
            service.task("""
class TestClass:
    def __init__(self):
        self.field1 = 42
        self.field2 = "hello"

    def method1(self):
        return "method1"

    def method2(self, x):
        return x * 2

TestClass()
""")
            .wait_for()
            .result()
        )

        # Get dir() output
        attrs = dir(obj)

        # Should be a list
        assert isinstance(attrs, list)

        # Should contain our custom attributes
        assert "field1" in attrs
        assert "field2" in attrs
        assert "method1" in attrs
        assert "method2" in attrs

        # Should also contain standard object attributes
        assert "__init__" in attrs
        assert "__class__" in attrs

        # Test with a built-in object (datetime)
        dt = (
            service.task("import datetime\ndatetime.datetime(2024, 1, 15)")
            .wait_for()
            .result()
        )
        dt_attrs = dir(dt)

        assert isinstance(dt_attrs, list)
        assert "year" in dt_attrs
        assert "month" in dt_attrs
        assert "day" in dt_attrs
        assert "isoformat" in dt_attrs
        assert "replace" in dt_attrs
