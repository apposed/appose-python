# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
TODO
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .service import Service
from .syntax import GroovySyntax, PythonSyntax
from .util.filepath import find_exe

if TYPE_CHECKING:
    from .builder import Builder, BuildListener, EnvStatus


class Environment:
    def __init__(self, base: Path | str, use_system_path: bool = False):
        self.base_path: Path = Path(base).absolute()
        self.use_system_path: bool = use_system_path

    def base(self) -> str:
        """
        Return the base directory of this environment.

        Returns:
            The absolute path to the base directory
        """
        return str(self.base_path)

    def bin_paths(self) -> list[str]:
        """
        Return the list of binary directories to search for executables.

        Returns:
            List of binary directory paths
        """
        # Default implementation - subclasses should override
        return [str(self.base_path / "bin")]

    def launch_args(self) -> list[str]:
        """
        Return the launch arguments to prepend when starting worker processes.

        Returns:
            List of launch arguments
        """
        # Default implementation - subclasses should override
        return []

    def env_vars(self) -> dict[str, str]:
        """
        Return environment variables to set when launching worker processes.

        Returns:
            Dictionary of environment variable names to values
        """
        # Default implementation - subclasses should override
        return {}

    def builder(self) -> Builder | None:
        """
        Get the builder that created this environment.

        Returns:
            The builder instance, or None if not created via a builder
        """
        return None

    def type(self) -> str:
        """
        Get the type of this environment (e.g., "pixi", "mamba", "uv").

        Returns:
            The environment type name
        """
        builder = self.builder()
        return builder.env_type() if builder else "unknown"

    def activate(self, name: str) -> Environment:
        """
        Return a new Environment targeting a named sub-environment.

        For pixi projects this installs (if needed) and activates the named
        pixi environment, equivalent to ``pixi run --environment <name>``.
        The returned Environment is fully ready to launch services.

        Args:
            name: The sub-environment name (e.g. ``"gpu"``, ``"shiny"``).

        Returns:
            A new Environment configured for the named sub-environment.

        Raises:
            NotImplementedError: If this environment type does not support
                named sub-environments.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support named sub-environments"
        )

    def rebuild(self) -> Environment:
        """
        Rebuilds this environment from scratch.
        This deletes the existing environment directory and rebuilds it using the
        current builder configuration.

        Returns:
            The newly rebuilt environment.
        Raises:
            BuildException: If something goes wrong during rebuild.
        """
        return self.builder().rebuild()

    def status(self) -> EnvStatus:
        """
        Gets the current status of this environment on disk.

        Returns:
            The result of Builder.status() on this environment's builder.
        """
        return self.builder().status()

    def delete(self) -> Environment:
        """
        Deletes the existing environment directory, if any.

        Returns:
            This environment, for fluid chaining.
        Raises:
            OSError: If something goes wrong during deletion.
        """
        self.builder().delete()
        return self

    def python(self, *args: str) -> Service:
        """
        Create a Python script service, or launch a custom Python process.

        If invoked without arguments, this is a *high level* way to create a
        a service, enabling execution of Python scripts asynchronously on its
        linked process running a `python_worker`.

        Or if invoked with any arguments, this becomes a *lower level* function
        for launching Python with any arguments of your choice. This can be
        useful to perform actions such as installing a wheel (`python -m pip
        install /path/to/wheel-file`), without the usual bother of
        platform-specific special casing.

        Args:
            args: Optional alternate args to pass to the python process.
                If empty, a normal Appose `python_worker` will be started.

        Returns:
            The newly created service.

        Raises:
            IOError: If something goes wrong starting the worker process.

        See Also:
            groovy(): To create a service for Groovy script execution.
        """
        python_exes = [
            "python",
            "python3",
            "python.exe",
            "bin/python",
            "bin/python.exe",
        ]
        python_args = args or [
            "-c",
            "import appose.python_worker; appose.python_worker.main()",
        ]
        # NB: Unset conda/mamba variables so they don't bleed into the worker
        # process and cause the wrong Python interpreter to be resolved.
        # Only clear variables not explicitly set by the caller via env().
        conda_vars = (
            "CONDA_PREFIX",
            "CONDA_DEFAULT_ENV",
            "CONDA_SHLVL",
            "PYTHONEXECUTABLE",
        )
        explicit = self.env_vars()
        conda_unset = {var: None for var in conda_vars if var not in explicit}
        return (
            self.service(python_exes, *python_args)
            .syntax(PythonSyntax())
            .env(**conda_unset)
        )

    def groovy(
        self,
        class_path: list[str] | None = None,
        jvm_args: list[str] | None = None,
    ) -> Service:
        """
        Create a Groovy script service.

        Groovy (https://groovy-lang.org/) is a script language for the JVM,
        capable of running Java bytecode conveniently and succinctly, as well
        as downloading and importing dependencies dynamically at runtime using
        its Grape subsystem (https://groovy-lang.org/Grape).

        This is a *high level* way to create a service, enabling execution of
        Groovy scripts asynchronously on its linked process running a
        `GroovyWorker`.

        Args:
            class_path: Additional classpath elements to pass to the JVM
                via its `-cp` command line option.
            jvm_args: Command line arguments to pass to the JVM invocation (e.g. `-Xmx4g`).

        Returns:
            The newly created service.

        Raises:
            IOError: If something goes wrong starting the worker process.

        See Also:
            python(): To create a service for Python script execution.
        """
        return self.java(
            "org.apposed.appose.GroovyWorker", class_path=class_path, jvm_args=jvm_args
        ).syntax(GroovySyntax())

    def java(
        self,
        main_class: str,
        class_path: list[str] | None = None,
        jvm_args: list[str] | None = None,
    ) -> Service:
        # Collect classpath elements into a set, to avoid duplicate entries.
        cp: dict[str, str | None] = {}  # NB: Use dict to maintain insertion order.

        # TODO: Ensure that the classpath includes Appose and its dependencies.

        # Append any explicitly requested classpath elements.
        if class_path is not None:
            for element in class_path:
                cp[element] = None

        # Build up the service arguments.
        args = [
            "-cp",
            os.pathsep.join(cp),
        ]
        if jvm_args is not None:
            args.extend(jvm_args)
        args.append(main_class)

        # Create the service.
        java_exes = [
            "java",
            "java.exe",
            "bin/java",
            "bin/java.exe",
            "jre/bin/java",
            "jre/bin/java.exe",
        ]
        return self.service(java_exes, *args)

    def service(self, exes: list[str], *args: str) -> Service:
        """
        Create a service with the given command line arguments.

        This is a **low level** way to create a service. It assumes the
        specified executable conforms to the Appose worker process contract,
        meaning it accepts requests on stdin and produces responses on
        stdout, both formatted according to Appose's assumptions.

        Args:
            exes: List of executables to try for launching the worker process.
            args: Command line arguments to pass to the worker process
                (e.g. ["-v", "--enable-everything"]).

        Returns:
            The newly created service.

        See Also:
            groovy(): To create a service for Groovy script execution.
            python(): To create a service for Python script execution.
        """
        if not exes:
            raise ValueError("No executable given")

        # Calculate exe string.
        launch_args_list = self.launch_args()
        if launch_args_list:
            # When there are launchArgs (e.g., "pixi run" or "mamba run"), use the bare
            # executable name. The launcher will activate the environment and find the
            # executable. This approach also avoids issues with pixi/mamba not properly
            # handling executable paths containing spaces.
            exe_path = exes[0]
        else:
            # No launchArgs, so we need to find and use the full path to the executable.
            # Get binary paths from environment configuration
            bin_paths = self.bin_paths()

            # Add system PATH if use_system_path is enabled
            dirs: list[str] = bin_paths if bin_paths else []
            if self.use_system_path:
                dirs.extend(os.environ["PATH"].split(os.pathsep))

            # Fall back to base directory if no bin paths configured
            if not dirs:
                dirs = [str(self.base_path)]

            exe_file = find_exe(dirs, exes)
            if exe_file is None:
                raise ValueError(f"No executables found amongst candidates: {exes}")

            # Use absolute path instead of relative path to preserve symlinks.
            # This is important for Python virtual environments where the python symlink
            # needs to be used directly (not the resolved target) for proper site-packages access.
            exe_path = str(exe_file.absolute())

        # Construct final args list: launchArgs + exe + args
        all_args: list[str] = []
        all_args.extend(launch_args_list)
        all_args.append(exe_path)
        all_args.extend(args)

        return Service(self.base(), self.env_vars(), *all_args)


# Locks serializing builds of LazyEnvironments, keyed by environment name.
_build_locks: dict[str, threading.Lock] = {}
_build_locks_lock = threading.Lock()


class LazyEnvironment:
    """
    An Appose environment that is built on first use, once, and then shared
    by any number of ResidentWorkers.

    Builds of environments with the same name are serialized, even across
    instances, because they typically share a directory on disk: e.g. when
    the environment's configuration changes while an older build is still
    running. So instances whose builders target the same directory should be
    given the same name.
    """

    def __init__(self, name: str, builder: Builder, activate: str | None = None):
        """
        Args:
            name: Name of the environment, as reported to listeners, and
                identifying builds to serialize. It is not given to the
                builder, which must already be configured with where to
                build, e.g. via Builder.name or Builder.base.
            builder: Builder for the environment; built on first use.
            activate: Name of the sub-environment to activate once built
                (e.g. a pixi environment), or None to use the environment as
                built.
        """
        self._name = name
        self._activate = activate
        self._listeners: list[BuildListener] = []
        self._env: Environment | None = None
        # Note: Subscribe once, here, and dispatch to the current listeners,
        # because builders accumulate subscribers with every call.
        self._builder = (
            builder.subscribe_progress(
                lambda title, current, maximum: self._notify(
                    "build_progress", title, current, maximum
                )
            )
            .subscribe_output(lambda text: self._notify("build_output", text))
            .subscribe_error(lambda text: self._notify("build_error", text))
        )

    def name(self) -> str:
        return self._name

    def add_build_listener(self, listener: BuildListener) -> LazyEnvironment:
        self._listeners.append(listener)
        return self

    def is_built(self) -> bool:
        """Whether the environment has been built by this instance."""
        return self._env is not None

    def get(self) -> Environment:
        """
        Get the environment, building it if this is its first use.

        Raises:
            BuildException: If the environment cannot be built.
        """
        if self._env is not None:
            return self._env
        with _build_locks_lock:
            lock = _build_locks.setdefault(self._name, threading.Lock())
        with lock:
            if self._env is not None:
                return self._env
            self._notify("build_started")
            try:
                built = self._builder.build()
                self._env = (
                    built if self._activate is None else built.activate(self._activate)
                )
            except Exception as e:
                self._notify("build_finished", e)
                raise
            self._notify("build_finished", None)
            return self._env

    def _notify(self, method: str, *args: Any) -> None:
        # Note: Iterate over a copy, so listeners can be added mid-build.
        for listener in list(self._listeners):
            getattr(listener, method)(self._name, *args)
