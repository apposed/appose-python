# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end tests for PixiBuilder."""

import json
import shutil
from pathlib import Path

import pytest

import appose
from appose.builder import BuildException, EnvStatus
from appose.builder.pixi import PixiBuilder
from appose.util.filepath import delete_recursively
from tests.test_base import cowsay_and_assert

# Get the path to test resources
TEST_RESOURCES: Path = Path(__file__).parent.parent / "resources" / "envs"


def test_conda():
    """Tests the builder-agnostic API with an environment.yml file."""
    env = (
        appose.file(str(TEST_RESOURCES / "cowsay.yml"))
        .base("target/envs/conda-cowsay")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "moo")


def test_pixi():
    """Tests building from a pixi.toml file."""
    env = (
        appose.pixi()
        .file(str(TEST_RESOURCES / "cowsay-pixi.toml"))
        .base("target/envs/pixi-cowsay")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "baa")


def test_pixi_inherited_shell_env():
    """
    Tests that a pixi environment launches correctly when the calling process
    is itself running inside an activated pixi environment of another project.
    """
    env = (
        appose.pixi()
        .file(str(TEST_RESOURCES / "cowsay-pixi.toml"))
        .base("target/envs/pixi-cowsay-shell")
        .env(PIXI_IN_SHELL="1", PIXI_ENVIRONMENT_NAME="nonexistent")
        .log_debug()
        .build()
    )
    assert env.launch_args()[-2:] == ["--environment", "default"]
    cowsay_and_assert(env, "baa")


def test_pixi_builder_api():
    """Tests the programmatic builder API for pixi."""
    env = (
        appose.pixi()
        .conda("python>=3.8", "appose")
        .pypi("cowsay==6.1")
        .base("target/envs/pixi-cowsay-builder")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "ooh")


def test_pixi_vacuous():
    """Tests that building without packages or config fails."""
    base = "target/envs/pixi-vacuous"
    if Path(base).exists():
        shutil.rmtree(base)

    with pytest.raises(BuildException):
        appose.pixi().base(base).log_debug().build()


def test_pixi_vacuous_keeps_existing_env():
    """Tests that building without packages or config uses an existing env as-is."""
    base = Path("target/envs/pixi-vacuous-existing")
    if base.exists():
        shutil.rmtree(base)
    marker = base / ".pixi" / "envs" / "default" / "conda-meta" / "history"
    marker.parent.mkdir(parents=True)
    marker.touch()

    # With nothing to build from, the existing env must be used as-is, not wiped.
    env = appose.pixi().base(base).log_debug().build()
    assert env.base() == str(base.absolute())
    assert marker.exists()


@pytest.mark.version_check
def test_pixi_appose_requirement():
    """Tests that building without appose adds a compatible appose."""
    base = Path("target/envs/pixi-appose-requirement")
    if base.exists():
        shutil.rmtree(base)

    env = (
        appose.pixi().conda("python").pypi("cowsay==6.1").base(base).log_debug().build()
    )
    assert "appose" in (base / "pixi.toml").read_text()
    cowsay_and_assert(env, "auto")


def test_pixi_pyproject():
    """Tests building from a pyproject.toml with pixi config."""
    env = (
        appose.pixi()
        .file(str(TEST_RESOURCES / "cowsay-pixi-pyproject.toml"))
        .base("target/envs/pixi-cowsay-pyproject")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "pixi-pyproject")


def test_content_api():
    """Tests building environment from content string using type-specific builder."""
    pixi_toml = """[workspace]
name = "content-test"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-64", "osx-arm64", "win-64"]

[dependencies]
python = ">=3.8"
appose = "*"

[pypi-dependencies]
cowsay = "==6.1"
"""

    env = (
        appose.pixi()
        .content(pixi_toml)
        .base("target/envs/pixi-content-test")
        .log_debug()
        .build()
    )

    cowsay_and_assert(env, "content!")


def test_content_environment_yml():
    """Tests auto-detecting builder from environment.yml content string."""
    env_yml = """name: content-env-yml
channels:
  - conda-forge
dependencies:
  - python>=3.8
  - appose
  - pip
  - pip:
    - cowsay==6.1
"""

    env = (
        appose.content(env_yml).base("target/envs/content-env-yml").log_debug().build()
    )

    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "yml!")


