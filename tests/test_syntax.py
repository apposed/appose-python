# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for Service functions related to ScriptSyntax."""

from __future__ import annotations

import pytest
from typing import Protocol

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


class Creature(Protocol):
    """Test protocol for proxy testing."""

    def walk(self, speed: int) -> str: ...
    def fly(self, speed: int, height: int) -> bool: ...
    def dive(self, depth: float) -> str: ...


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
        bird = service.proxy("bird", Creature)
        assert bird.walk(1) == "Hopped at rate: 1"
        assert bird.walk(2) == "Too fast for birds!"
        assert bird.fly(5, 100) is True
        assert (
            bird.dive(2) == "Dove down 2 deep" or bird.dive(2) == "Dove down 2.0 deep"
        )
        assert bird.dive(3) == "Too deep for birds!"

        # Validate fish behavior
        fish = service.proxy("fish", Creature)
        assert fish.walk(1) == "Nope! Only the Darwin fish can do that."
        assert fish.fly(2, 4) is True
        assert fish.fly(2, 10) is False
        assert (
            fish.dive(100) == "Swam down 100 deep"
            or fish.dive(100) == "Swam down 100.0 deep"
        )
