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
Type-safe builder for Micromamba-based environments.
"""

from __future__ import annotations

from pathlib import Path

from . import BaseBuilder, BuildException, Builder, BuilderFactory
from ..environment import Environment
from ..tool.mamba import Mamba


class MambaBuilder(BaseBuilder):
    """
    Type-safe builder for Micromamba-based environments.

    Mamba/Micromamba provides fast conda environment management.
    """

    def __init__(self):
        super().__init__()

        # Note: Already assigned in BaseBuilder, but stubgen wants these here, too.
        self.source_content: str | None = None
        self.scheme: str | None = None

    def name(self) -> str:
        return "mamba"

    def channels(self, *channels: str) -> MambaBuilder:
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
        Builds the Mamba environment.

        Returns:
            The newly constructed Environment

        Raises:
            BuildException: If the build fails
        """
        env_dir = self._env_dir()

        # Check for incompatible existing environments
        if (env_dir / ".pixi").is_dir():
            raise BuildException(
                self,
                f"Cannot use MambaBuilder: environment already managed by Pixi at {env_dir}",
            )
        if (env_dir / "pyvenv.cfg").exists():
            raise BuildException(
                self,
                f"Cannot use MambaBuilder: environment already managed by uv/venv at {env_dir}",
            )

        # Create Mamba tool instance early so it's available for wrapping
        mamba = Mamba()

        # Is this env_dir an already-existing conda directory?
        is_conda_dir = (env_dir / "conda-meta").is_dir()
        if is_conda_dir:
            # Environment already exists, just wrap it
            return self._create_environment(env_dir, mamba)

        # Building a new environment - config content is required
        if self.source_content is None:
            raise BuildException(
                self, "No source specified for MambaBuilder. Use .file() or .content()"
            )

        # Infer scheme if not explicitly set
        if self.scheme is None:
            self.scheme = self._scheme().name()

        if self.scheme != "environment.yml":
            raise BuildException(
                self,
                f"MambaBuilder only supports environment.yml scheme, got: {self.scheme}",
            )

        # Set up progress/output consumers
        mamba.set_output_consumer(
            lambda msg: [sub(msg) for sub in self.output_subscribers]
        )
        mamba.set_error_consumer(
            lambda msg: [sub(msg) for sub in self.error_subscribers]
        )
        mamba.set_download_progress_consumer(
            lambda cur, max: [
                sub("Downloading micromamba", cur, max)
                for sub in self.progress_subscribers
            ]
        )

        # Pass along intended build configuration
        mamba.set_env_vars(self.env_vars_dict)
        mamba.set_flags(self.flags_list)

        # Check for unsupported features
        if self.channels_list:
            raise BuildException(
                self,
                "MambaBuilder does not yet support programmatic channel configuration. "
                "Please specify channels in your environment.yml file.",
            )

        try:
            mamba.install()

            # Two-step build: create empty env, write config, then update
            # Step 1: Create empty environment
            mamba.create(env_dir)

            # Step 2: Write environment.yml to envDir
            env_yaml = env_dir / "environment.yml"
            env_yaml.write_text(self.source_content, encoding="utf-8")

            # Step 3: Update environment from yml
            mamba.update(env_dir, env_yaml)

            return self._create_environment(env_dir, mamba)

        except (IOError, KeyboardInterrupt) as e:
            raise BuildException(self, cause=e)

    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wraps an existing Mamba/conda environment directory.

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

        # Look for environment.yml configuration file
        env_yaml = env_path / "environment.yml"
        if env_yaml.exists() and env_yaml.is_file():
            # Read the content so rebuild() will work even after directory is deleted
            with open(env_yaml, "r", encoding="utf-8") as f:
                self.source_content = f.read()

        # Set the base directory and build (which will detect existing env)
        self.base(env_path)
        return self.build()

    def _create_environment(self, env_dir: Path, mamba: Mamba) -> Environment:
        """
        Creates an Environment for the given Mamba/conda directory.

        Args:
            env_dir: The Mamba/conda environment directory
            mamba: The Mamba tool instance

        Returns:
            Environment configured for this Mamba/conda installation
        """
        # Convert to absolute path for consistency
        env_dir_abs = env_dir.absolute()
        base = str(env_dir_abs)
        # Use the installed micromamba command (full path)
        launch_args = [mamba.command, "run", "-p", base]
        bin_paths = [str(env_dir_abs / "bin")]

        return self._create_env(base, bin_paths, launch_args)


class MambaBuilderFactory(BuilderFactory):
    """
    Factory for creating MambaBuilder instances.
    """

    def create_builder(self) -> Builder:
        """
        Creates a new MambaBuilder instance.

        Returns:
            A new MambaBuilder instance
        """
        return MambaBuilder()

    def name(self) -> str:
        return "mamba"

    def supports_scheme(self, scheme: str) -> bool:
        """
        Checks if this builder supports the given scheme.

        Args:
            scheme: The scheme to check

        Returns:
            True if supported
        """
        return scheme == "environment.yml"

    def priority(self) -> float:
        """
        Returns the priority for this builder.

        Returns:
            Priority value (higher = more preferred)
        """
        return 50.0  # Lower priority than pixi for environment.yml

    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Checks if this builder can wrap the given environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this is a conda/mamba environment
        """
        env_path = Path(env_dir)
        return (env_path / "conda-meta").is_dir()
