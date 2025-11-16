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
Base class for external tool helpers (Mamba, Pixi, uv, etc.).
Provides common functionality for process execution, stream handling,
and progress tracking.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from ..util import platform, process, download


class Tool(ABC):
    """
    Base class for external tool helpers.
    Provides common interface for process execution and installation.
    """

    def __init__(self, name: str, url: str, command: str, rootdir: str):
        """
        Initialize a Tool instance.

        Args:
            name: The name of the external tool (e.g. uv, pixi, micromamba).
            url: Remote URL to use when downloading the tool.
            command: Path to the tool's executable command.
            rootdir: Root directory where the tool is installed.
        """
        self.name = name
        self.url = url
        self.command = command
        self.rootdir = rootdir

        # Consumer callbacks
        self._output_consumer: Callable[[str], None] | None = None
        self._error_consumer: Callable[[str], None] | None = None
        self._download_progress_consumer: Callable[[int, int], None] | None = None

        # Environment variables and flags
        self._env_vars: dict[str, str] = {}
        self._flags: list[str] = []

        # Captured output
        self._captured_output: list[str] = []
        self._captured_error: list[str] = []

    def set_output_consumer(self, consumer: Callable[[str], None]) -> None:
        """
        Sets a consumer to receive standard output from the tool process.

        Args:
            consumer: Consumer that processes output strings.
        """
        self._output_consumer = consumer

    def set_error_consumer(self, consumer: Callable[[str], None]) -> None:
        """
        Sets a consumer to receive standard error from the tool process.

        Args:
            consumer: Consumer that processes error strings.
        """
        self._error_consumer = consumer

    def set_download_progress_consumer(
        self, consumer: Callable[[int, int], None]
    ) -> None:
        """
        Sets a consumer to track download progress during tool installation.

        Args:
            consumer: Consumer that receives (current, total) progress updates.
        """
        self._download_progress_consumer = consumer

    def set_env_vars(self, env_vars: dict[str, str]) -> None:
        """
        Sets environment variables to be passed to tool processes.

        Args:
            env_vars: Dictionary of environment variable names to values.
        """
        if env_vars is not None:
            self._env_vars = dict(env_vars)

    def set_flags(self, flags: list[str]) -> None:
        """
        Sets additional command-line flags to pass to tool commands.

        Args:
            flags: List of command-line flags.
        """
        if flags is not None:
            self._flags = list(flags)

    def version(self) -> str:
        """
        Get the version of the installed tool.

        This default implementation calls the tool with --version and
        extracts the first whitespace-delimited token that starts with a digit.
        Subclasses can override this method if their tool uses a different
        version reporting format.

        Returns:
            The version string.

        Raises:
            IOError: If an I/O error occurs.
        """
        # Example output of supported tools with --version flag:
        # - 2.3.3
        # - pixi 0.58.0
        # - uv 0.5.25 (9c07c3fc5 2025-01-28)
        self._exec_direct("--version")
        output = "".join(self._captured_output)

        for token in output.split():
            if token and token[0].isdigit():
                return token  # starts with a digit

        return output.strip()

    def install(self) -> None:
        """
        Downloads and installs the external tool.

        Raises:
            IOError: If an I/O error occurs.
        """
        if self.is_installed():
            return

        archive = self._download()
        self._decompress(archive)

    def is_installed(self) -> bool:
        """
        Gets whether the tool is installed or not.

        Returns:
            True if the tool is installed, False otherwise.
        """
        try:
            self.version()
            return True
        except Exception:
            return False

    def exec(self, *args: str, cwd: Path | None = None) -> None:
        """
        Executes a tool command with the specified arguments.

        Args:
            *args: Command arguments for the tool.
            cwd: Working directory for the command (None to use tool's root directory).

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: If the tool has not been installed.
        """
        if not self.is_installed():
            raise RuntimeError(f"{self.name} is not installed")

        self._do_exec(cwd, silent=False, include_flags=True, *args)

    def _exec_direct(self, *args: str) -> None:
        """
        Executes a tool command without validating installation,
        without passing output to external listeners, and without including flags.

        Args:
            *args: Command arguments for the tool.

        Raises:
            IOError: If an I/O error occurs.
        """
        self._do_exec(None, silent=True, include_flags=False, *args)

    def _download(self) -> Path:
        """
        Downloads the tool from its URL.

        Returns:
            Path to the downloaded file.

        Raises:
            IOError: If download fails.
        """
        return download.download(self.name, self.url, self._update_download_progress)

    @abstractmethod
    def _decompress(self, archive: Path) -> None:
        """
        Decompresses and installs the tool from the downloaded archive.

        Args:
            archive: Path to the downloaded archive file.

        Raises:
            IOError: If decompression/installation fails.
        """
        pass

    def _output(self, line: str) -> None:
        """
        Handles a line from the tool's standard output stream.

        - Captures the output for later inclusion in error messages.
        - Updates the output consumer with a message, if one is registered.

        Args:
            line: The line of stdout to process.
        """
        if line:
            self._captured_output.append(line)
            if self._output_consumer:
                self._output_consumer(line)

    def _error(self, line: str) -> None:
        """
        Handles a line from the tool's standard error stream.

        - Captures the error for later inclusion in error messages.
        - Updates the error consumer with a message, if one is registered.

        Args:
            line: The line of stderr to process.
        """
        if line:
            self._captured_error.append(line)
            if self._error_consumer:
                self._error_consumer(line)

    def _update_download_progress(self, current: int, total: int) -> None:
        """
        Updates the download progress consumer, if one is registered.

        Args:
            current: Current progress value.
            total: Total progress value.
        """
        if self._download_progress_consumer:
            self._download_progress_consumer(current, total)

    def _do_exec(
        self, cwd: Path | None, silent: bool, include_flags: bool, *args: str
    ) -> None:
        """
        Executes a tool command with the specified arguments.

        Args:
            cwd: Working directory for the command (None to use tool's root directory).
            silent: If False, pass command output along to external listeners.
            include_flags: If True, include self._flags in the command argument list.
            *args: Command arguments for the tool.

        Raises:
            IOError: If an I/O error occurs or command fails.
        """
        # Clear captured output from previous command
        self._captured_output.clear()
        self._captured_error.clear()

        # Build command
        cmd = platform.base_command()
        cmd.append(self.command)
        if include_flags:
            cmd.extend(self._flags)
        cmd.extend(args)

        # Determine working directory
        working_dir = Path(cwd) if cwd else Path(self.rootdir)

        # Set up output handlers
        if silent:
            output_handler = lambda line: self._captured_output.append(line)  # noqa: E731
            error_handler = lambda line: self._captured_error.append(line)  # noqa: E731
        else:
            output_handler = self._output
            error_handler = self._error

        # Execute command
        exit_code = process.run(
            cmd,
            cwd=working_dir,
            env=self._env_vars,
            output_consumer=output_handler,
            error_consumer=error_handler,
        )

        # Check exit code
        if exit_code != 0:
            error_msg = [
                f"{self.name} command failed with exit code {exit_code}: {' '.join(args)}"
            ]

            # Include stderr if available
            stderr = "".join(self._captured_error).strip()
            if stderr:
                error_msg.append(f"\n\nError output:\n{stderr}")

            # Include stdout if available and stderr was empty
            stdout = "".join(self._captured_output).strip()
            if not stderr and stdout:
                error_msg.append(f"\n\nOutput:\n{stdout}")

            raise IOError("".join(error_msg))
