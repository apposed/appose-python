# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end tests for UvBuilder."""

import json
from pathlib import Path

import pytest

import appose
from appose.builder import BuildException, EnvStatus
from appose.builder.uv import UvBuilder
from appose.util.filepath import delete_recursively
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


# -- Lock-file reproducible builds --


def test_uv_locked():
    """
    A user-supplied lock is copied into the env dir and the install runs with
    --locked, yielding a working environment. Exercises both lock_file()
    and lock_url().
    """
    # First, build without a lock to generate a valid uv.lock for the manifest.
    base_a = Path("target/envs/uv-lock-src")
    _build_unlocked(base_a)
    lock_file_a = base_a / "uv.lock"
    assert lock_file_a.is_file(), "first build should generate a uv.lock"

    # lock_file(): lock copied in, install runs --locked.
    base_b = Path("target/envs/uv-lock-file")
    delete_recursively(base_b)
    env_b = (
        appose.uv(TEST_RESOURCES / "cowsay-pyproject.toml")
        .base(base_b)
        .lock_file(lock_file_a)
        .log_debug()
        .build()
    )
    assert (base_b / "uv.lock").is_file(), "lock should be copied into the env dir"
    assert "lockHash" in _read_state(env_b)
    cowsay_and_assert(env_b, "locked")

    # lock_url(): same outcome via a file:// URL.
    base_c = Path("target/envs/uv-lock-url")
    delete_recursively(base_c)
    env_c = (
        appose.uv(TEST_RESOURCES / "cowsay-pyproject.toml")
        .base(base_c)
        .lock_url(lock_file_a.absolute().as_uri())
        .log_debug()
        .build()
    )
    assert "lockHash" in _read_state(env_c)
    cowsay_and_assert(env_c, "url-lock")


def test_uv_lock_stale_fails():
    """
    A lock that is out of date with the manifest must be rejected by
    --locked. (Without --locked, uv would update the lock and succeed.)
    """
    # A valid lock for the cowsay manifest...
    base_a = Path("target/envs/uv-stale-src")
    _build_unlocked(base_a)
    cowsay_lock = (base_a / "uv.lock").read_text(encoding="utf-8")

    # ...is stale for the same project additionally requiring `requests`.
    pyproject_extra = (
        (TEST_RESOURCES / "cowsay-pyproject.toml")
        .read_text(encoding="utf-8")
        .replace('"appose>=0.1.0",', '"appose>=0.1.0",\n    "requests",')
    )
    assert "requests" in pyproject_extra
    base = Path("target/envs/uv-lock-stale")
    delete_recursively(base)
    with pytest.raises(BuildException):
        (
            appose.uv()
            .content(pyproject_extra)
            .base(base)
            .lock_content(cowsay_lock)
            .log_debug()
            .build()
        )


def test_uv_no_lock_backward_compat():
    """
    When no lock is supplied, appose.json must not contain a lockHash key,
    so existing environments are never spuriously rebuilt.
    """
    env = _build_unlocked(Path("target/envs/uv-no-lock"))
    assert "lockHash" not in _read_state(env)
    cowsay_and_assert(env, "nolock")


def test_uv_lock_change_triggers_rebuild():
    """
    Changing the lock content must change the lockHash in appose.json and
    thus force a rebuild. The lock is edited with a trailing TOML comment,
    which doesn't change the resolved package set, so --locked still succeeds.
    """
    base_a = Path("target/envs/uv-lock-change-src")
    _build_unlocked(base_a)
    lock = (base_a / "uv.lock").read_text(encoding="utf-8")

    base = Path("target/envs/uv-lock-change")
    delete_recursively(base)
    env = (
        appose.uv(TEST_RESOURCES / "cowsay-pyproject.toml")
        .base(base)
        .lock_content(lock)
        .log_debug()
        .build()
    )
    hash_before = _read_state(env)["lockHash"]

    env = (
        appose.uv(TEST_RESOURCES / "cowsay-pyproject.toml")
        .base(base)
        .lock_content(lock + "# trailing comment\n")
        .log_debug()
        .build()
    )
    hash_after = _read_state(env)["lockHash"]
    assert hash_before != hash_after


def test_uv_wrap_lock_survives_rebuild():
    """
    wrap() captures the lock file into builder state, so rebuild() reproduces
    the locked environment even after its directory has been deleted.
    """
    src_base = Path("target/envs/uv-wrap-src")
    _build_unlocked(src_base)
    lock = (src_base / "uv.lock").read_text(encoding="utf-8")

    base = Path("target/envs/uv-wrap-locked")
    delete_recursively(base)
    (
        appose.uv(TEST_RESOURCES / "cowsay-pyproject.toml")
        .base(base)
        .lock_content(lock)
        .log_debug()
        .build()
    )

    # Wrap the locked env (capturing pyproject.toml + uv.lock), then wipe + rebuild.
    env = appose.wrap(base)
    assert isinstance(env.builder(), UvBuilder)
    assert env.builder().status() == EnvStatus.CURRENT
    rebuilt = env.rebuild()
    assert "lockHash" in _read_state(rebuilt), (
        "rebuild after wrap must reproduce lockHash from the captured lock"
    )
    cowsay_and_assert(rebuilt, "rewrapped")


def test_uv_wrap_ignores_unrequested_lock():
    """
    uv sync writes a uv.lock even when no lock is supplied. Wrapping such an
    environment must not adopt that lock, or the env would look stale, and
    rebuild() would install from a lock the caller never asked for.
    """
    base = Path("target/envs/uv-wrap-unlocked")
    _build_unlocked(base)
    assert (base / "uv.lock").is_file(), "uv sync should generate a uv.lock"

    env = appose.wrap(base)
    assert env.builder().status() == EnvStatus.CURRENT
    rebuilt = env.rebuild()
    assert "lockHash" not in _read_state(rebuilt), (
        "rebuild after wrap must not lock to the generated uv.lock"
    )
    cowsay_and_assert(rebuilt, "unlocked")


def _build_unlocked(base: Path):
    """Build the cowsay environment from scratch, without a lock."""
    delete_recursively(base)
    return (
        appose.uv(TEST_RESOURCES / "cowsay-pyproject.toml")
        .base(base)
        .log_debug()
        .build()
    )
