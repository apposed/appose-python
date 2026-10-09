# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


"""Tests for which appose-python builders install into environments."""

from pathlib import Path

from appose.builder.requirement import (
    ENV_VAR,
    MAIN_BRANCH,
    Requirement,
    appose_requirement,
    mentions_appose,
)


def test_release(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert appose_requirement("1.1.2") == Requirement("appose>=1.1,<1.2")
    assert appose_requirement("0.13.0.post1") == Requirement("appose>=0.13,<0.14")
    assert appose_requirement("1.9.0") == Requirement("appose>=1.9,<1.10")


def test_dev_version_pins_itself(monkeypatch):
    """A development version installs this very appose-python, as installed."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    requirement = appose_requirement("1.1.0.dev0")
    # NB: Tests run against an editable install of this checkout.
    here = Path(__file__).resolve().parents[2]
    assert requirement == Requirement(f"appose @ {here.as_uri()}", editable=True)
    assert requirement.pip_args() == ["-e", f"appose @ {here.as_uri()}"]


def test_dev_version_without_origin(monkeypatch):
    """A development version installed from an index falls back to main."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr("appose.builder.requirement._origin", lambda: None)
    assert appose_requirement("1.1.0.dev0") == MAIN_BRANCH


def test_override_requirement(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "appose==1.1.3")
    assert appose_requirement("1.1.2") == Requirement("appose==1.1.3")


def test_override_directory(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    requirement = appose_requirement("1.1.2")
    assert requirement == Requirement(f"appose @ {tmp_path.as_uri()}", editable=True)


def test_mentions_appose():
    assert mentions_appose(["numpy", "appose"])
    assert mentions_appose(["appose==1.1.2"])
    assert mentions_appose(["appose @ file:///somewhere"])
    assert not mentions_appose(["numpy"])
    assert not mentions_appose([])
