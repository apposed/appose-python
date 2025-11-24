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

"""
Pixi-based environment manager.
Pixi is a modern package management tool that provides better environment
management than micromamba and supports both conda and PyPI packages.
"""

from __future__ import annotations

from pathlib import Path

from . import Tool
from ..util import download, filepath, platform


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
    PIXI_VERSION: str = "v0.58.0"

    # Path where Appose installs Pixi by default (.pixi subdirectory thereof)
    BASE_PATH: str = filepath.appose_envs_dir()

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
            raise IOError(f"Expected pixi binary is missing: {self.command}")

        # Set executable permission if needed
        if not platform.is_executable(pixi_file):
            pixi_file.chmod(pixi_file.stat().st_mode | 0o111)

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

    def add_pypi_packages(self, project_dir: Path, *packages: str) -> None:
        """
        Add PyPI packages to a pixi project.

        Args:
            project_dir: The pixi project directory.
            packages: The PyPI packages to add.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Pixi has not been installed
        """
        if not packages:
            return

        cmd = [
            "add",
            "--pypi",
            "--manifest-path",
            str((project_dir / "pixi.toml").absolute()),
            *packages,
        ]
        self.exec(*cmd)
