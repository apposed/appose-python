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
uv-based environment manager.
uv is a fast Python package installer and resolver written in Rust.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


class Uv:
    """
    uv-based environment manager.

    It is expected that the uv installation has executable commands as shown below:

        UV_ROOT
        ├── .uv
        │   ├── bin
        │   │   ├── uv(.exe)
    """

    # uv version to download
    UV_VERSION = "0.9.5"

    # Path where Appose installs uv by default (.uv subdirectory thereof)
    BASE_PATH = None  # TODO: Get from util.environment or similar

    # URL from where uv is downloaded to be installed
    UV_URL = None  # TODO: Build based on platform detection

    def __init__(self, rootdir: str | None = None):
        """
        Create a new Uv object.

        Args:
            rootdir: The root dir for uv installation. If None, uses BASE_PATH.
        """
        self.name = "uv"
        self.rootdir = rootdir if rootdir else self.BASE_PATH
        self.url = self.UV_URL
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
        """Build the path to the uv executable."""
        # TODO: Implement based on platform detection
        # Windows: .uv/bin/uv.exe
        # Unix: .uv/bin/uv
        import platform

        if platform.system() == "Windows":
            return str(Path(self.rootdir) / ".uv" / "bin" / "uv.exe")
        else:
            return str(Path(self.rootdir) / ".uv" / "bin" / "uv")

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

    def create_venv(self, env_dir: Path, python_version: str | None = None) -> None:
        """
        Create a virtual environment using uv.

        Args:
            env_dir: The directory for the virtual environment.
            python_version: Optional Python version (e.g., "3.11"). Can be None for default.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If the current thread is interrupted.
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
            InterruptedError: If the current thread is interrupted.
            RuntimeError: if uv has not been installed
        """
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
            InterruptedError: If the current thread is interrupted.
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

    def sync(self, project_dir: Path, python_version: str | None = None) -> None:
        """
        Synchronize a project's dependencies from pyproject.toml.
        Creates a virtual environment at projectDir/.venv and installs dependencies.

        Args:
            project_dir: The project directory containing pyproject.toml.
            python_version: Optional Python version (e.g., "3.11"). Can be None for default.

        Raises:
            IOError: If an I/O error occurs.
            InterruptedError: If the current thread is interrupted.
            RuntimeError: if uv has not been installed
        """
        args = ["sync"]
        if python_version:
            args.extend(["--python", python_version])

        # Run uv sync with working directory set to projectDir.
        # TODO: This would need exec() to support a cwd parameter
        self.exec(*args)
