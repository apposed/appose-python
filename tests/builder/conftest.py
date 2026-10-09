# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


"""Shared fixtures for builder tests."""

import pytest


@pytest.fixture(autouse=True)
def skip_version_check(request, monkeypatch):
    """
    Skip the worker version check: most of these tests build environments from
    user-style files containing a released appose, from conda-forge or PyPI,
    which need not match the version of appose under test. They test
    environment building, not compatibility.

    Tests marked version_check, whose builders add a compatible appose
    themselves, enforce the check as usual.
    """
    if request.node.get_closest_marker("version_check") is None:
        monkeypatch.setenv("APPOSE_SKIP_VERSION_CHECK", "1")
