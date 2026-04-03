# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


import appose

from tests.test_base import source_override


def _numpy_env():
    return (
        appose.uv()
        .include("numpy")
        .env(**source_override())
        .base("target/envs/pyworker-numpy")
        .log_debug()
        .build()
    )


def test_numpy_warning():
    """Tests that a warning is issued when numpy is installed but not imported via init."""
    env = _numpy_env()
    with env.python() as service:
        error_lines = service.error_lines()
    assert any("[WARNING]" in line and "numpy" in line for line in error_lines)


def test_numpy_no_warning():
    """Tests that no warning is issued when numpy is imported via the init script."""
    env = _numpy_env()
    with env.python().init("import numpy") as service:
        error_lines = service.error_lines()
    assert not any("[WARNING]" in line and "numpy" in line for line in error_lines)


def test_no_warnings():
    """Tests that no warning is issued in numpy-free environments."""
    env = appose.system()
    with env.python() as service:
        error_lines = service.error_lines()
    assert not any("[WARNING]" in line for line in error_lines)
