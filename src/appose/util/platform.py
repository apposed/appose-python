# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions and constants for platform-specific logic.
"""

from __future__ import annotations

import os
import platform
from enum import Enum
from pathlib import Path


class OperatingSystem(Enum):
    """Operating system types."""

    LINUX = "LINUX"
    MACOS = "MACOS"
    WINDOWS = "WINDOWS"
    UNKNOWN = "UNKNOWN"


class CpuArchitecture(Enum):
    """CPU architecture types."""

    ARM64 = "ARM64"
    ARMV6 = "ARMV6"
    ARMV7 = "ARMV7"
    PPC64 = "PPC64"
    PPC64LE = "PPC64LE"
    RV64GC = "RV64GC"
    S390X = "S390X"
    X32 = "X32"
    X64 = "X64"
    UNKNOWN = "UNKNOWN"


def _detect_os() -> OperatingSystem:
    """Detects the current operating system."""
    system = platform.system().lower()
    if "linux" in system or system.endswith("ix"):
        return OperatingSystem.LINUX
    elif system in ("darwin", "macos") or system.startswith("darwin"):
        return OperatingSystem.MACOS
    elif system.startswith("windows") or "win32" in system:
        return OperatingSystem.WINDOWS
    else:
        return OperatingSystem.UNKNOWN


def _detect_arch() -> CpuArchitecture:
    """Detects the current CPU architecture."""
    machine = platform.machine().lower()

    if machine in ("aarch64", "arm64"):
        return CpuArchitecture.ARM64
    elif machine in ("arm", "armv6"):
        return CpuArchitecture.ARMV6
    elif machine in ("aarch32", "arm32", "armv7", "armv7l"):
        return CpuArchitecture.ARMV7
    elif machine in ("powerpc64", "ppc64"):
        return CpuArchitecture.PPC64
    elif machine in ("powerpc64le", "ppc64le"):
        return CpuArchitecture.PPC64LE
    elif machine in ("riscv64", "riscv64gc", "rv64gc"):
        return CpuArchitecture.RV64GC
    elif machine in ("s390x",):
        return CpuArchitecture.S390X
    elif machine in ("i386", "i486", "i586", "i686", "x32", "x86", "x86-32", "x86_32"):
        return CpuArchitecture.X32
    elif machine in ("amd64", "x86-64", "x86_64", "x64"):
        return CpuArchitecture.X64
    else:
        return CpuArchitecture.UNKNOWN


# Module-level constants
OS: OperatingSystem = _detect_os()
"""The detected operating system."""

ARCH: CpuArchitecture = _detect_arch()
"""The detected CPU architecture."""

PLATFORM: str = f"{OS.value}|{ARCH.value}"
"""A string of the form 'OS|ARCH'."""


def is_windows() -> bool:
    """Returns True if running on Windows."""
    return OS == OperatingSystem.WINDOWS


def is_macos() -> bool:
    """Returns True if running on macOS."""
    return OS == OperatingSystem.MACOS


def is_linux() -> bool:
    """Returns True if running on Linux."""
    return OS == OperatingSystem.LINUX


def is_executable(file: Path) -> bool:
    """
    Check if a file is executable.

    On Windows, this checks for .exe extension.
    On POSIX systems, this checks the executable bit.

    Args:
        file: The file to check.

    Returns:
        True if the file exists and is executable, False otherwise.
    """
    if OS == OperatingSystem.WINDOWS:
        # On Windows, check for .exe extension
        return file.exists() and file.name.lower().endswith(".exe")
    else:
        # On POSIX, check executable bit
        return file.exists() and os.access(file, os.X_OK)


def base_command() -> list[str]:
    """
    Get the arguments to prefix to execute a command in a separate process.

    Returns:
        ['cmd.exe', '/c'] for Windows and an empty list otherwise.
    """
    if is_windows():
        return ["cmd.exe", "/c"]
    return []
