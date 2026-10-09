# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Unit tests for lock file support. These are fast and require no
external tools or network access.
"""

import re

import pytest

import appose
from appose.builder import BuildException, SimpleBuilder, _lock_hash
from appose.builder.mamba import MambaBuilder
from appose.builder.pixi import PixiBuilder
from appose.builder.uv import UvBuilder


def test_lock_hash_deterministic():
    """Same lock content must produce an identical hash."""
    content = "version = 1\npackages = []\n"
    assert _lock_hash(content) == _lock_hash(content)


def test_lock_hash_content_sensitive():
    """Different lock content must produce different hashes."""
    assert _lock_hash('packages = ["a"]\n') != _lock_hash('packages = ["b"]\n')


def test_lock_hash_format():
    """The hash must be a 64-character lowercase hex string (SHA-256)."""
    assert re.fullmatch(r"[0-9a-f]{64}", _lock_hash("appose"))


def test_lock_hash_in_state():
    """appose.json records a lockHash only when a lock is supplied."""
    builder = UvBuilder().content("cowsay\n").scheme("requirements.txt")
    assert '"lockHash"' not in builder._build_state_string()
    lock = "version = 1\n"
    builder.lock_content(lock)
    assert f'"lockHash":"{_lock_hash(lock)}"' in builder._build_state_string()


def test_mamba_rejects_lock():
    """Builders that cannot honor lock files reject them early."""
    with pytest.raises(NotImplementedError):
        MambaBuilder().lock_content("anything")


def test_simple_rejects_lock():
    """Builders that cannot honor lock files reject them early."""
    with pytest.raises(NotImplementedError):
        SimpleBuilder().lock_content("anything")


def test_dynamic_lock_mamba_fails():
    """Forwarding a lock to a mamba delegate via a dynamic builder must fail."""
    env_yml = "name: lock-mamba-fail\nchannels:\n  - conda-forge\ndependencies:\n  - python>=3.8\n"
    with pytest.raises(NotImplementedError):
        (
            appose.content(env_yml)
            .builder("mamba")
            .lock_content("bogus")
            .base("target/envs/mamba-lock-fail")
            .build()
        )


def test_lock_file_missing_raises_build_exception():
    """A missing lock file surfaces as a BuildException."""
    with pytest.raises(BuildException):
        UvBuilder().lock_file("this-lock-does-not-exist.lock")


def test_lock_url_malformed_raises_build_exception():
    """A malformed lock URL surfaces as a BuildException."""
    with pytest.raises(BuildException):
        UvBuilder().lock_url("ht!tp://not a valid url")


def test_uv_lock_programmatic_unsupported():
    """Programmatic uv builds (no manifest) cannot be locked."""
    with pytest.raises(ValueError):
        (
            appose.uv()
            .include("cowsay==6.1")
            .lock_content("bogus")
            .base("target/envs/uv-lock-prog")
            .build()
        )


def test_uv_lock_unsupported_scheme():
    """uv lock files only apply to pyproject.toml, not requirements.txt."""
    with pytest.raises(ValueError):
        (
            appose.uv()
            .content("cowsay==6.1\n")
            .scheme("requirements.txt")
            .lock_content("bogus")
            .base("target/envs/uv-lock-reqs")
            .build()
        )


def test_pixi_lock_programmatic_unsupported():
    """Programmatic pixi builds (no manifest) cannot be locked."""
    with pytest.raises(ValueError):
        (
            appose.pixi()
            .conda("python>=3.8")
            .pypi("cowsay==6.1")
            .lock_content("bogus")
            .base("target/envs/pixi-lock-prog")
            .build()
        )


def test_pixi_lock_with_channels_unsupported():
    """
    Adding channels would re-resolve the manifest, rewriting the lock,
    so programmatic channels cannot be combined with a lock.
    """
    pixi_toml = '[workspace]\nname = "x"\nchannels = ["conda-forge"]\nplatforms = ["linux-64"]\n'
    with pytest.raises(ValueError):
        (
            PixiBuilder()
            .content(pixi_toml)
            .channels("bioconda")
            .lock_content("bogus")
            .base("target/envs/pixi-lock-channels")
            .build()
        )
