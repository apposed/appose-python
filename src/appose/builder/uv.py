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
Type-safe builder for uv-based virtual environments.
"""

from __future__ import annotations

from pathlib import Path

from . import BaseBuilder, BuildException, Builder
from ..environment import Environment


class UvBuilder(BaseBuilder):
    """
    Type-safe builder for uv-based virtual environments.

    uv is a fast Python package installer and resolver.
    """

    def __init__(self, source: str | None = None, scheme: str | None = None):
        super().__init__()
        self.python_version: str | None = None
        self.packages: list[str] = []
        if source:
            self.file(source)
        if scheme:
            self.scheme = scheme

    def name(self) -> str:
        return "uv"

    def python(self, version: str) -> UvBuilder:
        """
        Specifies the Python version to use for the virtual environment.

        Args:
            version: Python version (e.g., "3.11", "3.10")

        Returns:
            This builder instance
        """
        self.python_version = version
        return self

    def include(self, *packages: str) -> UvBuilder:
        """
        Adds PyPI packages to install in the virtual environment.

        Args:
            packages: PyPI package specifications (e.g., "numpy", "requests==2.28.0")

        Returns:
            This builder instance
        """
        self.packages.extend(packages)
        return self

    def channels(self, *indexes: str) -> UvBuilder:
        """
        Adds PyPI index URLs for package discovery.

        These are alternative or additional package indexes beyond the default pypi.org.

        Args:
            indexes: Index URLs (e.g., custom PyPI mirrors or private package repositories)

        Returns:
            This builder instance
        """
        return super().channels(*indexes)

    def build(self) -> Environment:
        """
        Builds the uv environment.

        Returns:
            The newly constructed Environment

        Raises:
            BuildException: If the build fails
        """
        env_dir = self._env_dir()

        # Check if this is already a uv virtual environment.
        is_uv_venv = (env_dir / "pyvenv.cfg").is_file()

        if is_uv_venv and self.source_content is None and not self.packages:
            # Environment already exists and no new config/packages, just use it.
            return self._create_environment(env_dir)

        # TODO: Implement actual uv environment building for new environments
        raise NotImplementedError(
            "UvBuilder.build() is not yet fully implemented. "
            "Currently only supports wrapping existing environments."
        )

    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wraps an existing uv/venv environment directory.

        Args:
            env_dir: The existing environment directory to wrap

        Returns:
            The wrapped Environment

        Raises:
            BuildException: If the directory doesn't exist or can't be wrapped
        """
        env_path = Path(env_dir)
        if not env_path.exists() or not env_path.is_dir():
            raise BuildException(self, f"Directory does not exist: {env_dir}")

        # Check for pyproject.toml first (preferred for uv projects)
        pyproject_toml = env_path / "pyproject.toml"
        if pyproject_toml.exists() and pyproject_toml.is_file():
            # Read the content so rebuild() will work even after directory is deleted
            with open(pyproject_toml, "r", encoding="utf-8") as f:
                self.source_content = f.read()
            self.scheme = "pyproject.toml"
        else:
            # Fall back to requirements.txt
            requirements_txt = env_path / "requirements.txt"
            if requirements_txt.exists() and requirements_txt.is_file():
                # Read the content so rebuild() will work even after directory is deleted
                with open(requirements_txt, "r", encoding="utf-8") as f:
                    self.source_content = f.read()
                self.scheme = "requirements.txt"

        # Set the base directory and build (which will detect existing env)
        self.base(env_path)
        return self.build()

    def _create_environment(self, env_dir: Path) -> Environment:
        """
        Creates an Environment for the given uv/venv directory.

        Args:
            env_dir: The uv/venv environment directory

        Returns:
            Environment configured for this uv/venv installation
        """
        from ..util.platform import is_windows

        base = str(env_dir.absolute())

        # Determine venv location based on project structure.
        # If .venv exists, it's a pyproject.toml-managed project (uv sync).
        # Otherwise, env_dir itself is the venv (uv venv + pip install).
        venv_dir = env_dir / ".venv"
        actual_venv_dir = venv_dir if venv_dir.exists() else env_dir

        # uv virtual environments use standard venv structure.
        bin_dir = "Scripts" if is_windows() else "bin"
        bin_paths = [str(actual_venv_dir / bin_dir)]

        # No special launch args needed - executables are directly in bin/Scripts.
        launch_args = []

        return self._create_env(base, bin_paths, launch_args)


class UvBuilderFactory:
    """
    Factory for creating UvBuilder instances.
    """

    def create_builder(
        self, source: str | None = None, scheme: str | None = None
    ) -> Builder:
        """
        Creates a new UvBuilder instance.

        Args:
            source: Optional source file path
            scheme: Optional scheme

        Returns:
            A new UvBuilder instance
        """
        return UvBuilder(source, scheme)

    def name(self) -> str:
        return "uv"

    def supports_scheme(self, scheme: str) -> bool:
        """
        Checks if this builder supports the given scheme.

        Args:
            scheme: The scheme to check

        Returns:
            True if supported
        """
        return scheme in ["requirements.txt", "pypi"]

    def supports_source(self, source: str) -> bool:
        """
        Checks if this builder can build from the given source file.

        Args:
            source: The source file path

        Returns:
            True if supported
        """
        return source.endswith("requirements.txt") or source.endswith(".txt")

    def priority(self) -> float:
        """
        Returns the priority for this builder.

        Returns:
            Priority value (higher = more preferred)
        """
        return 75.0  # Between pixi (100) and mamba (50)

    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Checks if this builder can wrap the given environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this is a uv/venv environment
        """
        env_path = Path(env_dir)
        # uv creates standard Python venv, so look for pyvenv.cfg,
        # but exclude conda and pixi environments
        has_pyvenv_cfg = (env_path / "pyvenv.cfg").is_file()
        is_not_pixi = (
            not (env_path / ".pixi").is_dir() and not (env_path / "pixi.toml").is_file()
        )
        is_not_conda = not (env_path / "conda-meta").is_dir()

        return has_pyvenv_cfg and is_not_pixi and is_not_conda
