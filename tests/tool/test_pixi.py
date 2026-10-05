# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for Pixi self-update logic."""

import os
import time
from pathlib import Path

import pytest

from appose.tool.pixi import Pixi, _version_tuple


class FakePixi(Pixi):
    """Pixi whose version and self-update calls are simulated."""

    def __init__(self, rootdir: Path, installed: str, latest: str):
        super().__init__(str(rootdir))
        Path(self.command).parent.mkdir(parents=True)
        self.installed = installed
        self.latest = latest
        self.calls: list[tuple[str, ...]] = []

    def version(self) -> str:
        return self.installed

    def _self_update(self, *args: str) -> None:
        self.calls.append(args)
        self.installed = args[1] if args else self.latest


@pytest.fixture(autouse=True)
def auto_update_enabled(monkeypatch):
    monkeypatch.delenv(Pixi.AUTO_UPDATE_VAR, raising=False)


def test_version_tuple():
    assert _version_tuple("v0.81.0") == (0, 81, 0)
    assert _version_tuple("0.9.10") == (0, 9, 10)
    assert _version_tuple("0.58.0") < _version_tuple("v0.81.0")
    assert _version_tuple("0.9.0") < _version_tuple("0.10.0")


def test_update_to_latest(tmp_path):
    pixi = FakePixi(tmp_path, installed="98.0.0", latest="99.0.0")
    pixi.update()
    assert pixi.calls == [()]
    assert pixi.installed == "99.0.0"


def test_update_throttled(tmp_path):
    pixi = FakePixi(tmp_path, installed="98.0.0", latest="99.0.0")
    pixi.update()
    pixi.update()
    assert pixi.calls == [()]

    # Once the interval elapses, check again.
    stamp = Path(pixi.command).parent / "last-update-check"
    old = time.time() - Pixi.UPDATE_INTERVAL - 1
    os.utime(stamp, (old, old))
    pixi.update()
    assert pixi.calls == [(), ()]


def test_update_disabled_enforces_minimum(tmp_path, monkeypatch):
    monkeypatch.setenv(Pixi.AUTO_UPDATE_VAR, "false")
    pixi = FakePixi(tmp_path, installed="0.1.0", latest="99.0.0")
    pixi.update()
    assert pixi.calls == [("--version", Pixi.MIN_VERSION.lstrip("v"))]


def test_update_disabled_leaves_newer_alone(tmp_path, monkeypatch):
    monkeypatch.setenv(Pixi.AUTO_UPDATE_VAR, "0")
    pixi = FakePixi(tmp_path, installed="99.0.0", latest="99.1.0")
    pixi.update()
    assert pixi.calls == []


def test_update_failure_falls_back_to_minimum(tmp_path):
    # Simulate failure (e.g. offline) when checking for the latest release.
    pixi = FakePixi(tmp_path, installed="0.1.0", latest="0.1.0")
    pixi.update()
    assert pixi.calls == [(), ("--version", Pixi.MIN_VERSION.lstrip("v"))]
