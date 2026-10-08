# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests Builder.status().
Uses hand-made marker files, so no tools or network are needed.
"""

from pathlib import Path

import pytest

import appose
from appose.builder import BuildException, EnvStatus


def touch(dir_path: Path, rel_path: str) -> None:
    p = dir_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()


def test_missing(tmp_path):
    env_dir = tmp_path / "missing"
    assert appose.mamba().base(env_dir).status() == EnvStatus.MISSING
    assert appose.pixi().base(env_dir).status() == EnvStatus.MISSING
    assert appose.uv().base(env_dir).status() == EnvStatus.MISSING


def test_empty_dir_is_missing(tmp_path):
    assert appose.mamba().base(tmp_path).status() == EnvStatus.MISSING
    assert appose.pixi().base(tmp_path).status() == EnvStatus.MISSING
    assert appose.uv().base(tmp_path).status() == EnvStatus.MISSING


def test_external_conda(tmp_path):
    touch(tmp_path, "conda-meta/history")
    assert appose.mamba().base(tmp_path).status() == EnvStatus.EXTERNAL


def test_external_venv(tmp_path):
    touch(tmp_path, "pyvenv.cfg")
    assert appose.uv().base(tmp_path).status() == EnvStatus.EXTERNAL


def test_incompatible(tmp_path):
    conda = tmp_path / "conda"
    touch(conda, "conda-meta/history")
    assert appose.pixi().base(conda).status() == EnvStatus.INCOMPATIBLE
    assert appose.uv().base(conda).status() == EnvStatus.INCOMPATIBLE
    # Note: build() must agree, failing before any tools are downloaded.
    with pytest.raises(BuildException):
        appose.pixi().base(conda).build()

    venv = tmp_path / "venv"
    touch(venv, "pyvenv.cfg")
    assert appose.mamba().base(venv).status() == EnvStatus.INCOMPATIBLE
    assert appose.pixi().base(venv).status() == EnvStatus.INCOMPATIBLE

    pixi = tmp_path / "pixi"
    touch(pixi, ".pixi/envs/default/conda-meta/history")
    assert appose.mamba().base(pixi).status() == EnvStatus.INCOMPATIBLE
    assert appose.uv().base(pixi).status() == EnvStatus.INCOMPATIBLE
    assert appose.pixi().base(pixi).status() == EnvStatus.EXTERNAL


def test_stale_and_current(tmp_path):
    touch(tmp_path, "conda-meta/history")
    builder = appose.mamba().base(tmp_path).content("name: foo\n")
    # Simulate a successful build by recording the builder's state.
    builder._write_appose_state_file(tmp_path)
    assert builder.status() == EnvStatus.CURRENT
    builder.channels("conda-forge")
    assert builder.status() == EnvStatus.STALE


def test_inferred_scheme_is_current(tmp_path):
    touch(tmp_path, "conda-meta/history")
    yml = "name: foo\n"
    # Note: build() infers and stores the scheme before writing appose.json.
    appose.mamba().base(tmp_path).content(yml).scheme(
        "environment.yml"
    )._write_appose_state_file(tmp_path)
    # A fresh builder with the same content must still report CURRENT.
    assert appose.mamba().base(tmp_path).content(yml).status() == EnvStatus.CURRENT


def test_state_file_without_environment_is_missing(tmp_path):
    builder = appose.mamba().base(tmp_path).content("name: foo\n")
    builder._write_appose_state_file(tmp_path)
    assert builder.status() == EnvStatus.MISSING


def test_delete_resets_to_missing(tmp_path):
    env_dir = tmp_path / "env"
    touch(env_dir, "conda-meta/history")
    builder = appose.mamba().base(env_dir).content("name: foo\n")
    builder._write_appose_state_file(env_dir)
    assert builder.status() == EnvStatus.CURRENT
    builder.delete()
    assert builder.status() == EnvStatus.MISSING


def test_dynamic_delegates(tmp_path):
    touch(tmp_path, ".pixi/envs/default/conda-meta/history")
    builder = appose.content("name: foo\ndependencies:\n  - python\n").base(tmp_path)
    assert builder.status() == EnvStatus.EXTERNAL


def test_simple(tmp_path):
    env_dir = tmp_path / "simple"
    assert appose.custom().base(env_dir).status() == EnvStatus.MISSING
    env_dir.mkdir()
    assert appose.custom().base(env_dir).status() == EnvStatus.EXTERNAL
