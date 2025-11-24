# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

# Adapted from JavaConda (https://github.com/javaconda/javaconda),
# which has the following license:

# Copyright (C) 2021, Ko Sugawara
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
Conda-based environment manager, implemented by delegating to micromamba.
"""

from __future__ import annotations

from pathlib import Path

from . import Tool
from ..util import download, filepath, platform


def _micromamba_platform() -> str | None:
    """Returns the platform string for micromamba download."""
    platform_str = platform.PLATFORM

    mapping = {
        "LINUX|X64": "linux-64",
        "LINUX|ARM64": "linux-aarch64",
        "LINUX|PPC64LE": "linux-ppc64le",
        "MACOS|X64": "osx-64",
        "MACOS|ARM64": "osx-arm64",
        "WINDOWS|X64": "win-64",
    }

    return mapping.get(platform_str)


class Mamba(Tool):
    """
    Conda-based environment manager, implemented by delegating to micromamba.

    It is expected that the Micromamba installation has executable commands as shown below:

        MAMBA_ROOT
        ├── bin
        │   ├── micromamba(.exe)
        │   ...
        ├── envs
        │   ├── your_env
        │   │   ├── python(.exe)
    """

    # Path where Appose installs Micromamba by default
    BASE_PATH: str = str(Path(filepath.appose_envs_dir()) / ".mamba")

    # The platform string for micromamba download
    PLATFORM: str | None = _micromamba_platform()

    # URL from where Micromamba is downloaded to be installed
    DOWNLOAD_URL: str | None = (
        f"https://micro.mamba.pm/api/micromamba/{PLATFORM}/latest" if PLATFORM else None
    )

    def __init__(self, rootdir: str | None = None):
        """
        Create a new Mamba object.

        Args:
            rootdir: The root dir for Mamba installation. If None, uses BASE_PATH.
        """
        root = rootdir if rootdir else self.BASE_PATH

        # Determine micromamba relative path based on platform
        if platform.is_windows():
            mamba_relative_path = Path("Library") / "bin" / "micromamba.exe"
        else:
            mamba_relative_path = Path("bin") / "micromamba"

        command_path = str(Path(root) / mamba_relative_path)

        super().__init__("micromamba", self.DOWNLOAD_URL, command_path, root)

    def _decompress(self, archive: Path) -> None:
        """
        Decompress and installs micromamba from the downloaded archive.

        Args:
            archive: Path to the downloaded archive file.

        Raises:
            IOError: If decompression/installation fails.
        """
        # Create mamba base directory
        mamba_base_dir = Path(self.rootdir)
        if not mamba_base_dir.is_dir():
            mamba_base_dir.mkdir(parents=True, exist_ok=True)

        # Extract archive
        download.unpack(archive, mamba_base_dir)

        # Verify micromamba binary exists
        mm_file = Path(self.command)
        if not mm_file.exists():
            raise IOError(f"Expected micromamba binary is missing: {self.command}")

        # Set executable permission if needed
        if not platform.is_executable(mm_file):
            mm_file.chmod(mm_file.stat().st_mode | 0o111)

    def create(self, env_dir: Path) -> None:
        """
        Create an empty conda environment at the specified directory.
        This is useful for two-step builds: create empty, then update with environment.yml.

        Args:
            env_dir: The directory where the environment will be created.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Micromamba has not been installed
        """
        self.exec("create", "--prefix", str(env_dir.absolute()), "-y", "--no-rc")

    def update(self, env_dir: Path, env_yaml: Path) -> None:
        """
        Update an existing conda environment from an environment.yml file.

        Args:
            env_dir: The directory of the existing environment.
            env_yaml: Path to the environment.yml file.

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: if Micromamba has not been installed
        """
        self.exec(
            "env",
            "update",
            "-y",
            "--prefix",
            str(env_dir.absolute()),
            "-f",
            str(env_yaml.absolute()),
        )