def test_build_installs_env():
    """
    Tests that PixiBuilder.build() fully installs the pixi environment,
    i.e. that .pixi/envs/default exists after build() returns,
    not only after the first pixi run invocation.
    """
    env = (
        appose.pixi()
        .file(str(TEST_RESOURCES / "cowsay-pixi.toml"))
        .base("target/envs/pixi-build-installs-env")
        .log_debug()
        .rebuild()
    )
    # The default pixi environment directory must exist right after build(),
    # before any service is launched.
    env_dir = Path(env.base()) / ".pixi" / "envs" / "default"
    assert env_dir.is_dir(), (
        f".pixi/envs/default should exist after build(), but was missing: {env_dir}"
    )
    cowsay_and_assert(env, "installed")


def test_pixi_activate():
    """Tests that env.activate() launches a service in a non-default pixi environment."""
    env = (
        appose.pixi()
        .file(str(TEST_RESOURCES / "cowsay-multi-env.toml"))
        .base("target/envs/pixi-multi-env")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    alt_env = env.activate("alt")
    # Verify launch args include --environment alt
    launch_args = alt_env.launch_args()
    assert "--environment" in launch_args, "launch_args should contain --environment"
    idx = launch_args.index("--environment")
    assert launch_args[idx + 1] == "alt"
    # Verify bin path resolves to the alt environment directory
    import os

    assert os.sep + "alt" + os.sep in alt_env.bin_paths()[0], (
        "bin_paths should reference the alt environment"
    )
    cowsay_and_assert(alt_env, "multi-env")


def test_content_pixi_toml():
    """Tests auto-detecting builder from pixi.toml content string."""
    pixi_toml = """[workspace]
name = "content-pixi-toml"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-64", "osx-arm64", "win-64"]

[dependencies]
python = ">=3.8"
appose = "*"

[pypi-dependencies]
cowsay = "==6.1"
"""

    env = (
        appose.content(pixi_toml)
        .base("target/envs/content-pixi-toml")
        .log_debug()
        .build()
    )

    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "toml!")


# -- Lock-file reproducible builds --


def test_pixi_locked():
    """
    A user-supplied lock is copied into the env dir and the install runs with
    --locked, yielding a working environment. Exercises both lock_file()
    and lock_url().
    """
    # First, build without a lock to generate a valid pixi.lock for the manifest.
    base_a = Path("target/envs/pixi-lock-src")
    _build_unlocked(base_a)
    lock_file_a = base_a / "pixi.lock"
    assert lock_file_a.is_file(), "first build should generate a pixi.lock"

    # lock_file(): lock copied in, install runs --locked.
    base_b = Path("target/envs/pixi-lock-file")
    delete_recursively(base_b)
    env_b = (
        appose.pixi(TEST_RESOURCES / "cowsay-pixi.toml")
        .base(base_b)
        .lock_file(lock_file_a)
        .log_debug()
        .build()
    )
    assert (base_b / "pixi.lock").is_file(), "lock should be copied into the env dir"
    assert "lockHash" in _read_state(env_b)
    cowsay_and_assert(env_b, "locked")

    # lock_url(): same outcome via a file:// URL.
    base_c = Path("target/envs/pixi-lock-url")
    delete_recursively(base_c)
    env_c = (
        appose.pixi(TEST_RESOURCES / "cowsay-pixi.toml")
        .base(base_c)
        .lock_url(lock_file_a.absolute().as_uri())
        .log_debug()
        .build()
    )
    assert "lockHash" in _read_state(env_c)
    cowsay_and_assert(env_c, "url-lock")


def test_pixi_lock_stale_fails():
    """
    A lock that is out of date with the manifest must be rejected by
    --locked. (Without --locked, pixi would update the lock and succeed.)
    """
    # A valid lock for the cowsay manifest...
    base_a = Path("target/envs/pixi-stale-src")
    _build_unlocked(base_a)
    cowsay_lock = (base_a / "pixi.lock").read_text(encoding="utf-8")

    # ...is stale for the same workspace additionally requiring `requests`.
    pixi_extra = (TEST_RESOURCES / "cowsay-pixi.toml").read_text(
        encoding="utf-8"
    ) + 'requests = "*"\n'
    base = Path("target/envs/pixi-lock-stale")
    delete_recursively(base)
    with pytest.raises(BuildException):
        (
            appose.pixi()
            .content(pixi_extra)
            .base(base)
            .lock_content(cowsay_lock)
            .log_debug()
            .build()
        )


