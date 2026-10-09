# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Pixi-based environment manager.
Pixi is a modern package management tool that provides better environment
management than micromamba and supports both conda and PyPI packages.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from ..util import download, environment, platform
from . import Tool


def _pixi_binary() -> str | None:
    """Returns the filename to download for the current platform."""
    platform_str = platform.PLATFORM

    mapping = {
        "MACOS|ARM64": "pixi-aarch64-apple-darwin.tar.gz",  # Apple Silicon macOS
        "MACOS|X64": "pixi-x86_64-apple-darwin.tar.gz",  # Intel macOS
        "WINDOWS|ARM64": "pixi-aarch64-pc-windows-msvc.zip",  # ARM64 Windows
        "WINDOWS|X64": "pixi-x86_64-pc-windows-msvc.zip",  # x64 Windows
        "LINUX|ARM64": "pixi-aarch64-unknown-linux-musl.tar.gz",  # ARM64 MUSL Linux
        "LINUX|X64": "pixi-x86_64-unknown-linux-musl.tar.gz",  # x64 MUSL Linux
    }

    return mapping.get(platform_str)


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parses a version string like "v0.81.0" into a comparable tuple of ints."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


class Pixi(Tool):
    """
    Pixi-based environment manager.

    It is expected that the Pixi installation has executable commands as shown below:

        PIXI_ROOT
        ├── .pixi
        │   ├── bin
        │   │   ├── pixi(.exe)
    """

    # Pixi version to download
    PIXI_VERSION: str = "v0.81.0"

    # Minimum acceptable Pixi version; older installations get upgraded to it
    MIN_VERSION: str = PIXI_VERSION

    # Minimum number of seconds between checks for a newer Pixi release
    UPDATE_INTERVAL: float = 24 * 60 * 60

    # Environment variable which, when set to false, disables checking for newer releases
    AUTO_UPDATE_VAR: str = "APPOSE_PIXI_AUTO_UPDATE"

    # Path where Appose installs Pixi by default (.pixi subdirectory thereof)
    BASE_PATH: str = environment.appose_envs_dir()

    # The filename to download for the current platform
    PIXI_BINARY: str | None = _pixi_binary()

    # URL from where Pixi is downloaded to be installed
    DOWNLOAD_URL: str | None = (
        f"https://github.com/prefix-dev/pixi/releases/download/{PIXI_VERSION}/{PIXI_BINARY}"
        if PIXI_BINARY
        else None
    )

    def __init__(self, rootdir: str | None = None):
        """
        Create a new Pixi object.

        Args:
            rootdir: The root dir for Pixi installation. If None, uses BASE_PATH.
        """
        root = rootdir if rootdir else self.BASE_PATH

        # Determine pixi relative path based on platform
        if platform.is_windows():
            pixi_relative_path = Path(".pixi") / "bin" / "pixi.exe"
        else:
            pixi_relative_path = Path(".pixi") / "bin" / "pixi"

        command_path = str(Path(root) / pixi_relative_path)

        super().__init__("pixi", self.DOWNLOAD_URL, command_path, root)

    def _decompress(self, archive: Path) -> None:
        """
        Decompress and installs pixi from the downloaded archive.

        Args:
            archive: Path to the downloaded archive file.

        Raises:
            IOError: If decompression/installation fails.
        """
        pixi_base_dir = Path(self.rootdir)
        if not pixi_base_dir.is_dir():
            pixi_base_dir.mkdir(parents=True, exist_ok=True)

        pixi_bin_dir = pixi_base_dir / ".pixi" / "bin"
        if not pixi_bin_dir.exists():
            pixi_bin_dir.mkdir(parents=True, exist_ok=True)

        download.unpack(archive, pixi_bin_dir)

        pixi_file = Path(self.command)
        if not pixi_file.exists():
            raise OSError(f"Expected pixi binary is missing: {self.command}")

        # Set executable permission if needed
        if not platform.is_executable(pixi_file):
            pixi_file.chmod(pixi_file.stat().st_mode | 0o111)

    def update(self) -> None:
        """
        Upgrade the installed Pixi, if warranted.

        Pixi is upgraded to the latest release, at most once per UPDATE_INTERVAL,
        unless the APPOSE_PIXI_AUTO_UPDATE environment variable is set to false.
        Regardless, Pixi is upgraded to at least MIN_VERSION, so that it
        understands manifests, lock files and caches written by newer Pixi
        installations elsewhere on the system.

        Failures (e.g. due to no network connection) are reported to the error
        consumer, but not raised, so that builds can proceed with the existing Pixi.

        Raises:
            IOError: If Pixi is not installed.
        """
        if self._auto_update_enabled() and self._update_check_due():
            self._self_update()

        if _version_tuple(self.version()) < _version_tuple(self.MIN_VERSION):
            self._self_update("--version", self.MIN_VERSION.lstrip("v"))

    def _auto_update_enabled(self) -> bool:
        value = os.environ.get(self.AUTO_UPDATE_VAR, "").strip().lower()
        return value not in ("0", "false", "no", "off")

    def _update_check_due(self) -> bool:
        """
        Check whether UPDATE_INTERVAL has elapsed since the last update check,
        recording the current time as the latest check if so.
        """
        stamp = Path(self.command).parent / "last-update-check"
        try:
            elapsed = time.time() - stamp.stat().st_mtime
            if 0 <= elapsed < self.UPDATE_INTERVAL:
                return False
        except OSError:
            pass  # No previous check recorded.
        try:
            # Note: Record the check even if it fails, so that
            # being offline does not cause a failed check every time.
            stamp.touch()
        except OSError:
            pass
        return True

    def _self_update(self, *args: str) -> None:
        try:
            self._do_exec(
                cwd=None,
                silent=False,
                include_flags=False,
                args=("self-update", "--no-release-note", *args),
            )
        except OSError:
            # Note: Pixi's own error output has already gone to the error consumer.
            self._error(
                "Warning: could not update pixi; continuing with the installed version.\n"
            )

    def init(self, project_dir: Path) -> None:
        """
        Initialize a pixi project in the specified directory.

        Args:
            project_dir: The directory to initialize as a pixi project.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Pixi has not been installed
        """
        self.exec("init", str(project_dir.absolute()))

    def add_channels(self, project_dir: Path, *channels: str) -> None:
        """
        Add conda channels to a pixi project.

        Args:
            project_dir: The pixi project directory.
            channels: The channels to add.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Pixi has not been installed
        """
        if not channels:
            return

        cmd = [
            "project",
            "channel",
            "add",
            "--manifest-path",
            str((project_dir / "pixi.toml").absolute()),
            *channels,
        ]
        self.exec(*cmd)

    def add_conda_packages(self, project_dir: Path, *packages: str) -> None:
        """
        Add conda packages to a pixi project.

        Args:
            project_dir: The pixi project directory.
            packages: The conda packages to add.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Pixi has not been installed
        """
        if not packages:
            return

        cmd = [
            "add",
            "--manifest-path",
            str((project_dir / "pixi.toml").absolute()),
            *packages,
        ]
        self.exec(*cmd)

    def add_pypi_packages(
        self, project_dir: Path, *packages: str, editable: bool = False
    ) -> None:
        """
        Add PyPI packages to a pixi project.

        Args:
            project_dir: The pixi project directory.
            packages: The PyPI packages to add.
            editable: Whether to install the packages in editable mode,
                which applies to packages given as local directories.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Pixi has not been installed
        """
        if not packages:
            return

        cmd = [
            "add",
            "--pypi",
            *(["--editable"] if editable else []),
            "--manifest-path",
            str((project_dir / "pixi.toml").absolute()),
            *packages,
        ]
        self.exec(*cmd)
