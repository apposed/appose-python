# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Type-safe builder for uv-based virtual environments.
"""

from __future__ import annotations

from pathlib import Path

from ..environment import Environment
from ..scheme import from_content as scheme_from_content
from ..scheme import from_name as scheme_from_name
from ..tool.uv import Uv
from ..util.platform import is_windows
from . import BaseBuilder, Builder, BuilderFactory, BuildException, EnvStatus
from .requirement import appose_requirement, mentions_appose


class UvBuilder(BaseBuilder):
    """
    Type-safe builder for uv-based virtual environments.

    uv is a fast Python package installer and resolver.
    """

    def __init__(self):
        super().__init__()
        self._python_version: str | None = None
        self._packages: list[str] = []
        self._groups: list[str] = []

    def python(self, version: str) -> UvBuilder:
        """
        Specify the Python version to use for the virtual environment.

        Args:
            version: Python version (e.g., "3.11", "3.10")

        Returns:
            This builder instance
        """
        self._python_version = version
        return self

    def include(self, *packages: str) -> UvBuilder:
        """
        Add PyPI packages to install in the virtual environment.

        Args:
            packages: PyPI package specifications (e.g., "numpy", "requests==2.28.0")

        Returns:
            This builder instance
        """
        self._packages.extend(packages)
        return self

    def group(self, *groups: str) -> UvBuilder:
        """
        Add PEP 735 dependency groups to install via `uv sync --group`.
        Only supported with the pyproject.toml scheme.

        Args:
            groups: Dependency group names defined in [dependency-groups].

        Returns:
            This builder instance
        """
        self._groups.extend(groups)
        return self

    def env_type(self) -> str:
        return "uv"

    def _add_state_fields(self, state: dict) -> None:
        super()._add_state_fields(state)
        state["pythonVersion"] = self._python_version
        state["packages"] = list(self._packages)
        if self._groups:
            state["groups"] = list(self._groups)
        if self._adds_appose():
            # NB: Recorded, so that a change in Appose version triggers a rebuild.
            state["appose"] = appose_requirement().pip_args()

    def _adds_appose(self) -> bool:
        """Whether this builder adds appose to the packages it installs."""
        # NB: With no packages to install, there is nothing to build, and an
        # existing environment (e.g. one being wrapped) is used as-is.
        return (
            self._content is None
            and bool(self._packages)
            and not mentions_appose(self._packages)
        )

    def _has_environment(self, env_dir: Path) -> bool:
        return (env_dir / "pyvenv.cfg").is_file() or (env_dir / ".venv").is_dir()

    def _incompatibility(self, env_dir: Path) -> str | None:
        if (env_dir / ".pixi").is_dir():
            return "environment already managed by Pixi"
        if (env_dir / "conda-meta").is_dir():
            return "environment already managed by Mamba/Conda"
        return None

    def build(self) -> Environment:
        """
        Build the uv environment.

        Returns:
            The newly constructed Environment

        Raises:
            BuildException: If the build fails
        """
        env_dir = self._resolve_env_dir()

        self._check_compatibility(env_dir)

        uv = Uv()

        # Set up progress/output consumers
        uv.set_output_consumer(
            lambda msg: [sub(msg) for sub in self._output_subscribers]
        )
        uv.set_error_consumer(lambda msg: [sub(msg) for sub in self._error_subscribers])
        uv.set_download_progress_consumer(
            lambda cur, max: [
                sub("Downloading uv", cur, max) for sub in self._progress_subscribers
            ]
        )

        # Pass along intended build configuration
        uv.set_env_vars(self._env_vars)
        uv.set_flags(self._flags)

        # Check for unsupported features
        if self._channels:
            raise BuildException(
                self,
                "UvBuilder does not yet support programmatic index configuration. "
                "Please specify custom indices in your requirements.txt file using "
                "'--index-url' or '--extra-index-url' directives.",
            )

        # Validate content/scheme BEFORE installing any tools.
        if self._content is not None:
            if self._scheme is None:
                self._scheme = scheme_from_content(self._content)
            if self._scheme.name() not in ["requirements.txt", "pyproject.toml"]:
                raise ValueError(
                    f"UvBuilder only supports requirements.txt and pyproject.toml schemes, got: {self._scheme.name()}"
                )

        # Validate groups are only used with pyproject.toml.
        if self._groups and (
            self._scheme is None or self._scheme.name() != "pyproject.toml"
        ):
            raise ValueError(
                "Dependency groups are only supported with pyproject.toml scheme"
            )

        # Validate lock-file compatibility. uv lockfiles only apply to the
        # pyproject.toml / uv sync path: requirements.txt uses pip install (no
        # lockfile), and programmatic builds have no manifest to lock against.
        if self._lock_content is not None:
            if self._content is None:
                raise ValueError(
                    "UvBuilder lock files require a declaration file via file()/content(); "
                    "programmatic builds cannot be locked."
                )
            if self._scheme.name() != "pyproject.toml":
                raise ValueError(
                    "UvBuilder lock files require a pyproject.toml declaration; "
                    "requirements.txt has no lockfile mechanism."
                )

        try:
            uv.install()

            # If the env state matches our current configuration,
            # skip all package management and return immediately.
            if self.status() == EnvStatus.CURRENT:
                return self._create_environment(env_dir)

            # We are about to hit the network anyway; take the opportunity
            # to keep uv current, so it understands state written by newer
            # uv installations elsewhere on the system.
            uv.self_update()

            # Determine whether the venv already exists.
            is_venv_built = (env_dir / "pyvenv.cfg").is_file() or (
                env_dir / ".venv"
            ).is_dir()

            # Handle source-based build (file or content)
            if self._content is not None:
                if self._scheme.name() == "pyproject.toml":
                    # Handle pyproject.toml - uses uv sync
                    # Create envDir if it doesn't exist
                    if not env_dir.exists():
                        env_dir.mkdir(parents=True, exist_ok=True)

                    # Write pyproject.toml to envDir
                    pyproject_file = env_dir / "pyproject.toml"
                    pyproject_file.write_text(self._content, encoding="utf-8")

                    # If a lock file was provided, copy it into the env dir and
                    # install strictly from it (--locked) for reproducibility.
                    locked = self._lock_content is not None
                    if locked:
                        uv_lock_file = env_dir / "uv.lock"
                        uv_lock_file.write_text(self._lock_content, encoding="utf-8")

                    # Run uv sync to create .venv and install dependencies
                    uv.sync(env_dir, self._python_version, self._groups, locked)
                else:
                    # Handle requirements.txt - traditional venv + pip install
                    # Create virtual environment if it doesn't exist
                    if not is_venv_built:
                        uv.create_venv(env_dir, self._python_version)

                    # Write requirements.txt to envDir
                    reqs_file = env_dir / "requirements.txt"
                    reqs_file.write_text(self._content, encoding="utf-8")

                    # Install packages from requirements.txt
                    uv.pip_install_from_requirements(env_dir, str(reqs_file.absolute()))
            else:
                # Programmatic package building
                if not is_venv_built:
                    # Create virtual environment
                    uv.create_venv(env_dir, self._python_version)

                # Install packages, including a compatible appose for the worker,
                # unless the caller chose one explicitly.
                if self._packages:
                    all_packages = list(self._packages)
                    if self._adds_appose():
                        all_packages.extend(appose_requirement().pip_args())
                    uv.pip_install(env_dir, *all_packages)

            self._write_appose_state_file(env_dir)
            return self._create_environment(env_dir)

        except (OSError, KeyboardInterrupt) as e:
            raise BuildException(self, cause=e)

    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wrap an existing uv/venv environment directory.

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
                self._content = f.read()
            self._scheme = scheme_from_name("pyproject.toml")

            # Restore any dependency groups, which pyproject.toml does not record.
            # Otherwise, the environment looks stale, and gets synced without them.
            state = None if self._groups else self._read_appose_state(env_path)
            if state is not None and isinstance(state.get("groups"), list):
                self._groups.extend(str(g) for g in state["groups"])

            # Likewise, restore the lock file, if the env was built from one.
            self._restore_lock_content(env_path, "uv.lock")
        else:
            # Fall back to requirements.txt
            requirements_txt = env_path / "requirements.txt"
            if requirements_txt.exists() and requirements_txt.is_file():
                # Read the content so rebuild() will work even after directory is deleted
                with open(requirements_txt, "r", encoding="utf-8") as f:
                    self._content = f.read()
                self._scheme = scheme_from_name("requirements.txt")

        # Set the base directory and build (which will detect existing env)
        self.base(env_path)
        return self.build()

    def _create_environment(self, env_dir: Path) -> Environment:
        """
        Create an Environment for the given uv/venv directory.

        Args:
            env_dir: The uv/venv environment directory

        Returns:
            Environment configured for this uv/venv installation
        """
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
        Create a new UvBuilder instance.

        Returns:
            A new UvBuilder instance
        """
        return UvBuilder()

    def env_type(self) -> str:
        return "uv"

    def supports_scheme(self, scheme: str) -> bool:
        """
        Check if this builder supports the given scheme.

        Args:
            scheme: The scheme to check

        Returns:
            True if supported
        """
        return scheme in ["requirements.txt", "pypi"]

    def priority(self) -> float:
        """
        Return the priority for this builder.

        Returns:
            Priority value (higher = more preferred)
        """
        return 75.0  # Between pixi (100) and mamba (50)

    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Check if this builder can wrap the given environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this is a uv/venv environment
        """
        env_path = Path(env_dir)
        # uv creates standard Python venv, so look for pyvenv.cfg,
        # but exclude conda and pixi environments. For pyproject.toml
        # projects, uv sync puts the venv in a .venv subdirectory.
        has_pyvenv_cfg = (env_path / "pyvenv.cfg").is_file() or (
            env_path / ".venv" / "pyvenv.cfg"
        ).is_file()
        is_not_pixi = (
            not (env_path / ".pixi").is_dir() and not (env_path / "pixi.toml").is_file()
        )
        is_not_conda = not (env_path / "conda-meta").is_dir()

        return has_pyvenv_cfg and is_not_pixi and is_not_conda