def test_pixi_no_lock_backward_compat():
    """
    When no lock is supplied, appose.json must not contain a lockHash key,
    so existing environments are never spuriously rebuilt.
    """
    env = _build_unlocked(Path("target/envs/pixi-no-lock"))
    assert "lockHash" not in _read_state(env)
    cowsay_and_assert(env, "nolock")


def test_pixi_lock_change_triggers_rebuild():
    """
    Changing the lock content must change the lockHash in appose.json and
    thus force a rebuild. The lock is edited with a trailing comment, which
    doesn't change the resolved package set, so --locked still succeeds.
    """
    base_a = Path("target/envs/pixi-lock-change-src")
    _build_unlocked(base_a)
    lock = (base_a / "pixi.lock").read_text(encoding="utf-8")

    base = Path("target/envs/pixi-lock-change")
    delete_recursively(base)
    env = (
        appose.pixi(TEST_RESOURCES / "cowsay-pixi.toml")
        .base(base)
        .lock_content(lock)
        .log_debug()
        .build()
    )
    hash_before = _read_state(env)["lockHash"]

    env = (
        appose.pixi(TEST_RESOURCES / "cowsay-pixi.toml")
        .base(base)
        .lock_content(lock + "# trailing comment\n")
        .log_debug()
        .build()
    )
    hash_after = _read_state(env)["lockHash"]
    assert hash_before != hash_after


def test_pixi_wrap_lock_survives_rebuild():
    """
    wrap() captures the lock file into builder state, so rebuild() reproduces
    the locked environment even after its directory has been deleted.
    """
    src_base = Path("target/envs/pixi-wrap-src")
    _build_unlocked(src_base)
    lock = (src_base / "pixi.lock").read_text(encoding="utf-8")

    base = Path("target/envs/pixi-wrap-locked")
    delete_recursively(base)
    (
        appose.pixi(TEST_RESOURCES / "cowsay-pixi.toml")
        .base(base)
        .lock_content(lock)
        .log_debug()
        .build()
    )

    # Wrap the locked env (capturing pixi.toml + pixi.lock), then wipe + rebuild.
    env = appose.wrap(base)
    assert isinstance(env.builder(), PixiBuilder)
    assert env.builder().status() == EnvStatus.CURRENT
    rebuilt = env.rebuild()
    assert "lockHash" in _read_state(rebuilt), (
        "rebuild after wrap must reproduce lockHash from the captured lock"
    )
    cowsay_and_assert(rebuilt, "rewrapped")


def test_pixi_wrap_ignores_unrequested_lock():
    """
    pixi install writes a pixi.lock even when no lock is supplied. Wrapping
    such an environment must not adopt that lock, or the env would look
    stale, and rebuild() would install from a lock never asked for.
    """
    base = Path("target/envs/pixi-wrap-unlocked")
    _build_unlocked(base)
    assert (base / "pixi.lock").is_file(), "pixi install should generate a pixi.lock"

    env = appose.wrap(base)
    assert env.builder().status() == EnvStatus.CURRENT
    rebuilt = env.rebuild()
    assert "lockHash" not in _read_state(rebuilt), (
        "rebuild after wrap must not lock to the generated pixi.lock"
    )
    cowsay_and_assert(rebuilt, "unlocked")


def _read_state(env) -> dict:
    appose_json = Path(env.base()) / "appose.json"
    assert appose_json.is_file(), "appose.json should exist"
    return json.loads(appose_json.read_text(encoding="utf-8"))


def _build_unlocked(base: Path):
    """Build the cowsay environment from scratch, without a lock."""
    delete_recursively(base)
    return (
        appose.pixi(TEST_RESOURCES / "cowsay-pixi.toml").base(base).log_debug().build()
    )
