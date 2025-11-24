# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for TaskException behavior."""

from __future__ import annotations

import pytest

import appose
from appose import TaskException
from appose.service import TaskStatus
from tests.test_base import maybe_debug


def test_task_exception_on_failure():
    """
    Test that wait_for() raises TaskException on script failure,
    and that the exception provides access to the task details.
    """
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Create a task with a syntax error that will fail
        task = service.task("undefined_variable")

        with pytest.raises(TaskException) as exc_info:
            task.wait_for()

        # Verify exception contains useful information
        e = exc_info.value
        assert "failed" in str(e).lower()
        assert "NameError" in str(e) or "nameerror" in str(e).lower()

        # Verify we can access the task and its details through the exception
        assert e.task is task
        assert e.task.status == TaskStatus.FAILED
        assert e.task.error is not None
        assert "NameError" in e.task.error or "nameerror" in e.task.error.lower()


def test_no_exception_on_success():
    """
    Test that wait_for() returns normally on success and
    outputs can be accessed without checking status.
    """
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)

        # Create a task that will succeed
        task = service.task("2 + 2").wait_for()

        # No exception thrown - we can directly access the result
        result = task.outputs.get("result")
        assert result == 4
        assert task.status == TaskStatus.COMPLETE
