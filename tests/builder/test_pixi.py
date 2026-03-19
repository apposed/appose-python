# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end tests for PixiBuilder."""

import shutil
from pathlib import Path

import pytest

import appose
from appose.builder.pixi import PixiBuilder

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

    with pytest.raises(Exception):  # Should raise IllegalStateException equivalent
        appose.pixi().base(base).log_debug().build()


def test_pixi_appose_requirement():
    """Tests that building without appose dependency fails."""
    base = "target/envs/pixi-appose-requirement"
    if Path(base).exists():
        shutil.rmtree(base)

    with pytest.raises(Exception):  # Should raise IllegalStateException equivalent
        (
            appose.pixi()
            .conda("python")
            .pypi("cowsay==6.1")
            .base(base)
            .log_debug()
            .build()
        )


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


def test_pixi_environment_selection():
    """Tests that .environment() selects a non-default pixi environment."""
    env = (
        appose.pixi()
        .file(str(TEST_RESOURCES / "cowsay-multi-env.toml"))
        .base("target/envs/pixi-multi-env")
        .environment("alt")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    # Verify launch args include --environment alt
    launch_args = env.launch_args()
    assert "--environment" in launch_args, "launch_args should contain --environment"
    idx = launch_args.index("--environment")
    assert launch_args[idx + 1] == "alt"
    # Verify bin path resolves to the alt environment directory
    import os

    assert os.sep + "alt" + os.sep in env.bin_paths()[0], (
        "bin_paths should reference the alt environment"
    )
    cowsay_and_assert(env, "multi-env")


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
