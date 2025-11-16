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
from typing import Callable


class Mamba:
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
    BASE_PATH = None  # TODO: Get from util.environment or similar

    # URL from where Micromamba is downloaded to be installed
    MICROMAMBA_URL = None  # TODO: Build based on platform detection

    def __init__(self, rootdir: str | None = None):
        """
        Create a new Mamba object.

        Args:
            rootdir: The root dir for Mamba installation. If None, uses BASE_PATH.
        """
        self.name = "micromamba"
        self.rootdir = rootdir if rootdir else self.BASE_PATH
        self.url = self.MICROMAMBA_URL
        self.command = self._build_command_path()

        # Consumers and configuration
        self.output_consumer: Callable[[str], None] | None = None
        self.error_consumer: Callable[[str], None] | None = None
        self.download_progress_consumer: Callable[[int, int], None] | None = None
        self.env_vars: dict[str, str] = {}
        self.flags: list[str] = []

        # Captured output
        self.captured_output: list[str] = []
        self.captured_error: list[str] = []

    def _build_command_path(self) -> str:
        """Build the path to the micromamba executable."""
        # TODO: Implement based on platform detection
        # Windows: Library/bin/micromamba.exe
        # Unix: bin/micromamba
        import platform

        if platform.system() == "Windows":
            return str(Path(self.rootdir) / "Library" / "bin" / "micromamba.exe")
        else:
            return str(Path(self.rootdir) / "bin" / "micromamba")

    def set_output_consumer(self, consumer: Callable[[str], None]) -> None:
        """Sets a consumer to receive standard output from the tool process."""
        self.output_consumer = consumer

    def set_error_consumer(self, consumer: Callable[[str], None]) -> None:
        """Sets a consumer to receive standard error from the tool process."""
        self.error_consumer = consumer

    def set_download_progress_consumer(
        self, consumer: Callable[[int, int], None]
    ) -> None:
        """Sets a consumer to track download progress during tool installation."""
        self.download_progress_consumer = consumer

    def set_env_vars(self, env_vars: dict[str, str]) -> None:
        """Sets environment variables to be passed to tool processes."""
        if env_vars:
            self.env_vars = dict(env_vars)

    def set_flags(self, flags: list[str]) -> None:
        """Sets additional command-line flags to pass to tool commands."""
        if flags:
            self.flags = list(flags)

    def version(self) -> str:
        """
        Get the version of the installed tool.

        Returns:
            The version string.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If the current thread is interrupted.
        """
        # TODO: Implement
        raise NotImplementedError("version() not yet implemented")

    def install(self) -> None:
        """
        Downloads and installs the external tool.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If interrupted during installation.
        """
        # TODO: Implement
        raise NotImplementedError("install() not yet implemented")

    def is_installed(self) -> bool:
        """
        Gets whether the tool is installed or not.

        Returns:
            True if the tool is installed, False otherwise.
        """
        try:
            self.version()
            return True
        except (IOError, InterruptedError, NotImplementedError):
            return False

    def exec(self, *args: str) -> None:
        """
        Executes a tool command with the specified arguments in the tool's root directory.

        Args:
            args: Command arguments for the tool.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If the current thread is interrupted.
            RuntimeError: If the tool has not been installed.
        """
        # TODO: Implement
        raise NotImplementedError("exec() not yet implemented")

    def create(self, env_dir: Path) -> None:
        """
        Creates an empty conda environment at the specified directory.
        This is useful for two-step builds: create empty, then update with environment.yml.

        Args:
            env_dir: The directory where the environment will be created.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If the current thread is interrupted.
            RuntimeError: if Micromamba has not been installed
        """
        self.exec("create", "--prefix", str(env_dir.absolute()), "-y", "--no-rc")

    def update(self, env_dir: Path, env_yaml: Path) -> None:
        """
        Updates an existing conda environment from an environment.yml file.

        Args:
            env_dir: The directory of the existing environment.
            env_yaml: Path to the environment.yml file.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If the current thread is interrupted.
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
