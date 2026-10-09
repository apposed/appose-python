# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Type-safe builder for Pixi-based environments.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..environment import Environment
from ..scheme import from_content as scheme_from_content
from ..scheme import from_name as scheme_from_name
from ..tool.pixi import Pixi
from . import BaseBuilder, Builder, BuilderFactory, BuildException, EnvStatus
from .pixi_install_monitor import PixiInstallMonitor
from .requirement import appose_requirement, mentions_appose


class PixiBuilder(BaseBuilder):
    """
    Type-safe builder for Pixi-based environments.

    Pixi is a modern package manager supporting both conda and PyPI packages.
    """

    def __init__(self):
        super().__init__()
        self._conda_packages: list[str] = []
        self._pypi_packages: list[str] = []

    def conda(self, *packages: str) -> PixiBuilder:
        """
        Add conda packages to the environment.

        Args:
            packages: Conda package specifications (e.g., "numpy", "python>=3.8")

        Returns:
            This builder instance
        """
        self._conda_packages.extend(packages)
        return self

    def pypi(self, *packages: str) -> PixiBuilder:
        """
        Add PyPI packages to the environment.

        Args:
            packages: PyPI package specifications (e.g., "matplotlib", "requests==2.28.0")

        Returns:
            This builder instance
        """
        self._pypi_packages.extend(packages)
        return self

    def env_type(self) -> str:
        return "pixi"

    def _add_state_fields(self, state: dict) -> None:
        super()._add_state_fields(state)
        state["condaPackages"] = list(self._conda_packages)
        state["pypiPackages"] = list(self._pypi_packages)
        if self._adds_appose():
            # NB: Recorded, so that a change in Appose version triggers a rebuild.
            state["appose"] = appose_requirement().pip_args()

    def _adds_appose(self) -> bool:
        """Whether this builder adds appose to the packages it installs."""
        return self._content is None and not mentions_appose(
            self._conda_packages + self._pypi_packages
        )

    def _has_environment(self, env_dir: Path) -> bool:
        return (env_dir / ".pixi" / "envs" / "default").is_dir()

    def _incompatibility(self, env_dir: Path) -> str | None:
        if (env_dir / "conda-meta").exists() and not (env_dir / ".pixi").exists():
            return "environment already managed by Mamba/Conda"
        if (env_dir / "pyvenv.cfg").exists():
            return "environment already managed by uv/venv"
        return None

    def build(self) -> Environment:
        """
        Build the Pixi environment.

        Returns:
            The newly constructed Environment

        Raises:
            BuildException: If the build fails
        """
        env_dir = self._resolve_env_dir()

        self._check_compatibility(env_dir)

        # Validate content/scheme BEFORE installing any tools.
        if self._content is not None:
            if self._scheme is None:
                self._scheme = scheme_from_content(self._content)
            if self._scheme.name() not in [
                "pixi.toml",
                "pyproject.toml",
                "environment.yml",
            ]:
                raise ValueError(
                    f"PixiBuilder only supports pixi.toml, pyproject.toml, and environment.yml schemes, got: {self._scheme.name()}"
                )

        # Validate lock-file compatibility. pixi lockfiles apply to manifest-
        # based builds (pixi.toml / pyproject.toml); programmatic builds and
        # imported environment.yml have no user manifest to lock against.
        if self._lock_content is not None:
            if self._content is None:
                raise ValueError(
                    "PixiBuilder lock files require a declaration file via file()/content(); "
                    "programmatic builds cannot be locked."
                )
            if self._scheme.name() not in ["pixi.toml", "pyproject.toml"]:
                raise ValueError(
                    "PixiBuilder lock files require a pixi.toml or pyproject.toml declaration; "
                    "environment.yml imports have no lockfile mechanism."
                )
            # Note: adding channels re-resolves the manifest and rewrites the lock.
            if self._channels:
                raise ValueError(
                    "PixiBuilder lock files cannot be combined with programmatic channels; "
                    "declare the channels in the manifest instead."
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

            # If the env state matches our current configuration,
            # skip all package management and return immediately.
            if self.status() == EnvStatus.CURRENT:
                return self._build_pixi_environment(pixi, env_dir)

            # With nothing to build from, use an existing env as-is, if any.
            # Note: this must happen before anything is wiped below.
            if (
                self._content is None
                and not self._conda_packages
                and not self._pypi_packages
            ):
                if self._has_environment(env_dir):
                    return self._build_pixi_environment(pixi, env_dir)
                raise BuildException(
                    self,
                    "Cannot build empty environment programmatically. "
                    "Either provide a source file via Appose.pixi(source), or add packages via .conda() or .pypi().",
                )

            # We are about to hit the network anyway; take the opportunity
            # to keep pixi current, so it understands state written by newer
            # pixi installations elsewhere on the system.
            pixi.self_update()

            # Handle source-based build (file or content)
            if self._content is not None:
                if not env_dir.exists():
                    env_dir.mkdir(parents=True, exist_ok=True)

                if self._scheme.name() == "pixi.toml":
                    # Write pixi.toml to envDir
                    pixi_toml_file = env_dir / "pixi.toml"
                    pixi_toml_file.write_text(self._content, encoding="utf-8")
                elif self._scheme.name() == "pyproject.toml":
                    # Write pyproject.toml to envDir (Pixi natively supports it)
                    pyproject_toml_file = env_dir / "pyproject.toml"
                    pyproject_toml_file.write_text(self._content, encoding="utf-8")
                elif self._scheme.name() == "environment.yml":
                    # Write environment.yml and import
                    environment_yaml_file = env_dir / "environment.yml"
                    environment_yaml_file.write_text(self._content, encoding="utf-8")
                    # Only run init --import if pixi.toml doesn't exist yet
                    # (importing creates pixi.toml, so this avoids "pixi.toml already exists" error)
                    if not (env_dir / "pixi.toml").exists():
                        pixi.exec(
                            "init",
                            "--import",
                            str(environment_yaml_file.absolute()),
                            str(env_dir.absolute()),
                        )

                # If a lock file was provided, copy it into the env dir so the
                # subsequent install runs strictly from it (--locked).
                if self._lock_content is not None:
                    pixi_lock_file = env_dir / "pixi.lock"
                    pixi_lock_file.write_text(self._lock_content, encoding="utf-8")

                # Add any programmatic channels to augment source file
                if self._channels:
                    pixi.add_channels(env_dir, *self._channels)
            else:
                # Programmatic package building: wipe and reinitialize to avoid stale state.
                if env_dir.exists():
                    shutil.rmtree(env_dir)
                env_dir.mkdir(parents=True, exist_ok=True)

                pixi.init(env_dir)

                # Add channels
                if self._channels:
                    pixi.add_channels(env_dir, *self._channels)

                # Add conda packages
                if self._conda_packages:
                    pixi.add_conda_packages(env_dir, *self._conda_packages)

                # Add PyPI packages
                if self._pypi_packages:
                    pixi.add_pypi_packages(env_dir, *self._pypi_packages)

                # Add a compatible appose for the worker,
                # unless the caller chose one explicitly.
                if self._adds_appose():
                    requirement = appose_requirement()
                    pixi.add_pypi_packages(
                        env_dir, requirement.spec, editable=requirement.editable
                    )

            self._run_pixi_install(pixi, env_dir)
            self._write_appose_state_file(env_dir)
            return self._build_pixi_environment(pixi, env_dir)

        except (OSError, KeyboardInterrupt) as e:
            raise BuildException(self, cause=e)

    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wrap an existing Pixi environment directory.

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
            self._scheme = scheme_from_name("pixi.toml")
        else:
            # Check for pyproject.toml
            pyproject_toml = env_path / "pyproject.toml"
            if pyproject_toml.exists() and pyproject_toml.is_file():
                # Read the content so rebuild() will work even after directory is deleted
                with open(pyproject_toml, "r", encoding="utf-8") as f:
                    self._content = f.read()
                self._scheme = scheme_from_name("pyproject.toml")
        self._restore_lock_content(env_path, "pixi.lock")

        # Set the base directory and build (which will detect existing env)
        self.base(env_path)
        return self.build()

    def _run_pixi_install(self, pixi: Pixi, env_dir: Path) -> None:
        """Run pixi install for the given environment directory."""
        env_dir_abs = env_dir.absolute()
        manifest_file = env_dir_abs / "pyproject.toml"
        if not manifest_file.exists():
            manifest_file = env_dir_abs / "pixi.toml"

        # Set up install progress monitoring when subscribers are registered.
        monitor = None
        if self._progress_subscribers:
            # Inject -vv if not already present, so stderr emits phase signals.
            if not any(f in ("-v", "-vv", "-vvv") for f in self._flags):
                pixi.set_flags(self._flags + ["-vv"])

            monitor = PixiInstallMonitor(
                env_dir,
                "default",
                self._progress_subscribers,
                lambda msg: [sub(msg) for sub in self._error_subscribers],
            )
            pixi.set_error_consumer(monitor.intercept)

        # Ensure the pixi environment is fully installed. When a lock was
        # provided, pass --locked so pixi installs exactly what pixi.lock
        # specifies, failing if the lock is out of date with the manifest.
        args = ["install", "--manifest-path", str(manifest_file.absolute())]
        if self._lock_content is not None:
            args.append("--locked")
        try:
            pixi.exec(*args)
        finally:
            if monitor is not None:
                monitor.shutdown()
                # Restore the original error consumer.
                pixi.set_error_consumer(
                    lambda msg: [sub(msg) for sub in self._error_subscribers]
                )
                # Restore the original flags.
                pixi.set_flags(self._flags)

    def _build_pixi_environment(self, pixi: Pixi, env_dir: Path) -> Environment:
        """
        Construct an Environment object for the given Pixi directory.

        Args:
            pixi: The Pixi tool instance
            env_dir: The Pixi environment directory

        Returns:
            Environment configured for this Pixi installation
        """
        env_dir_abs = env_dir.absolute()

        manifest_file = env_dir_abs / "pyproject.toml"
        if not manifest_file.exists():
            manifest_file = env_dir_abs / "pixi.toml"

        base = str(env_dir_abs)
        run_args = [
            pixi.command,
            "run",
            "--manifest-path",
            str(manifest_file.absolute()),
        ]
        # Note: Always name the environment explicitly. Otherwise, when the
        # calling process is itself inside an activated pixi environment,
        # pixi selects the environment named by the inherited
        # PIXI_ENVIRONMENT_NAME, even though it belongs to another project.
        launch_args = run_args + ["--environment", "default"]
        bin_paths = [str(env_dir_abs / ".pixi" / "envs" / "default" / "bin")]

        def activator(name: str) -> Environment:
            pixi.exec(
                "install",
                "--manifest-path",
                str(manifest_file.absolute()),
                "--environment",
                name,
            )
            return self._create_env(
                base,
                [str(env_dir_abs / ".pixi" / "envs" / name / "bin")],
                run_args + ["--environment", name],
            )

        return self._create_env(base, bin_paths, launch_args, activator=activator)


class PixiBuilderFactory(BuilderFactory):
    """
    Factory for creating PixiBuilder instances.
    """

    def create_builder(self) -> Builder:
        """
        Create a new PixiBuilder instance.

        Returns:
            A new PixiBuilder instance
        """
        return PixiBuilder()

    def env_type(self) -> str:
        return "pixi"

    def supports_scheme(self, scheme: str) -> bool:
        """
        Check if this builder supports the given scheme.

        Args:
            scheme: The scheme to check

        Returns:
            True if supported
        """
        return scheme in [
            "pixi.toml",
            "pyproject.toml",
            "environment.yml",
            "conda",
            "pypi",
        ]

    def priority(self) -> float:
        """
        Return the priority for this builder.

        Returns:
            Priority value (higher = more preferred)
        """
        return 100.0  # Preferred for environment.yml and conda/pypi packages

    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Check if this builder can wrap the given environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this is a Pixi environment
        """
        env_path = Path(env_dir)
        return (env_path / ".pixi").is_dir() or (env_path / "pixi.toml").is_file()
