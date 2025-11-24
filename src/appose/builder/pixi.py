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

from . import BaseBuilder, BuildException, Builder, BuilderFactory
from ..environment import Environment
from ..scheme import from_content as scheme_from_content
from ..tool.pixi import Pixi


class PixiBuilder(BaseBuilder):
    """
    Type-safe builder for Pixi-based environments.

    Pixi is a modern package manager supporting both conda and PyPI packages.
    """

    def __init__(self):
        super().__init__()
        self._conda_packages: list[str] = []
        self._pypi_packages: list[str] = []

    def env_type(self) -> str:
        return "pixi"

    def conda(self, *packages: str) -> PixiBuilder:
        """
        Adds conda packages to the environment.

        Args:
            packages: Conda package specifications (e.g., "numpy", "python>=3.8")

        Returns:
            This builder instance
        """
        self._conda_packages.extend(packages)
        return self

    def pypi(self, *packages: str) -> PixiBuilder:
        """
        Adds PyPI packages to the environment.

        Args:
            packages: PyPI package specifications (e.g., "matplotlib", "requests==2.28.0")

        Returns:
            This builder instance
        """
        self._pypi_packages.extend(packages)
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
        env_dir = self._resolve_env_dir()

        # Check for incompatible existing environments
        if (env_dir / "conda-meta").exists() and not (env_dir / ".pixi").exists():
            raise BuildException(
                self,
                f"Cannot use PixiBuilder: environment already managed by Mamba/Conda at {env_dir}",
            )
        if (env_dir / "pyvenv.cfg").exists():
            raise BuildException(
                self,
                f"Cannot use PixiBuilder: environment already managed by uv/venv at {env_dir}",
            )

        pixi = Pixi()

        # Set up progress/output consumers
        pixi.set_output_consumer(
            lambda msg: [sub(msg) for sub in self._output_subscribers]
        )
        pixi.set_error_consumer(
            lambda msg: [sub(msg) for sub in self._error_subscribers]
        )
        pixi.set_download_progress_consumer(
            lambda cur, max: [
                sub("Downloading pixi", cur, max) for sub in self._progress_subscribers
            ]
        )

        # Pass along intended build configuration
        pixi.set_env_vars(self._env_vars)
        pixi.set_flags(self._flags)

        try:
            pixi.install()

            # Check if this is already a pixi project
            is_pixi_dir = (
                (env_dir / "pixi.toml").is_file()
                or (env_dir / "pyproject.toml").is_file()
                or (env_dir / ".pixi").is_dir()
            )

            if (
                is_pixi_dir
                and self._content is None
                and not self._conda_packages
                and not self._pypi_packages
            ):
                # Environment already exists, just use it
                return self._create_environment(env_dir, pixi)

            # Handle source-based build (file or content)
            if self._content is not None:
                # Infer scheme if not explicitly set
                if self._scheme is None:
                    self._scheme = scheme_from_content(self._content)

                if not env_dir.exists():
                    env_dir.mkdir(parents=True, exist_ok=True)

                if self._scheme.name() == "pixi.toml":
                    # Write pixi.toml to envDir
                    pixi_toml_file = env_dir / "pixi.toml"
                    pixi_toml_file.write_text(self._content, encoding="utf-8")
                elif self._scheme.name() == "pyproject.toml":
                    # Write pyproject.toml to envDir (Pixi natively supports it)
                    pyproject_toml_file = env_dir / "pyproject.toml"
                    pyproject_toml_file.write_text(
                        self._content, encoding="utf-8"
                    )
                elif self._scheme.name() == "environment.yml":
                    # Write environment.yml and import
                    environment_yaml_file = env_dir / "environment.yml"
                    environment_yaml_file.write_text(
                        self._content, encoding="utf-8"
                    )
                    # Only run init --import if pixi.toml doesn't exist yet
                    # (importing creates pixi.toml, so this avoids "pixi.toml already exists" error)
                    if not (env_dir / "pixi.toml").exists():
                        pixi.exec(
                            "init",
                            "--import",
                            str(environment_yaml_file.absolute()),
                            str(env_dir.absolute()),
                        )

                # Add any programmatic channels to augment source file
                if self._channels:
                    pixi.add_channels(env_dir, *self._channels)
            else:
                # Programmatic package building
                if is_pixi_dir:
                    # Already initialized, just use it
                    return self._create_environment(env_dir, pixi)

                if not env_dir.exists():
                    env_dir.mkdir(parents=True, exist_ok=True)

                pixi.init(env_dir)

                # Fail fast for vacuous environments
                if not self._conda_packages and not self._pypi_packages:
                    raise BuildException(
                        self,
                        "Cannot build empty environment programmatically. "
                        "Either provide a source file via Appose.pixi(source), or add packages via .conda() or .pypi().",
                    )

                # Add channels
                if self._channels:
                    pixi.add_channels(env_dir, *self._channels)

                # Add conda packages
                if self._conda_packages:
                    pixi.add_conda_packages(env_dir, *self._conda_packages)

                # Add PyPI packages
                if self._pypi_packages:
                    pixi.add_pypi_packages(env_dir, *self._pypi_packages)

                # Verify that appose was included when building programmatically
                prog_build = bool(self._conda_packages) or bool(self._pypi_packages)
                if prog_build:
                    import re

                    has_appose = any(
                        re.match(r"^appose\b", pkg) for pkg in self._conda_packages
                    ) or any(re.match(r"^appose\b", pkg) for pkg in self._pypi_packages)
                    if not has_appose:
                        raise BuildException(
                            self,
                            "Appose package must be explicitly included when building programmatically. "
                            'Add .conda("appose") or .pypi("appose") to your builder.',
                        )

            return self._create_environment(env_dir, pixi)

        except (IOError, KeyboardInterrupt) as e:
            raise BuildException(self, cause=e)

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
                self._content = f.read()
            self._scheme = scheme_from_content("pixi.toml")
        else:
            # Check for pyproject.toml
            pyproject_toml = env_path / "pyproject.toml"
            if pyproject_toml.exists() and pyproject_toml.is_file():
                # Read the content so rebuild() will work even after directory is deleted
                with open(pyproject_toml, "r", encoding="utf-8") as f:
                    self._content = f.read()
                self._scheme = scheme_from_content("pyproject.toml")

        # Set the base directory and build (which will detect existing env)
        self.base(env_path)
        return self.build()

    def _create_environment(self, env_dir: Path, pixi: Pixi) -> Environment:
        """
        Creates an Environment for the given Pixi directory.

        Args:
            env_dir: The Pixi environment directory
            pixi: The Pixi tool instance

        Returns:
            Environment configured for this Pixi installation
        """
        # Convert to absolute path for consistency
        env_dir_abs = env_dir.absolute()
        base = str(env_dir_abs)

        # Check which manifest file exists (pyproject.toml takes precedence)
        manifest_file = env_dir_abs / "pyproject.toml"
        if not manifest_file.exists():
            manifest_file = env_dir_abs / "pixi.toml"

        # Use the installed pixi command (full path)
        launch_args = [
            pixi.command,
            "run",
            "--manifest-path",
            str(manifest_file.absolute()),
        ]
        bin_paths = [str(env_dir_abs / ".pixi" / "envs" / "default" / "bin")]

        return self._create_env(base, bin_paths, launch_args)


class PixiBuilderFactory(BuilderFactory):
    """
    Factory for creating PixiBuilder instances.
    """

    def create_builder(self) -> Builder:
        """
        Creates a new PixiBuilder instance.

        Returns:
            A new PixiBuilder instance
        """
        return PixiBuilder()

    def env_type(self) -> str:
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
