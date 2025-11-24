# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end tests for MambaBuilder."""

from pathlib import Path


from appose.builder import DynamicBuilder
from appose.builder.mamba import MambaBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES: Path = Path(__file__).parent.parent / "resources" / "envs"


def test_explicit_mamba_builder():
    """Tests explicit mamba builder selection using .builder() method."""
    env = (
        DynamicBuilder()
        .file(str(TEST_RESOURCES / "cowsay.yml"))
        .builder("mamba")
        .base("target/envs/mamba-cowsay")
        .log_debug()
        .build()
    )

    assert isinstance(env.builder(), MambaBuilder)

    # Verify it actually used mamba by checking for conda-meta directory
    env_base = Path(env.base())
    conda_meta = env_base / "conda-meta"
    assert conda_meta.exists() and conda_meta.is_dir(), (
        "Environment should have conda-meta directory when using mamba builder"
    )

    cowsay_and_assert(env, "yay")
