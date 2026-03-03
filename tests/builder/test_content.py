# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for the builder .content() API across all builder/scheme combinations.

Verifies that each builder:
- correctly accepts its supported schemes and builds a working environment
- fails fast (before any tool installation) with a clear error for unsupported schemes

Matrix: 4 builders × 5 content types = 20 tests:
- uv: accepts requirements.txt, pyproject.toml; rejects environment.yml, pixi.toml, unrecognized
- pixi: accepts pixi.toml, pyproject.toml, environment.yml; rejects requirements.txt, unrecognized
- mamba: accepts environment.yml only; rejects all others
- content (dynamic): auto-detects requirements.txt→uv, environment.yml→pixi,
  pixi.toml→pixi, pyproject.toml→pixi; rejects unrecognized
"""

from pathlib import Path

import pytest

import appose
from appose.builder.mamba import MambaBuilder
from appose.builder.pixi import PixiBuilder
from appose.builder.uv import UvBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES: Path = Path(__file__).parent.parent / "resources" / "envs"

# Minimal content stubs for "fail fast" tests — just enough to trigger correct
# scheme detection, but deliberately incompatible with the builder under test.

PIXI_TOML_STUB = """\
[workspace]
name = "stub"
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
python = "*"
"""

ENV_YML_STUB = """\
name: stub-env
dependencies:
  - python
"""

REQUIREMENTS_TXT_STUB = "appose\n"

PYPROJECT_TOML_STUB = """\
[project]
name = "stub"
version = "0.1.0"
dependencies = []
"""

# Must not match any scheme (does not start with a letter/digit or TOML/YAML markers).
UNRECOGNIZED = "## not a valid config format\n"


# ======================== UvBuilder ========================


def test_uv_with_requirements_txt():
    content = (TEST_RESOURCES / "cowsay-requirements.txt").read_text(encoding="utf-8")
    env = (
        appose.uv()
        .content(content)
        .base("target/envs/content-uv-requirements")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "uv-req")


def test_uv_with_pyproject_toml():
    content = (TEST_RESOURCES / "cowsay-pyproject.toml").read_text(encoding="utf-8")
    env = (
        appose.uv()
        .content(content)
        .base("target/envs/content-uv-pyproject")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "uv-pyproject")


def test_uv_with_environment_yml():
    with pytest.raises(Exception):
        appose.uv().content(ENV_YML_STUB).base("target/envs/content-uv-envyml").build()


def test_uv_with_pixi_toml():
    with pytest.raises(Exception):
        appose.uv().content(PIXI_TOML_STUB).base("target/envs/content-uv-pixi").build()


def test_uv_with_unrecognized():
    with pytest.raises(Exception):
        appose.uv().content(UNRECOGNIZED).base("target/envs/content-uv-unknown").build()


# ======================== PixiBuilder ========================


def test_pixi_with_pixi_toml():
    content = (TEST_RESOURCES / "cowsay-pixi.toml").read_text(encoding="utf-8")
    env = (
        appose.pixi()
        .content(content)
        .base("target/envs/content-pixi-pixi")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "pixi-pixi")


def test_pixi_with_pyproject_toml():
    content = (TEST_RESOURCES / "cowsay-pixi-pyproject.toml").read_text(
        encoding="utf-8"
    )
    env = (
        appose.pixi()
        .content(content)
        .base("target/envs/content-pixi-pyproject")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "pixi-pyproject")


def test_pixi_with_environment_yml():
    content = (TEST_RESOURCES / "cowsay.yml").read_text(encoding="utf-8")
    env = (
        appose.pixi()
        .content(content)
        .base("target/envs/content-pixi-envyml")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "pixi-envyml")


def test_pixi_with_requirements_txt():
    with pytest.raises(Exception):
        appose.pixi().content(REQUIREMENTS_TXT_STUB).base(
            "target/envs/content-pixi-requirements"
        ).build()


def test_pixi_with_unrecognized():
    with pytest.raises(Exception):
        appose.pixi().content(UNRECOGNIZED).base(
            "target/envs/content-pixi-unknown"
        ).build()


# ======================== MambaBuilder ========================


def test_mamba_with_environment_yml():
    content = (TEST_RESOURCES / "cowsay.yml").read_text(encoding="utf-8")
    env = (
        appose.mamba()
        .content(content)
        .base("target/envs/content-mamba-envyml")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), MambaBuilder)
    cowsay_and_assert(env, "mamba-envyml")


def test_mamba_with_pyproject_toml():
    with pytest.raises(Exception):
        appose.mamba().content(PYPROJECT_TOML_STUB).base(
            "target/envs/content-mamba-pyproject"
        ).build()


def test_mamba_with_requirements_txt():
    with pytest.raises(Exception):
        appose.mamba().content(REQUIREMENTS_TXT_STUB).base(
            "target/envs/content-mamba-requirements"
        ).build()


def test_mamba_with_pixi_toml():
    with pytest.raises(Exception):
        appose.mamba().content(PIXI_TOML_STUB).base(
            "target/envs/content-mamba-pixi"
        ).build()


def test_mamba_with_unrecognized():
    with pytest.raises(Exception):
        appose.mamba().content(UNRECOGNIZED).base(
            "target/envs/content-mamba-unknown"
        ).build()


# ======================== DynamicBuilder (appose.content) ========================


def test_content_with_requirements_txt():
    content = (TEST_RESOURCES / "cowsay-requirements.txt").read_text(encoding="utf-8")
    env = (
        appose.content(content)
        .base("target/envs/content-dynamic-requirements")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "dynamic-req")


def test_content_with_environment_yml():
    content = (TEST_RESOURCES / "cowsay.yml").read_text(encoding="utf-8")
    env = (
        appose.content(content)
        .base("target/envs/content-dynamic-envyml")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "dynamic-envyml")


def test_content_with_pixi_toml():
    content = (TEST_RESOURCES / "cowsay-pixi.toml").read_text(encoding="utf-8")
    env = (
        appose.content(content)
        .base("target/envs/content-dynamic-pixi")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "dynamic-pixi")


def test_content_with_pyproject_toml():
    content = (TEST_RESOURCES / "cowsay-pixi-pyproject.toml").read_text(
        encoding="utf-8"
    )
    env = (
        appose.content(content)
        .base("target/envs/content-dynamic-pyproject")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "dynamic-pyproject")


def test_content_with_unrecognized():
    with pytest.raises(Exception):
        appose.content(UNRECOGNIZED).base("target/envs/content-dynamic-unknown").build()
