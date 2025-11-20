###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2025 Appose developers.
# %%
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# #L%
###

"""End-to-end tests for PixiBuilder."""

import shutil
from pathlib import Path

import pytest

from appose.builder import DynamicBuilder
from appose.builder.pixi import PixiBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES = Path(__file__).parent.parent / "resources" / "envs"


def test_conda():
    """Tests the builder-agnostic API with an environment.yml file."""
    env = (
        DynamicBuilder()
        .file(str(TEST_RESOURCES / "cowsay.yml"))
        .base("target/envs/conda-cowsay")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "moo")


def test_pixi():
    """Tests building from a pixi.toml file."""
    env = (
        PixiBuilder()
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
        PixiBuilder()
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
        PixiBuilder().base(base).log_debug().build()


def test_pixi_appose_requirement():
    """Tests that building without appose dependency fails."""
    base = "target/envs/pixi-appose-requirement"
    if Path(base).exists():
        shutil.rmtree(base)

    with pytest.raises(Exception):  # Should raise IllegalStateException equivalent
        (
            PixiBuilder()
            .conda("python")
            .pypi("cowsay==6.1")
            .base(base)
            .log_debug()
            .build()
        )


def test_pixi_pyproject():
    """Tests building from a pyproject.toml with pixi config."""
    env = (
        PixiBuilder()
        .file(str(TEST_RESOURCES / "cowsay-pixi-pyproject.toml"))
        .base("target/envs/pixi-cowsay-pyproject")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "pixi-pyproject")


def test_content_api():
    """Tests building environment from content string using type-specific builder."""
    pixi_toml = """[project]
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
        PixiBuilder()
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
        DynamicBuilder()
        .content(env_yml)
        .base("target/envs/content-env-yml")
        .log_debug()
        .build()
    )

    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "yml!")


def test_content_pixi_toml():
    """Tests auto-detecting builder from pixi.toml content string."""
    pixi_toml = """[project]
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
        DynamicBuilder()
        .content(pixi_toml)
        .base("target/envs/content-pixi-toml")
        .log_debug()
        .build()
    )

    assert isinstance(env.builder(), PixiBuilder)
    cowsay_and_assert(env, "toml!")
