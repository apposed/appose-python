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

from . import BaseBuilder, BuildException, Builder, BuilderFactory
from ..environment import Environment


class UvBuilder(BaseBuilder):
    """
    Type-safe builder for uv-based virtual environments.

    uv is a fast Python package installer and resolver.
    """

    def __init__(self):
        super().__init__()
        self.python_version: str | None = None
        self.packages: list[str] = []

        # Note: Already assigned in BaseBuilder, but stubgen wants these here, too.
        self.source_content: str | None = None
        self.scheme: str | None = None

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
        from ..tool.uv import Uv

        env_dir = self._env_dir()

        # Check for incompatible existing environments
        if (env_dir / ".pixi").is_dir():
            raise BuildException(
                self,
                f"Cannot use UvBuilder: environment already managed by Pixi at {env_dir}",
            )
        if (env_dir / "conda-meta").is_dir():
            raise BuildException(
                self,
                f"Cannot use UvBuilder: environment already managed by Mamba/Conda at {env_dir}",
            )

        uv = Uv()

        # Set up progress/output consumers
        uv.set_output_consumer(
            lambda msg: [sub(msg) for sub in self.output_subscribers]
        )
        uv.set_error_consumer(lambda msg: [sub(msg) for sub in self.error_subscribers])
        uv.set_download_progress_consumer(
            lambda cur, max: [
                sub("Downloading uv", cur, max) for sub in self.progress_subscribers
            ]
        )

        # Pass along intended build configuration
        uv.set_env_vars(self.env_vars_dict)
        uv.set_flags(self.flags_list)

        # Check for unsupported features
        if self.channels_list:
            raise BuildException(
                self,
                "UvBuilder does not yet support programmatic index configuration. "
                "Please specify custom indices in your requirements.txt file using "
                "'--index-url' or '--extra-index-url' directives.",
            )

        try:
            uv.install()

            # Check if this is already a uv virtual environment
            is_uv_venv = (env_dir / "pyvenv.cfg").is_file()

            if is_uv_venv and self.source_content is None and not self.packages:
                # Environment already exists and no new config/packages, just use it
                return self._create_environment(env_dir)

            # Handle source-based build (file or content)
            if self.source_content is not None:
                # Infer scheme if not explicitly set
                if self.scheme is None:
                    self.scheme = self._scheme().name()

                if self.scheme not in ["requirements.txt", "pyproject.toml"]:
                    raise BuildException(
                        self,
                        f"UvBuilder only supports requirements.txt and pyproject.toml schemes, got: {self.scheme}",
                    )

                if self.scheme == "pyproject.toml":
                    # Handle pyproject.toml - uses uv sync
                    # Create envDir if it doesn't exist
                    if not env_dir.exists():
                        env_dir.mkdir(parents=True, exist_ok=True)

                    # Write pyproject.toml to envDir
                    pyproject_file = env_dir / "pyproject.toml"
                    pyproject_file.write_text(self.source_content, encoding="utf-8")

                    # Run uv sync to create .venv and install dependencies
                    uv.sync(env_dir, self.python_version)
                else:
                    # Handle requirements.txt - traditional venv + pip install
                    # Create virtual environment if it doesn't exist
                    if not is_uv_venv:
                        uv.create_venv(env_dir, self.python_version)

                    # Write requirements.txt to envDir
                    reqs_file = env_dir / "requirements.txt"
                    reqs_file.write_text(self.source_content, encoding="utf-8")

                    # Install packages from requirements.txt
                    uv.pip_install_from_requirements(env_dir, str(reqs_file.absolute()))
            else:
                # Programmatic package building
                if not is_uv_venv:
                    # Create virtual environment
                    uv.create_venv(env_dir, self.python_version)

                # Install packages
                if self.packages:
                    all_packages = list(self.packages)
                    # Always include appose if we're installing packages
                    if "appose" not in all_packages:
                        all_packages.append("appose")
                    uv.pip_install(env_dir, *all_packages)

            return self._create_environment(env_dir)

        except (IOError, KeyboardInterrupt) as e:
            raise BuildException(self, cause=e)

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

        # Convert to absolute path for consistency
        env_dir_abs = env_dir.absolute()
        base = str(env_dir_abs)

        # Determine venv location based on project structure.
        # If .venv exists, it's a pyproject.toml-managed project (uv sync).
        # Otherwise, env_dir itself is the venv (uv venv + pip install).
        venv_dir = env_dir_abs / ".venv"
        actual_venv_dir = venv_dir if venv_dir.exists() else env_dir_abs

        # uv virtual environments use standard venv structure.
        bin_dir = "Scripts" if is_windows() else "bin"
        bin_paths = [str(actual_venv_dir / bin_dir)]

        # No special launch args needed - executables are directly in bin/Scripts.
        launch_args = []

        return self._create_env(base, bin_paths, launch_args)


class UvBuilderFactory(BuilderFactory):
    """
    Factory for creating UvBuilder instances.
    """

    def create_builder(self) -> Builder:
        """
        Creates a new UvBuilder instance.

        Returns:
            A new UvBuilder instance
        """
        return UvBuilder()

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
