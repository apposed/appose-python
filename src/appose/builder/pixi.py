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
Type-safe builder for Pixi-based environments.
"""

from __future__ import annotations

from pathlib import Path

from . import BaseBuilder, BuildException, Builder
from ..environment import Environment


class PixiBuilder(BaseBuilder):
    """
    Type-safe builder for Pixi-based environments.

    Pixi is a modern package manager supporting both conda and PyPI packages.
    """

    def __init__(self, source: str | None = None, scheme: str | None = None):
        super().__init__()
        self.conda_packages: list[str] = []
        self.pypi_packages: list[str] = []
        if source:
            self.file(source)
        if scheme:
            self.scheme = scheme

    def name(self) -> str:
        return "pixi"

    def conda(self, *packages: str) -> PixiBuilder:
        """
        Adds conda packages to the environment.

        Args:
            packages: Conda package specifications (e.g., "numpy", "python>=3.8")

        Returns:
            This builder instance
        """
        self.conda_packages.extend(packages)
        return self

    def pypi(self, *packages: str) -> PixiBuilder:
        """
        Adds PyPI packages to the environment.

        Args:
            packages: PyPI package specifications (e.g., "matplotlib", "requests==2.28.0")

        Returns:
            This builder instance
        """
        self.pypi_packages.extend(packages)
        return self

    def channels(self, *channels: str) -> PixiBuilder:
        """
        Adds conda channels to search for packages.

        Args:
            channels: Channel names (e.g., "conda-forge", "bioconda")

        Returns:
            This builder instance
        """
        return super().channels(*channels)

    def build(self) -> Environment:
        """
        Builds the Pixi environment.

        Returns:
            The newly constructed Environment

        Raises:
            BuildException: If the build fails
        """
        env_dir = self._env_dir()

        # Check if this is already a pixi project.
        is_pixi_dir = (
            (env_dir / "pixi.toml").is_file()
            or (env_dir / "pyproject.toml").is_file()
            or (env_dir / ".pixi").is_dir()
        )

        if (
            is_pixi_dir
            and self.source_content is None
            and not self.conda_packages
            and not self.pypi_packages
        ):
            # Environment already exists, just use it.
            return self._create_environment(env_dir)

        # Handle source-based build (file or content).
        if self.source_content is not None:
            if is_pixi_dir:
                # Already initialized, just use it.
                return self._create_environment(env_dir)

        # TODO: Implement actual Pixi environment building for new environments
        raise NotImplementedError(
            "PixiBuilder.build() is not yet fully implemented. "
            "Currently only supports wrapping existing environments."
        )

    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wraps an existing Pixi environment directory.

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

        # Look for pixi.toml configuration file first
        pixi_toml = env_path / "pixi.toml"
        if pixi_toml.exists() and pixi_toml.is_file():
            # Read the content so rebuild() will work even after directory is deleted
            with open(pixi_toml, "r", encoding="utf-8") as f:
                self.source_content = f.read()
            self.scheme = "pixi.toml"
        else:
            # Check for pyproject.toml
            pyproject_toml = env_path / "pyproject.toml"
            if pyproject_toml.exists() and pyproject_toml.is_file():
                # Read the content so rebuild() will work even after directory is deleted
                with open(pyproject_toml, "r", encoding="utf-8") as f:
                    self.source_content = f.read()
                self.scheme = "pyproject.toml"

        # Set the base directory and build (which will detect existing env)
        self.base(env_path)
        return self.build()

    def _create_environment(self, env_dir: Path) -> Environment:
        """
        Creates an Environment for the given Pixi directory.

        Args:
            env_dir: The Pixi environment directory

        Returns:
            Environment configured for this Pixi installation
        """
        base = str(env_dir.absolute())

        # Check which manifest file exists (pyproject.toml takes precedence)
        manifest_file = env_dir / "pyproject.toml"
        if not manifest_file.exists():
            manifest_file = env_dir / "pixi.toml"

        # pixi command - will be found via system PATH or installed pixi
        launch_args = [
            "pixi",
            "run",
            "--manifest-path",
            str(manifest_file.absolute()),
        ]
        bin_paths = [str(env_dir / ".pixi" / "envs" / "default" / "bin")]

        return self._create_env(base, bin_paths, launch_args)


class PixiBuilderFactory:
    """
    Factory for creating PixiBuilder instances.
    """

    def create_builder(
        self, source: str | None = None, scheme: str | None = None
    ) -> Builder:
        """
        Creates a new PixiBuilder instance.

        Args:
            source: Optional source file path
            scheme: Optional scheme

        Returns:
            A new PixiBuilder instance
        """
        return PixiBuilder(source, scheme)

    def name(self) -> str:
        return "pixi"

    def supports_scheme(self, scheme: str) -> bool:
        """
        Checks if this builder supports the given scheme.

        Args:
            scheme: The scheme to check

        Returns:
            True if supported
        """
        return scheme in ["pixi.toml", "environment.yml", "conda", "pypi"]

    def supports_source(self, source: str) -> bool:
        """
        Checks if this builder can build from the given source file.

        Args:
            source: The source file path

        Returns:
            True if supported
        """
        return (
            source.endswith("pixi.toml")
            or source.endswith(".yml")
            or source.endswith(".yaml")
        )

    def priority(self) -> float:
        """
        Returns the priority for this builder.

        Returns:
            Priority value (higher = more preferred)
        """
        return 100.0  # Preferred for environment.yml and conda/pypi packages

    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Checks if this builder can wrap the given environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this is a Pixi environment
        """
        env_path = Path(env_dir)
        return (env_path / ".pixi").is_dir() or (env_path / "pixi.toml").is_file()
