# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions for working with environments.
"""

from __future__ import annotations

import os


def env_vars(*keys: str) -> dict[str, str]:
    """
    Retrieves the specified environment variables from the current process.
    Only variables that are set will be included in the returned map.

    Args:
        keys: The names of environment variables to retrieve.

    Returns:
        A dictionary containing the requested environment variables and their values.
        Variables that are not set will be omitted from the dictionary.
    """
    result = {}
    for key in keys:
        value = os.environ.get(key)
        if value is not None:
            result[key] = value
    return result


def system_path() -> list[str]:
    """
    Returns the current process's system PATH as a list of directory paths.

    This splits the PATH environment variable on the platform-specific separator
    (colon on Unix-like systems, semicolon on Windows).

    Returns:
        List of directory paths from the system PATH, or empty list if PATH is not set.
    """
    path_env = os.environ.get("PATH")
    if not path_env:
        return []

    separator = os.pathsep
    return path_env.split(separator)
