# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end tests for UvBuilder."""

import json
from pathlib import Path

import pytest

import appose
from appose.builder import EnvStatus
from appose.builder.uv import UvBuilder
from tests.test_base import cowsay_and_assert

# Get the path to test resources
TEST_RESOURCES: Path = Path(__file__).parent.parent / "resources" / "envs"


def test_uv():
    """Tests building from a requirements.txt file."""
    env = (
        appose.uv()
        .file(str(TEST_RESOURCES / "cowsay-requirements.txt"))
        .base("target/envs/uv-cowsay")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "uv")


@pytest.mark.version_check
def test_uv_builder_api():
    """Tests the programmatic builder API for uv."""
    env = (
        appose.uv()
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
        appose.uv()
        .file(str(TEST_RESOURCES / "cowsay-pyproject.toml"))
        .base("target/envs/uv-cowsay-pyproject")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "pyproject")

    # No groups were requested, so none should be recorded.
    state = _read_state(env)
    assert "groups" not in state, (
        "appose.json should not contain 'groups' when none specified"
    )


def test_uv_pyproject_with_group():
    """Tests building from a pyproject.toml file with a dependency group."""
    env = (
        appose.uv()
        .file(str(TEST_RESOURCES / "cowsay-pyproject-groups.toml"))
        .group("cowsay")
        .base("target/envs/uv-cowsay-groups")
        .log_debug()
        .build()
    )
    cowsay_and_assert(env, "groups")

    state = _read_state(env)
    assert state["groups"] == ["cowsay"]

    # Wrapping (e.g. after an application restart) must retain the groups,
    # rather than treating the environment as stale and syncing without them.
    wrapped = appose.wrap(env.base())
    assert isinstance(wrapped.builder(), UvBuilder)
    assert wrapped.builder().status() == EnvStatus.CURRENT
    cowsay_and_assert(wrapped, "wrapped")

    # Rebuilding the wrapped environment must retain the groups too.
    rebuilt = wrapped.rebuild()
    cowsay_and_assert(rebuilt, "rebuilt")
    assert _read_state(rebuilt)["groups"] == ["cowsay"]


def test_uv_group_rejects_without_pyproject():
    """Tests that dependency groups require the pyproject.toml scheme."""
    with pytest.raises(ValueError):
        (
            appose.uv()
            .content("appose\n")
            .group("cowsay")
            .base("target/envs/uv-group-no-pyproject")
            .build()
        )


def _read_state(env) -> dict:
    appose_json = Path(env.base()) / "appose.json"
    assert appose_json.is_file(), "appose.json should exist"
    return json.loads(appose_json.read_text(encoding="utf-8"))
