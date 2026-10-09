# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for tool self-update logic."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from appose.tool import TOOL_AUTO_UPDATE_VAR, Tool, _version_tuple
from appose.tool.mamba import Mamba
from appose.tool.pixi import Pixi
from appose.tool.uv import Uv


class FakeTool(Tool):
    """Tool whose version and release downloads are simulated."""

    MIN_VERSION = "1.0.0"
    AUTO_UPDATE_VAR = "APPOSE_FAKE_AUTO_UPDATE"

    def __init__(self, rootdir: Path, installed: str, latest: str | None):
        super().__init__("fake", None, str(rootdir / "bin" / "fake"), str(rootdir))
        Path(self.command).parent.mkdir(parents=True)
        self.installed = installed
        self.latest = latest
        self.downloads: list[str] = []

    def version(self) -> str:
        return self.installed

    def _latest_version(self) -> str | None:
        if self.latest is None:
            raise OSError("offline")
        return self.latest

    def _download_url(self, version: str) -> str | None:
        return f"https://example.com/fake/{version}"

    def _download_from(self, url: str) -> Path:
        self.downloads.append(url.rsplit("/", 1)[-1])
        return Path(url)

    def _decompress(self, archive: Path) -> None:
        self.installed = archive.name


@pytest.fixture(autouse=True)
def auto_update_enabled(monkeypatch):
    monkeypatch.delenv(TOOL_AUTO_UPDATE_VAR, raising=False)
    monkeypatch.delenv(FakeTool.AUTO_UPDATE_VAR, raising=False)


def test_version_tuple():
    assert _version_tuple("v0.81.0") == (0, 81, 0)
    assert _version_tuple("0.9.10") == (0, 9, 10)
    assert _version_tuple("0.58.0") < _version_tuple("v0.81.0")
    assert _version_tuple("0.9.0") < _version_tuple("0.10.0")


def test_update_to_latest(tmp_path):
    tool = FakeTool(tmp_path, installed="98.0.0", latest="99.0.0")
    tool.self_update()
    assert tool.downloads == ["99.0.0"]
    assert tool.installed == "99.0.0"


def test_update_already_latest(tmp_path):
    tool = FakeTool(tmp_path, installed="99.0.0", latest="99.0.0")
    tool.self_update()
    assert tool.downloads == []


def test_update_throttled(tmp_path):
    tool = FakeTool(tmp_path, installed="98.0.0", latest="99.0.0")
    tool.self_update()
    tool.latest = "99.1.0"
    tool.self_update()
    assert tool.downloads == ["99.0.0"]

    # Once the interval elapses, check again.
    stamp = Path(tool.command).parent / "last-update-check"
    old = time.time() - Tool.UPDATE_INTERVAL - 1
    os.utime(stamp, (old, old))
    tool.self_update()
    assert tool.downloads == ["99.0.0", "99.1.0"]


def test_update_disabled_enforces_minimum(tmp_path, monkeypatch):
    monkeypatch.setenv(FakeTool.AUTO_UPDATE_VAR, "false")
    tool = FakeTool(tmp_path, installed="0.1.0", latest="99.0.0")
    tool.self_update()
    assert tool.downloads == [FakeTool.MIN_VERSION]


def test_update_disabled_leaves_newer_alone(tmp_path, monkeypatch):
    monkeypatch.setenv(FakeTool.AUTO_UPDATE_VAR, "0")
    tool = FakeTool(tmp_path, installed="99.0.0", latest="99.1.0")
    tool.self_update()
    assert tool.downloads == []


@pytest.mark.parametrize(
    "blanket,specific,enabled",
    [
        (None, None, True),
        ("false", None, False),
        ("true", None, True),
        ("false", "true", True),
        ("true", "off", False),
        ("no", "", False),
    ],
)
def test_auto_update_vars(tmp_path, monkeypatch, blanket, specific, enabled):
    if blanket is not None:
        monkeypatch.setenv(TOOL_AUTO_UPDATE_VAR, blanket)
    if specific is not None:
        monkeypatch.setenv(FakeTool.AUTO_UPDATE_VAR, specific)
    tool = FakeTool(tmp_path, installed="98.0.0", latest="99.0.0")
    tool.self_update()
    assert tool.downloads == (["99.0.0"] if enabled else [])


def test_update_failure_falls_back_to_minimum(tmp_path):
    # Simulate failure (e.g. offline) when checking for the latest release.
    errors = []
    tool = FakeTool(tmp_path, installed="0.1.0", latest=None)
    tool.set_error_consumer(errors.append)
    tool.self_update()
    assert tool.downloads == [FakeTool.MIN_VERSION]
    assert any("could not update fake" in e for e in errors)


def test_update_unsupported_tool(tmp_path):
    # A tool without release hooks is left alone.
    class PlainTool(FakeTool):
        MIN_VERSION = None

        def _latest_version(self):
            return Tool._latest_version(self)

    tool = PlainTool(tmp_path, installed="0.1.0", latest="99.0.0")
    tool.self_update()
    assert tool.downloads == []


def test_tool_update_vars():
    assert Pixi.AUTO_UPDATE_VAR == "APPOSE_PIXI_AUTO_UPDATE"
    assert Uv.AUTO_UPDATE_VAR == "APPOSE_UV_AUTO_UPDATE"
    assert Mamba.AUTO_UPDATE_VAR == "APPOSE_MAMBA_AUTO_UPDATE"


def test_pixi_upgrade_uses_self_update(tmp_path):
    class RecordingPixi(Pixi):
        def _do_exec(self, cwd, silent, include_flags, args):
            self.calls.append(args)

    pixi = RecordingPixi(str(tmp_path))
    pixi.calls = []
    pixi._upgrade(None)
    pixi._upgrade("v0.81.0")
    assert pixi.calls == [
        ("self-update", "--no-release-note"),
        ("self-update", "--no-release-note", "--version", "0.81.0"),
    ]
