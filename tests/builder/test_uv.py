# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end tests for UvBuilder."""

from pathlib import Path


from appose.builder.uv import UvBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES: Path = Path(__file__).parent.parent / "resources" / "envs"


def test_uv():
    """Tests building from a requirements.txt file."""
    env = (
        UvBuilder()
        .file(str(TEST_RESOURCES / "cowsay-requirements.txt"))
        .base("target/envs/uv-cowsay")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "uv")


def test_uv_builder_api():
    """Tests the programmatic builder API for uv."""
    env = (
        UvBuilder()
        .include("cowsay==6.1")
        .base("target/envs/uv-cowsay-builder")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "fast")


def test_uv_pyproject():
    """Tests building from a pyproject.toml file."""
    env = (
        UvBuilder()
        .file(str(TEST_RESOURCES / "cowsay-pyproject.toml"))
        .base("target/envs/uv-cowsay-pyproject")
        .log_debug()
        .build()
    )
    cowsay_and_assert(env, "pyproject")
