# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Base class for external tool helpers (Mamba, Pixi, uv, etc.).
Provides common functionality for process execution, stream handling,
and progress tracking.
"""

from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from ..util import download, platform, process

# Environment variable which, when set to false, disables checking for newer
# releases of all tools; tool-specific variables (e.g. APPOSE_PIXI_AUTO_UPDATE)
# take precedence over it
TOOL_AUTO_UPDATE_VAR = "APPOSE_TOOL_AUTO_UPDATE"


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parses a version string like "v0.81.0" into a comparable tuple of ints."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


class Tool(ABC):
    """
    Base class for external tool helpers.
    Provides common interface for process execution and installation.
    """

    # Minimum acceptable version; older installations get upgraded to it
    MIN_VERSION: str | None = None

    # Minimum number of seconds between checks for a newer release
    UPDATE_INTERVAL: float = 24 * 60 * 60

    # Environment variable which, when set to false, disables checking for
    # newer releases of this tool; overrides the blanket TOOL_AUTO_UPDATE_VAR
    AUTO_UPDATE_VAR: str | None = None

    def __init__(self, name: str, url: str, command: str, rootdir: str):
        """
        Initialize a Tool instance.

        Args:
            name: The name of the external tool (e.g. uv, pixi, micromamba).
            url: Remote URL to use when downloading the tool.
            command: Path to the tool's executable command.
            rootdir: Root directory where the tool is installed.
        """
        self.name: str = name
        self.url: str = url
        self.command: str = command
        self.rootdir: str = rootdir

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
        Set a consumer to receive standard output from the tool process.

        Args:
            consumer: Consumer that processes output strings.
        """
        self._output_consumer = consumer

    def set_error_consumer(self, consumer: Callable[[str], None]) -> None:
        """
        Set a consumer to receive standard error from the tool process.

        Args:
            consumer: Consumer that processes error strings.
        """
        self._error_consumer = consumer

    def set_download_progress_consumer(
        self, consumer: Callable[[int, int], None]
    ) -> None:
        """
        Set a consumer to track download progress during tool installation.

        Args:
            consumer: Consumer that receives (current, total) progress updates.
        """
        self._download_progress_consumer = consumer

    def set_env_vars(self, env_vars: dict[str, str]) -> None:
        """
        Set environment variables to be passed to tool processes.

        Args:
            env_vars: Dictionary of environment variable names to values.
        """
        if env_vars is not None:
            self._env_vars = dict(env_vars)

    def set_flags(self, flags: list[str]) -> None:
        """
        Set additional command-line flags to pass to tool commands.

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
        Download and installs the external tool.

        Raises:
            IOError: If an I/O error occurs.
        """
        if self.is_installed():
            return

        archive = self._download()
        self._decompress(archive)

    def self_update(self) -> None:
        """
        Upgrade the installed tool, if warranted.

        The tool is upgraded to the latest release, at most once per
        UPDATE_INTERVAL, unless auto-updating is disabled: the tool's own
        AUTO_UPDATE_VAR environment variable (e.g. APPOSE_PIXI_AUTO_UPDATE)
        or else the blanket APPOSE_TOOL_AUTO_UPDATE variable is set to false.
        Regardless, the tool is upgraded to at least MIN_VERSION, if any, so
        that it understands state written by newer installations of the tool
        elsewhere on the system.

        Failures (e.g. due to no network connection) are reported to the error
        consumer, but not raised, so that builds can proceed with the existing tool.

        Raises:
            IOError: If the tool is not installed.
        """
        if self._auto_update_enabled() and self._update_check_due():
            self._try_upgrade(None)

        if self.MIN_VERSION is not None and _version_tuple(
            self.version()
        ) < _version_tuple(self.MIN_VERSION):
            self._try_upgrade(self.MIN_VERSION)

    def is_installed(self) -> bool:
        """
        Get whether the tool is installed or not.

        Returns:
            True if the tool is installed, False otherwise.
        """
        try:
            self.version()
            return True
        except Exception:  # noqa: BLE001 -- any failure to run/parse version means "not installed"
            return False

    def exec(self, *args: str, cwd: Path | None = None) -> None:
        """
        Execute a tool command with the specified arguments.

        Args:
            *args: Command arguments for the tool.
            cwd: Working directory for the command (None to use tool's root directory).

        Raises:
            IOError: If an I/O error occurs.
            RuntimeError: If the tool has not been installed.
        """
        if not self.is_installed():
            command_path = Path(self.command)
            if command_path.is_file():
                raise RuntimeError(
                    f'{self.name} is installed at "{self.command}"'
                    " but could not be run -- the path may contain characters"
                    " that are special to the shell (e.g. parentheses on Windows)"
                )
            raise RuntimeError(
                f"{self.name} is not installed"
                f' (expected executable at "{self.command}")'
            )

        self._do_exec(cwd=cwd, silent=False, include_flags=True, args=args)

    def _exec_direct(self, *args: str) -> None:
        """
        Execute a tool command with the specified arguments, without validating the
        tool installation beforehand, without passing output to external listeners
        (see set_output_consumer and set_error_consumer), and without including flags.

        This method mainly exists for version() checking, and subclasses of Tool are
        unlikely to need it—they should probably use exec(...) instead.

        Args:
            *args: Command arguments for the tool.

        Raises:
            IOError: If an I/O error occurs.
        """
        self._do_exec(cwd=None, silent=True, include_flags=False, args=args)

    def _download(self) -> Path:
        """
        Download the tool from its URL.

        Returns:
            Path to the downloaded file.

        Raises:
            IOError: If download fails or URL is not available for this platform.
        """
        if self.url is None:
            raise OSError(
                f"{self.name} is not available for this platform ({platform.PLATFORM}). "
                "Please install it manually."
            )
        return self._download_from(self.url)

    def _download_from(self, url: str) -> Path:
        return download.download(self.name, url, self._update_download_progress)

    def _upgrade(self, version: str | None) -> None:
        """
        Upgrade the installed tool to the given version.

        This default implementation downloads the requested release from
        _download_url and installs it over the existing one via _decompress.
        Subclasses whose tool can upgrade itself may override it.

        Args:
            version: The version to upgrade to, or None for the latest release.

        Raises:
            IOError: If the upgrade fails.
        """
        if version is None:
            version = self._latest_version()
            if version is None or _version_tuple(self.version()) >= _version_tuple(
                version
            ):
                return
        url = self._download_url(version)
        if url is None:
            return
        self._output(f"Updating {self.name} to {version}\n")
        archive = self._download_from(url)
        self._decompress(archive)

    def _latest_version(self) -> str | None:
        """
        Get the version of the tool's latest release.

        Returns:
            The latest version, or None if this tool cannot check for newer releases.

        Raises:
            IOError: If the check fails.
        """
        return None

    def _download_url(self, version: str) -> str | None:
        """
        Get the URL from which the given release of the tool can be downloaded.

        Args:
            version: The release version.

        Returns:
            The download URL, or None if unavailable.
        """
        return None

    def _try_upgrade(self, version: str | None) -> None:
        try:
            self._upgrade(version)
        except OSError:
            # Note: The tool's own error output has already gone to the error consumer.
            self._error(
                f"Warning: could not update {self.name}; continuing with the installed version.\n"
            )

    def _auto_update_enabled(self) -> bool:
        for var in (self.AUTO_UPDATE_VAR, TOOL_AUTO_UPDATE_VAR):
            value = os.environ.get(var, "").strip().lower() if var else ""
            if value:
                return value not in ("0", "false", "no", "off")
        return True

    def _update_check_due(self) -> bool:
        """
        Check whether UPDATE_INTERVAL has elapsed since the last update check,
        recording the current time as the latest check if so.
        """
        stamp = Path(self.command).parent / "last-update-check"
        now = time.time()
        try:
            elapsed = now - stamp.stat().st_mtime
            if 0 <= elapsed < self.UPDATE_INTERVAL:
                return False
        except OSError:
            pass  # No previous check recorded.
        try:
            # Note: Record the check even if it fails, so that
            # being offline does not cause a failed check every time.
            stamp.touch()
            # Note: Stamp the time we compare against, not the filesystem's
            # own, which can run ahead of time.time() (e.g. on Windows).
            os.utime(stamp, (now, now))
        except OSError:
            pass
        return True

    @abstractmethod
    def _decompress(self, archive: Path) -> None:
        """
        Decompress and installs the tool from the downloaded archive.

        Args:
            archive: Path to the downloaded archive file.

        Raises:
            IOError: If decompression/installation fails.
        """

    def _output(self, line: str) -> None:
        """
        Handle a line from the tool's standard output stream.

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
        Handle a line from the tool's standard error stream.

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
        Update the download progress consumer, if one is registered.

        Args:
            current: Current progress value.
            total: Total progress value.
        """
        if self._download_progress_consumer:
            self._download_progress_consumer(current, total)

    def _do_exec(
        self, cwd: Path | None, silent: bool, include_flags: bool, args: tuple[str, ...]
    ) -> None:
        """
        Execute a tool command with the specified arguments.

        Args:
            cwd: Working directory for the command (None to use tool's root directory).
            silent: If False, pass command output along to external listeners.
            include_flags: If True, include self._flags in the command argument list.
            args: Command arguments for the tool.

        Raises:
            IOError: If an I/O error occurs or command fails.
        """
        # Clear captured output from previous command
        self._captured_output.clear()
        self._captured_error.clear()

        # Build command
        cmd = platform.command(self.command)
        if include_flags:
            cmd.extend(self._flags)
        cmd.extend(args)

        # Determine working directory
        working_dir = Path(cwd) if cwd else Path(self.rootdir)

        # Set up output handlers
        if silent:
            output_handler = lambda line: self._captured_output.append(line)
            error_handler = lambda line: self._captured_error.append(line)
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

            raise OSError("".join(error_msg))
