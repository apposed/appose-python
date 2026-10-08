# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


"""Shared fixtures for builder tests."""

import pytest


@pytest.fixture(autouse=True)
def skip_version_check(monkeypatch):
    """
    Skip the worker version check: these tests build environments containing a
    released appose, from conda-forge or PyPI, which need not match the version
    of appose under test. They test environment building, not compatibility.
    """
    monkeypatch.setenv("APPOSE_SKIP_VERSION_CHECK", "1")
