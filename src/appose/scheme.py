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
Configuration file scheme detection and parsing.

This module provides classes for detecting and parsing different environment
configuration file formats (pixi.toml, environment.yml, pyproject.toml,
requirements.txt).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class Scheme(ABC):
    """
    Represents a configuration file scheme for environment builders.

    Each scheme encapsulates format-specific knowledge about a configuration file type
    (e.g., pixi.toml, pyproject.toml, environment.yml, requirements.txt).
    """

    @abstractmethod
    def name(self) -> str:
        """
        Gets the name of this scheme.

        Returns:
            The scheme name (e.g., "pixi.toml", "environment.yml")
        """
        ...

    @abstractmethod
    def priority(self) -> float:
        """
        Gets the priority of this scheme for detection ordering.

        Higher priority schemes are tested first. This ensures more specific
        schemes (e.g., pyproject.toml) are checked before less specific ones
        (e.g., generic pixi.toml).

        Returns:
            Priority value (higher = earlier detection)
        """
        ...

    @abstractmethod
    def env_name(self, content: str) -> str | None:
        """
        Extracts the environment name from configuration content.

        If no name is found in the content, returns None.

        Args:
            content: Configuration file content

        Returns:
            The environment name, or None if not found
        """
        ...

    @abstractmethod
    def supports_content(self, content: str) -> bool:
        """
        Tests whether this scheme can handle the given configuration content.

        Implementations should use heuristics to detect their format.

        Args:
            content: Configuration file content

        Returns:
            True if this scheme supports the content format
        """
        ...


class PixiTomlScheme(Scheme):
    """
    Scheme for pixi.toml configuration files.

    Pixi uses top-level [dependencies] and [pypi-dependencies] sections.
    """

    def name(self) -> str:
        return "pixi.toml"

    def priority(self) -> float:
        # Lower priority than pyproject.toml but higher than environment.yml and plain text.
        return 50.0

    def env_name(self, content: str) -> str | None:
        if not content:
            return None

        lines = content.split("\n")

        for line in lines:
            trimmed = line.strip()

            # Look for top-level name (not in any section).
            if trimmed.startswith("name") and "=" in trimmed:
                equals_index = trimmed.index("=")
                value = trimmed[equals_index + 1 :].strip()
                value = re.sub(r'^["\']|["\']$', "", value)
                if value:
                    return value

        return None

    def supports_content(self, content: str) -> bool:
        if not content:
            return False

        trimmed = content.strip()

        # Must have TOML structure.
        if not re.search(r"\[.*\]", trimmed, re.DOTALL):
            return False

        # Pixi-specific markers: top-level dependencies sections.
        return "[dependencies]" in trimmed or "[pypi-dependencies]" in trimmed


class EnvironmentYmlScheme(Scheme):
    """
    Scheme for environment.yml (conda/mamba) configuration files.
    """

    def name(self) -> str:
        return "environment.yml"

    def priority(self) -> float:
        # Higher priority than requirements.txt, but lower than pixi.toml and pyproject.toml.
        return 20.0

    def env_name(self, content: str) -> str | None:
        if not content:
            return None

        lines = content.split("\n")

        for line in lines:
            trimmed = line.strip()

            if trimmed.startswith("name:"):
                value = trimmed[5:].strip().replace('"', "")
                if value:
                    return value

        return None

    def supports_content(self, content: str) -> bool:
        if not content:
            return False

        trimmed = content.strip()

        # YAML format detection: starts with common conda keys or has key: value pattern.
        return (
            trimmed.startswith("name:")
            or trimmed.startswith("channels:")
            or trimmed.startswith("dependencies:")
            or bool(re.match(r"^[a-z_]+:\s*.*", trimmed, re.DOTALL))
        )


class PyProjectTomlScheme(Scheme):
    """
    Scheme for pyproject.toml configuration files (PEP 621 format).

    Supports both standard Python projects with [project.dependencies]
    and Pixi-flavored pyproject.toml with [tool.pixi.*] sections.
    """

    def name(self) -> str:
        return "pyproject.toml"

    def priority(self) -> float:
        # Higher priority than pixi.toml since pyproject.toml is more specific.
        return 100.0

    def env_name(self, content: str) -> str | None:
        if not content:
            return None

        lines = content.split("\n")
        in_project_section = False

        for line in lines:
            trimmed = line.strip()

            # Track if we're in a [project] section.
            if trimmed == "[project]":
                in_project_section = True
                continue
            elif trimmed.startswith("[") and not trimmed.startswith("[project"):
                in_project_section = False

            # Look for name in [project] section.
            if in_project_section and trimmed.startswith("name") and "=" in trimmed:
                equals_index = trimmed.index("=")
                value = trimmed[equals_index + 1 :].strip()
                value = re.sub(r'^["\']|["\']$', "", value)
                if value:
                    return value

        return None

    def supports_content(self, content: str) -> bool:
        if not content:
            return False

        trimmed = content.strip()

        # Must have TOML structure.
        if not re.search(r"\[.*\]", trimmed, re.DOTALL):
            return False

        # Must have [project] section.
        if "[project]" not in trimmed:
            return False

        # Must have either:
        # - Pixi-flavored: [tool.pixi.*]
        # - Standard PEP 621: [project.dependencies] or dependencies = in [project] section
        return (
            "[tool.pixi." in trimmed
            or "[project.dependencies]" in trimmed
            or bool(re.search(r"\[project\].*dependencies\s*=", trimmed, re.DOTALL))
        )


class RequirementsTxtScheme(Scheme):
    """
    Scheme for requirements.txt (pip) configuration files.

    This format does not contain environment name metadata.
    """

    def name(self) -> str:
        return "requirements.txt"

    def priority(self) -> float:
        # This scheme is less rich than the others, so don't prefer it.
        return 0.0

    def env_name(self, content: str) -> str | None:
        # requirements.txt does not contain environment name metadata.
        return None

    def supports_content(self, content: str) -> bool:
        if not content:
            return False

        trimmed = content.strip()

        # Plain text list of package specifications.
        # Must start with package name (alphanumeric, underscore, or hyphen).
        # Optionally followed by version specifiers.
        return bool(re.match(r"^[a-zA-Z0-9_-]+(==|>=|<=|~=|!=)?", trimmed, re.DOTALL))


# All known scheme implementations, in priority order.
# More specific schemes should come first to ensure correct detection.
# For example, pyproject.toml must be checked before pixi.toml
# since both are TOML files but pyproject.toml has more specific markers.
_SCHEMES: list[Scheme] = sorted(
    [
        PixiTomlScheme(),
        EnvironmentYmlScheme(),
        PyProjectTomlScheme(),
        RequirementsTxtScheme(),
    ],
    key=lambda s: s.priority(),
    reverse=True,
)


def from_content(content: str) -> Scheme:
    """
    Detects and returns the appropriate scheme for the given configuration content.

    Args:
        content: Configuration file content

    Returns:
        The matching scheme

    Raises:
        ValueError: If no scheme can handle the content
    """
    for scheme in _SCHEMES:
        if scheme.supports_content(content):
            return scheme

    raise ValueError(
        "Cannot infer scheme from content. Please specify explicitly with .scheme()"
    )


def from_name(name: str) -> Scheme:
    """
    Returns the scheme with the given name.

    Args:
        name: Scheme name (e.g., "pixi.toml", "environment.yml")

    Returns:
        The matching scheme

    Raises:
        ValueError: If no scheme matches the name
    """
    for scheme in _SCHEMES:
        if scheme.name() == name:
            return scheme

    raise ValueError(f"Unknown scheme: {name}")
