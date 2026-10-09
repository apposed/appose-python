# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
uv-based environment manager.
uv is a fast Python package installer and resolver written in Rust.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from ..util import download, environment, platform
from . import Tool


def _uv_binary() -> str | None:
    """Returns the filename to download for the current platform."""
    platform_str = platform.PLATFORM

    mapping = {
        "MACOS|ARM64": "uv-aarch64-apple-darwin.tar.gz",  # Apple Silicon macOS
        "MACOS|X64": "uv-x86_64-apple-darwin.tar.gz",  # Intel macOS
        "WINDOWS|ARM64": "uv-aarch64-pc-windows-msvc.zip",  # ARM64 Windows
        "WINDOWS|X32": "uv-i686-pc-windows-msvc.zip",  # x86 Windows
        "WINDOWS|X64": "uv-x86_64-pc-windows-msvc.zip",  # x64 Windows
        "LINUX|ARM64": "uv-aarch64-unknown-linux-gnu.tar.gz",  # ARM64 Linux
        "LINUX|X32": "uv-i686-unknown-linux-gnu.tar.gz",  # x86 Linux
        "LINUX|PPC64LE": "uv-powerpc64le-unknown-linux-gnu.tar.gz",  # PPC64LE Linux
        "LINUX|RV64GC": "uv-riscv64gc-unknown-linux-gnu.tar.gz",  # RISCV Linux
        "LINUX|S390X": "uv-s390x-unknown-linux-gnu.tar.gz",  # S390x Linux
        "LINUX|X64": "uv-x86_64-unknown-linux-gnu.tar.gz",  # x64 Linux
        "LINUX|ARMV7": "uv-armv7-unknown-linux-gnueabihf.tar.gz",  # ARMv7 Linux
        "LINUX|ARMV6": "uv-arm-unknown-linux-musleabihf.tar.gz",  # ARMv6 MUSL Linux
    }

    return mapping.get(platform_str)


class Uv(Tool):
    """
    uv-based environment manager.

    It is expected that the uv installation has executable commands as shown below:

        UV_ROOT
        ├── .uv
        │   ├── bin
        │   │   ├── uv(.exe)
    """

    # uv version to download
    UV_VERSION = "0.12.24"

    # Minimum acceptable uv version; older installations get upgraded to it
    MIN_VERSION: str = UV_VERSION

    # Environment variable which, when set to false, disables checking for newer releases
    AUTO_UPDATE_VAR: str = "APPOSE_UV_AUTO_UPDATE"

    # URL which redirects to the latest uv release
    LATEST_URL: str = "https://github.com/astral-sh/uv/releases/latest"

    # Path where Appose installs uv by default (.uv subdirectory thereof)
    BASE_PATH: str = environment.appose_envs_dir()

    # The filename to download for the current platform
    UV_BINARY: str | None = _uv_binary()

    # URL from where uv is downloaded to be installed
    DOWNLOAD_URL: str | None = (
        f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{UV_BINARY}"
        if UV_BINARY
        else None
    )

    def __init__(self, rootdir: str | None = None):
        """
        Create a new Uv object.

        Args:
            rootdir: The root dir for uv installation. If None, uses BASE_PATH.
        """
        root = rootdir if rootdir else self.BASE_PATH

        # Determine uv relative path based on platform
        if platform.is_windows():
            uv_relative_path = Path(".uv") / "bin" / "uv.exe"
        else:
            uv_relative_path = Path(".uv") / "bin" / "uv"

        command_path = str(Path(root) / uv_relative_path)

        super().__init__("uv", self.DOWNLOAD_URL, command_path, root)

    def _decompress(self, archive: Path) -> None:
        """
        Decompress and installs uv from the downloaded archive.

        Args:
            archive: Path to the downloaded archive file.

        Raises:
            IOError: If decompression/installation fails.
        """
        uv_bin_dir = Path(self.command).parent
        uv_bin_dir.mkdir(parents=True, exist_ok=True)

        # Note: Unpack to a staging directory and move the binaries into place,
        # rather than overwriting existing binaries in place, which can break
        # them while in use (and invalidates cached code signatures on macOS).
        with tempfile.TemporaryDirectory(dir=uv_bin_dir.parent) as staging:
            staging_dir = Path(staging)
            download.unpack(archive, staging_dir)

            # Windows ZIPs contain the binaries directly;
            # others contain them in a uv-<platform> subdirectory.
            platform_dirs = [
                f
                for f in staging_dir.iterdir()
                if f.is_dir() and f.name.startswith("uv-")
            ]
            source_dir = platform_dirs[0] if platform_dirs else staging_dir

            for binary in source_dir.iterdir():
                if not binary.is_file():
                    continue
                dest = uv_bin_dir / binary.name
                os.replace(binary, dest)
                if not platform.is_executable(dest):
                    dest.chmod(dest.stat().st_mode | 0o111)

        if not Path(self.command).exists():
            raise OSError(f"Expected uv binary is missing: {self.command}")

    def _latest_version(self) -> str | None:
        location = download.redirect_location(self.LATEST_URL)
        match = re.search(r"/tag/([^/]+)$", location or "")
        if not match:
            raise OSError(
                f"Could not determine latest uv release from {self.LATEST_URL}"
            )
        return match.group(1)

    def _download_url(self, version: str) -> str | None:
        if not self.UV_BINARY:
            return None
        return f"https://github.com/astral-sh/uv/releases/download/{version}/{self.UV_BINARY}"

    def create_venv(self, env_dir: Path, python_version: str | None = None) -> None:
        """
        Create a virtual environment using uv.

        Args:
            env_dir: The directory for the virtual environment.
            python_version: Optional Python version (e.g., "3.11"). Can be None for default.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if uv has not been installed
        """
        args = ["venv"]
        if python_version:
            args.extend(["--python", python_version])
        args.append(str(env_dir.absolute()))
        self.exec(*args)

    def pip_install(self, env_dir: Path, *packages: str) -> None:
        """
        Install PyPI packages into a virtual environment.

        Args:
            env_dir: The virtual environment directory.
            packages: The packages to install.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if uv has not been installed
        """
        if not packages:
            return
        args = ["pip", "install", "--python", str(env_dir.absolute()), *packages]
        self.exec(*args)

    def pip_install_from_requirements(
        self, env_dir: Path, requirements_file: str
    ) -> None:
        """
        Install packages from a requirements.txt file.

        Args:
            env_dir: The virtual environment directory.
            requirements_file: Path to requirements.txt file.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if uv has not been installed
        """
        self.exec(
            "pip",
            "install",
            "--python",
            str(env_dir.absolute()),
            "-r",
            requirements_file,
        )

    def sync(
        self,
        project_dir: Path,
        python_version: str | None = None,
        groups: list[str] | None = None,
    ) -> None:
        """
        Synchronize a project's dependencies from pyproject.toml.
        Create a virtual environment at projectDir/.venv and installs dependencies.

        Args:
            project_dir: The project directory containing pyproject.toml.
            python_version: Optional Python version (e.g., "3.11"). Can be None for default.
            groups: Optional PEP 735 dependency groups to include. Can be None for none.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if uv has not been installed
        """
        args = ["sync"]
        if python_version:
            args.extend(["--python", python_version])
        for group in groups or []:
            args.extend(["--group", group])

        # Run uv sync with working directory set to projectDir
        self.exec(*args, cwd=project_dir)
