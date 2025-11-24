# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests the wrap feature for existing environments."""

from pathlib import Path

import pytest

import appose
from appose.builder import BuildException, SimpleBuilder
from appose.builder.mamba import MambaBuilder
from appose.builder.pixi import PixiBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES: Path = Path(__file__).parent.parent / "resources" / "envs"


def test_wrap_pixi():
    """Tests wrapping a pixi environment."""
    pixi_dir = Path("target/test-wrap-pixi")
    pixi_dir.mkdir(parents=True, exist_ok=True)
    pixi_toml = pixi_dir / "pixi.toml"
    pixi_toml.touch()

    try:
        pixi_env = appose.wrap(pixi_dir)
        assert pixi_env is not None
        assert isinstance(pixi_env.builder(), PixiBuilder)
        assert pixi_env.base() == str(pixi_dir.absolute())
        assert pixi_env.launch_args() is not None
        assert len(pixi_env.launch_args()) > 0
        assert "pixi" in pixi_env.launch_args()[0], (
            "Pixi environment should use pixi launcher"
        )
    finally:
        if pixi_toml.exists():
            pixi_toml.unlink()
        if pixi_dir.exists():
            pixi_dir.rmdir()


def test_wrap_mamba():
    """Tests wrapping a conda/mamba environment."""
    conda_dir = Path("target/test-wrap-conda")
    conda_dir.mkdir(parents=True, exist_ok=True)
    conda_meta = conda_dir / "conda-meta"
    conda_meta.mkdir(parents=True, exist_ok=True)

    try:
        conda_env = appose.wrap(conda_dir)
        assert conda_env is not None
        assert conda_env.base() == str(conda_dir.absolute())
        assert conda_env.launch_args() is not None
        assert len(conda_env.launch_args()) > 0
        assert "micromamba" in conda_env.launch_args()[0], (
            "Conda environment should use micromamba launcher"
        )
    finally:
        if conda_meta.exists():
            conda_meta.rmdir()
        if conda_dir.exists():
            conda_dir.rmdir()


def test_wrap_uv():
    """Tests wrapping a uv environment."""
    uv_dir = Path("target/test-wrap-uv")
    uv_dir.mkdir(parents=True, exist_ok=True)
    pyvenv_cfg = uv_dir / "pyvenv.cfg"
    pyvenv_cfg.touch()

    try:
        uv_env = appose.wrap(uv_dir)
        assert uv_env is not None
        assert uv_env.base() == str(uv_dir.absolute())
        # uv environments use standard venv structure with no special launch args.
        assert len(uv_env.launch_args()) == 0, (
            "uv environment should have no special launcher"
        )
    finally:
        if pyvenv_cfg.exists():
            pyvenv_cfg.unlink()
        if uv_dir.exists():
            uv_dir.rmdir()


def test_wrap_custom():
    """Tests wrapping a plain directory (should fall back to SimpleBuilder)."""
    custom_dir = Path("target/test-wrap-simple")
    custom_dir.mkdir(parents=True, exist_ok=True)

    try:
        custom_env = appose.wrap(custom_dir)
        assert custom_env is not None
        assert isinstance(custom_env.builder(), SimpleBuilder)
        assert custom_env.base() == str(custom_dir.absolute())
        # SimpleBuilder uses empty launch args by default.
        assert len(custom_env.launch_args()) == 0, (
            "Custom environment should have no special launcher"
        )
    finally:
        if custom_dir.exists():
            custom_dir.rmdir()


def test_wrap_non_existent():
    """Tests that wrapping non-existent directory throws exception."""
    non_existent = Path("target/does-not-exist")

    with pytest.raises(BuildException) as exc_info:
        appose.wrap(non_existent)

    assert "does not exist" in str(exc_info.value)


def test_wrap_and_rebuild():
    """Tests that preexisting (wrapped) environments can be rebuilt properly."""
    # Build an environment from a config file.
    env_dir = Path("target/envs/mamba-wrap-rebuild-test")
    env1 = (
        appose.mamba(str(TEST_RESOURCES / "cowsay.yml"))
        .base(env_dir)
        .log_debug()
        .build()
    )
    assert env1 is not None

    # Wrap the environment (simulating restarting the application).
    env2 = appose.wrap(env_dir)
    assert env2 is not None
    assert env2.base() == str(env_dir.absolute())
    assert env2.builder() is not None, "Wrapped environment should have a builder"

    # Verify that the builder detected the config file.
    assert isinstance(env2.builder(), MambaBuilder)

    # Rebuild the wrapped environment.
    env3 = env2.builder().rebuild()
    assert env3 is not None
    assert env3.base() == str(env_dir.absolute())

    # Verify the rebuilt environment works.
    cowsay_and_assert(env3, "rebuilt")
