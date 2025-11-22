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
Environment builder infrastructure for creating and managing Appose environments.

This module provides the core builder protocols and implementations for creating
environments with different package managers (pixi, mamba, uv) or simple system
environments.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Protocol
from urllib.request import urlopen

from ..environment import Environment
from ..scheme import Scheme
from .. import scheme


# Type alias for progress callback
ProgressConsumer = Callable[[str, int, int], None]


class BuildException(Exception):
    """
    Exception thrown when a Builder fails to build an environment.
    """

    def __init__(
        self,
        builder: Builder | None = None,
        message: str | None = None,
        cause: Exception | None = None,
    ):
        """
        Create a BuildException.

        Args:
            builder: The builder associated with this exception
            message: Error message
            cause: The underlying exception that caused the build to fail
        """
        if message is None:
            noun = "build" if builder is None else f"{builder.name()} build"
            verb = "interrupted" if isinstance(cause, KeyboardInterrupt) else "failed"
            message = f"{noun} {verb}"
        super().__init__(message)
        self.builder: Builder | None = builder
        self.__cause__: Exception | None = cause


class Builder(Protocol):
    """
    Base protocol for all Appose environment builders.

    Builders are responsible for creating and configuring Appose environments.

    The type parameter enables fluent method chaining to return the concrete
    builder type without requiring subclasses to override every method.
    """

    def name(self) -> str:
        """
        Returns the name of this builder (e.g., "pixi", "mamba", "uv", "custom").

        Returns:
            The builder name
        """
        ...

    def build(self) -> Environment:
        """
        Builds the environment. This is the terminator method for any fluid building chain.

        Returns:
            The newly constructed Appose Environment

        Raises:
            BuildException: If the build fails due to I/O errors, interruption,
                or other build-related issues
        """
        ...

    def rebuild(self) -> Environment:
        """
        Rebuilds the environment from scratch.

        Deletes the existing environment directory (if it exists) and rebuilds it
        using the current builder configuration. This is more robust than trying to
        update an existing environment in place.

        This method is a shorthand for delete() then build().

        Returns:
            The newly rebuilt Environment

        Raises:
            BuildException: If the build fails
        """
        ...

    def delete(self) -> None:
        """
        Deletes the builder's linked environment directory, if any.

        Raises:
            OSError: If something goes wrong during deletion
        """
        ...

    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wraps an existing environment directory, detecting and using any
        configuration files present for future rebuild() calls.

        This method examines the directory for known configuration files
        (e.g., pixi.toml, environment.yml, requirements.txt) and populates
        the builder's configuration accordingly.

        Args:
            env_dir: The existing environment directory to wrap

        Returns:
            The wrapped Environment

        Raises:
            BuildException: If the directory doesn't exist or can't be wrapped
        """
        ...

    def env(self, key: str, value: str) -> Builder:
        """
        Sets an environment variable to be passed to worker processes.

        Args:
            key: The environment variable name
            value: The environment variable value

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def env_vars(self, vars: dict[str, str]) -> Builder:
        """
        Sets multiple environment variables to be passed to worker processes.

        Args:
            vars: Map of environment variable names to values

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def set_name(self, env_name: str) -> Builder:
        """
        Sets the name for the environment.
        The environment will be created in the standard Appose environments directory with this name.

        Args:
            env_name: The name for the environment

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def base(self, env_dir: str | Path) -> Builder:
        """
        Sets the base directory for the environment.
        For many builders, this overrides any name specified via set_name().

        Args:
            env_dir: The directory for the environment

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def channels(self, *channels: str) -> Builder:
        """
        Adds channels/repositories to search for packages.

        The interpretation of channels is builder-specific:
        - Pixi/Mamba: conda channels (e.g., "conda-forge", "bioconda")
        - uv: PyPI index URLs (e.g., custom package indexes)

        Args:
            channels: Channel names or URLs to add

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def file(self, path: str | Path) -> Builder:
        """
        Specifies a configuration file to build from.
        Reads the file content immediately and delegates to content().

        Args:
            path: Path to configuration file (e.g., "pixi.toml", "environment.yml")

        Returns:
            This builder instance, for fluent-style programming

        Raises:
            BuildException: If the file cannot be read
        """
        ...

    def content(self, content: str) -> Builder:
        """
        Specifies configuration file content to build from.
        The scheme will be auto-detected from content syntax.

        Args:
            content: Configuration file content

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def url(self, url: str) -> Builder:
        """
        Specifies a URL to fetch configuration content from.
        Reads the URL content immediately and delegates to content().

        Args:
            url: URL to configuration file

        Returns:
            This builder instance, for fluent-style programming

        Raises:
            BuildException: If the URL cannot be read
        """
        ...

    def scheme(self, scheme: str) -> Builder:
        """
        Explicitly specifies the scheme for the configuration.
        This overrides auto-detection.

        Args:
            scheme: The scheme (e.g., "pixi.toml", "environment.yml", "requirements.txt")

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def subscribe_progress(self, subscriber: ProgressConsumer) -> Builder:
        """
        Registers a callback to be invoked when progress happens during environment building.

        Args:
            subscriber: Function to call with (title, current, maximum) when progress happens

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def subscribe_output(self, subscriber: Callable[[str], None]) -> Builder:
        """
        Registers a callback to be invoked when output is generated during environment building.

        Args:
            subscriber: Function to call with output strings

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def subscribe_error(self, subscriber: Callable[[str], None]) -> Builder:
        """
        Registers a callback to be invoked when errors occur during environment building.

        Args:
            subscriber: Function to call with error strings

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def flags(self, *flags: str) -> Builder:
        """
        Adds command-line flags to be passed to the underlying tool during build operations.

        These flags are passed directly to the tool's command-line invocation.
        The interpretation of flags is tool-specific:
        - Pixi: flags like "--color=always", "-v"
        - Mamba: flags like "-vv", "--json"
        - uv: flags like "--color=always", "--verbose"

        Args:
            flags: Command-line flags to add

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    def log_debug(self) -> Builder:
        """
        Convenience method to log debug output to stderr.
        Default implementation subscribes both output and error to stderr.

        Returns:
            This builder instance, for fluent-style programming
        """
        ...


class BuilderFactory(Protocol):
    """
    Factory protocol for creating builder instances.

    Implementations are discovered at runtime via entry points and managed by
    the Builders utility class.
    """

    def create_builder(self) -> Builder:
        """
        Creates a new builder instance with no configuration.
        Configuration should be provided via the fluent API (e.g., content, scheme).

        Returns:
            A new builder instance
        """
        ...

    def name(self) -> str:
        """
        Returns the name of this builder (e.g., "pixi", "mamba", "custom").

        Returns:
            The builder name
        """
        ...

    def supports_scheme(self, scheme: str) -> bool:
        """
        Checks if this builder supports the given scheme.

        Args:
            scheme: The scheme to check (e.g., "environment.yml", "conda", "pypi")

        Returns:
            True if this builder supports the scheme
        """
        ...

    def priority(self) -> float:
        """
        Returns the priority of this builder for scheme resolution.
        Higher priority builders are preferred when multiple builders support the same scheme.

        Returns:
            The priority value (higher = more preferred)
        """
        ...

    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Checks if this builder can wrap the given existing environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this builder can wrap the directory
        """
        ...


class BaseBuilder:
    """
    Base class for environment builders.
    Provides common implementation for the Builder protocol.
    """

    def __init__(self):
        self.progress_subscribers: list[ProgressConsumer] = []
        self.output_subscribers: list[Callable[[str], None]] = []
        self.error_subscribers: list[Callable[[str], None]] = []
        self.env_vars_dict: dict[str, str] = {}
        self.channels_list: list[str] = []
        self.flags_list: list[str] = []
        self.env_name: str | None = None
        self.env_dir: Path | None = None
        self.source_content: str | None = None
        self.scheme: str | None = None

    def rebuild(self) -> Environment:
        """Default implementation: delete then build."""
        try:
            self.delete()
        except Exception as e:
            raise BuildException(self, cause=e)
        return self.build()

    def delete(self) -> None:
        """Default implementation: delete env_dir if it exists."""
        dir_path = self._env_dir()
        if dir_path.exists():
            shutil.rmtree(dir_path)

    def wrap(self, env_dir: str | Path) -> Environment:
        """Default implementation: set base and build."""
        env_path = Path(env_dir)
        if not env_path.exists():
            raise BuildException(self, f"Directory does not exist: {env_dir}")
        if not env_path.is_dir():
            raise BuildException(self, f"Not a directory: {env_dir}")
        self.base(env_path)
        return self.build()

    def env(self, key: str, value: str) -> BaseBuilder:
        """Set a single environment variable."""
        self.env_vars_dict[key] = value
        return self

    def env_vars(self, vars: dict[str, str]) -> BaseBuilder:
        """Set multiple environment variables."""
        self.env_vars_dict.update(vars)
        return self

    def set_name(self, env_name: str) -> BaseBuilder:
        """Set the environment name."""
        self.env_name = env_name
        return self

    def base(self, env_dir: str | Path) -> BaseBuilder:
        """Set the base directory."""
        self.env_dir = Path(env_dir)
        return self

    def channels(self, *channels: str) -> BaseBuilder:
        """Add channels."""
        self.channels_list.extend(channels)
        return self

    def file(self, path: str | Path) -> BaseBuilder:
        """Load configuration from a file."""
        try:
            file_path = Path(path)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.content(content)
        except Exception as e:
            raise BuildException(self, cause=e)

    def content(self, content: str) -> BaseBuilder:
        """Set configuration content."""
        self.source_content = content
        return self

    def url(self, url: str) -> BaseBuilder:
        """Load configuration from a URL."""
        try:
            with urlopen(url) as response:
                content = response.read().decode("utf-8")
            return self.content(content)
        except Exception as e:
            raise BuildException(self, cause=e)

    def scheme(self, scheme: str) -> BaseBuilder:
        """Set the explicit scheme."""
        self.scheme = scheme
        return self

    def subscribe_progress(self, subscriber: ProgressConsumer) -> BaseBuilder:
        """Register a progress callback."""
        self.progress_subscribers.append(subscriber)
        return self

    def subscribe_output(self, subscriber: Callable[[str], None]) -> BaseBuilder:
        """Register an output callback."""
        self.output_subscribers.append(subscriber)
        return self

    def subscribe_error(self, subscriber: Callable[[str], None]) -> BaseBuilder:
        """Register an error callback."""
        self.error_subscribers.append(subscriber)
        return self

    def flags(self, *flags: str) -> BaseBuilder:
        """Add command-line flags."""
        self.flags_list.extend(flags)
        return self

    def log_debug(self) -> BaseBuilder:
        """Log output and errors to stderr."""
        return self.subscribe_output(
            lambda msg: print(msg, file=sys.stdout, end="")
        ).subscribe_error(lambda msg: print(msg, file=sys.stderr, end=""))

    # Helper methods

    def _env_name(self) -> str:
        """Get the environment name, extracting from content if needed."""
        if self.env_name:
            return self.env_name
        # Extract name from source content
        scheme = self._scheme()
        return scheme.env_name(self.source_content) or "appose-env"

    def _env_dir(self) -> Path:
        """Get the environment directory path."""
        if self.env_dir:
            return self.env_dir
        # Fall back to Appose-managed environments directory
        from ..util.filepath import appose_envs_dir

        return Path(appose_envs_dir()) / self._env_name()

    def _scheme(self) -> Scheme:
        """Get the scheme, detecting from content if needed."""
        if self.scheme:
            return scheme.from_name(self.scheme)
        if self.source_content:
            return scheme.from_content(self.source_content)
        raise ValueError("Cannot determine scheme: neither scheme nor content is set")

    def _create_env(
        self, base: str, bin_paths: list[str], launch_args: list[str]
    ) -> Environment:
        """
        Create an Environment with the given configuration.

        Args:
            base: The base directory path
            bin_paths: List of binary directories to search
            launch_args: Launch arguments to prepend to worker commands

        Returns:
            A new Environment instance
        """

        # Create a simple Environment implementation
        class BuiltEnvironment(Environment):
            def __init__(
                self,
                base_path: str,
                bin_path_list: list[str],
                launch_arg_list: list[str],
                env_var_dict: dict[str, str],
                parent_builder: Builder,
            ):
                super().__init__(base_path)
                self._bin_paths: list[str] = bin_path_list
                self._launch_args: list[str] = launch_arg_list
                self._env_vars: dict[str, str] = env_var_dict
                self._builder: Builder = parent_builder

            def bin_paths(self) -> list[str]:
                return self._bin_paths

            def launch_args(self) -> list[str]:
                return self._launch_args

            def env_vars(self) -> dict[str, str]:
                return self._env_vars

            def builder(self) -> Builder | None:
                return self._builder

        return BuiltEnvironment(base, bin_paths, launch_args, self.env_vars_dict, self)


class SimpleBuilder(BaseBuilder):
    """
    Builder for simple environments without package management.
    Simple environments don't install packages; they use whatever executables
    are found via configured binary paths.
    """

    def __init__(self):
        super().__init__()
        self._custom_bin_paths: list[str] = []

    def name(self) -> str:
        return "custom"

    def bin_paths(self, *paths: str) -> SimpleBuilder:
        """
        Appends additional binary paths to search for executables.
        Paths are searched in the order they are added.

        Args:
            paths: Additional binary paths to search

        Returns:
            This builder instance
        """
        self._custom_bin_paths.extend(paths)
        return self

    def append_system_path(self) -> SimpleBuilder:
        """
        Appends the current process's system PATH directories to the environment's binary paths.

        Returns:
            This builder instance
        """
        system_path = os.environ.get("PATH", "").split(os.pathsep)
        self._custom_bin_paths.extend(system_path)
        return self

    def inherit_running_java(self) -> SimpleBuilder:
        """
        Configures the environment to use the same Java installation as the parent process.
        This prepends ${JAVA_HOME}/bin to the binary paths and sets the JAVA_HOME
        environment variable.

        Returns:
            This builder instance
        """
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            java_home_bin = Path(java_home) / "bin"
            if java_home_bin.is_dir():
                # Prepend to beginning of list for highest priority
                self._custom_bin_paths.insert(0, str(java_home_bin))
            self.env_vars_dict["JAVA_HOME"] = java_home
        return self

    def build(self) -> Environment:
        """Build the simple environment."""
        base = self._env_dir()
        if base is None:
            base = Path(".")

        # Create directory if it doesn't exist
        if not base.exists():
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise BuildException(
                    self, f"Failed to create base directory: {base}", e
                )

        base_path = str(base.absolute())
        launch_args: list[str] = []
        bin_paths: list[str] = []

        # Add bin directory from the environment itself (highest priority)
        bin_dir = base / "bin"
        if bin_dir.is_dir():
            bin_paths.append(str(bin_dir.absolute()))

        # Add custom binary paths configured via builder methods
        bin_paths.extend(self._custom_bin_paths)

        return self._create_env(base_path, bin_paths, launch_args)

    def rebuild(self) -> Environment:
        """SimpleBuilder does not support rebuild."""
        raise NotImplementedError(
            "SimpleBuilder does not support rebuild(). "
            "Custom environments do not manage packages and cannot be rebuilt."
        )

    def set_name(self, env_name: str) -> SimpleBuilder:
        """SimpleBuilder does not support named environments."""
        raise NotImplementedError(
            "SimpleBuilder does not support named environments. "
            "Use base() to specify the working directory."
        )

    def channels(self, *channels: str) -> SimpleBuilder:
        """SimpleBuilder does not support package channels."""
        raise NotImplementedError(
            "SimpleBuilder does not support package channels. "
            "It uses existing executables without package management."
        )

    def _env_dir(self) -> Path:
        """Override to default to current directory."""
        return self.env_dir if self.env_dir else Path(".")


class DynamicBuilder(BaseBuilder):
    """
    Dynamic builder that auto-detects the appropriate specific builder
    based on configuration content and scheme.
    """

    def __init__(self):
        super().__init__()
        self.builder_name: str | None = None

    def builder(self, builder_name: str) -> DynamicBuilder:
        """
        Specifies the preferred builder to use.

        Args:
            builder_name: The builder name (e.g., "pixi", "mamba", "uv")

        Returns:
            This builder instance
        """
        self.builder_name = builder_name
        return self

    def name(self) -> str:
        return "dynamic"

    def build(self) -> Environment:
        """Build by delegating to the appropriate builder."""
        delegate = self._create_builder(self.builder_name, self.scheme)
        self._copy_config_to_delegate(delegate)
        return delegate.build()

    def rebuild(self) -> Environment:
        """Rebuild by delegating to the appropriate builder."""
        delegate = self._create_builder(self.builder_name, self.scheme)
        self._copy_config_to_delegate(delegate)
        return delegate.rebuild()

    def _copy_config_to_delegate(self, delegate: Builder) -> None:
        """Copy configuration from dynamic builder to delegate."""
        delegate.env_vars(self.env_vars_dict)
        if self.env_name:
            delegate.set_name(self.env_name)
        if self.env_dir:
            delegate.base(self.env_dir)
        if self.source_content:
            delegate.content(self.source_content)
        if self.scheme:
            delegate.scheme(self.scheme)
        delegate.channels(*self.channels_list)
        delegate.flags(*self.flags_list)
        for subscriber in self.progress_subscribers:
            delegate.subscribe_progress(subscriber)
        for subscriber in self.output_subscribers:
            delegate.subscribe_output(subscriber)
        for subscriber in self.error_subscribers:
            delegate.subscribe_error(subscriber)

    def _create_builder(
        self,
        name: str | None,
        scheme: str | None,
    ) -> Builder:
        """Create the appropriate builder based on name and scheme."""
        # Find the builder matching the specified name, if any
        if name:
            factory = find_factory_by_name(name)
            if factory is None:
                raise ValueError(f"Unknown builder: {name}")
            return factory.create_builder()

        # Detect scheme from content if content is provided but scheme is not
        effective_scheme = scheme
        if effective_scheme is None and self.source_content:
            effective_scheme = self._scheme().name()

        # Find the highest-priority builder that supports this scheme
        if effective_scheme:
            factory = find_factory_by_scheme(effective_scheme)
            if factory is None:
                raise ValueError(f"No builder supports scheme: {effective_scheme}")
            return factory.create_builder()

        raise ValueError("Content and/or scheme must be provided for dynamic builder")


_BUILDERS: list[BuilderFactory] | None = None


def find_factory_by_name(name: str) -> BuilderFactory | None:
    """
    Finds a factory by name.

    Args:
        name: The builder name to search for

    Returns:
        The factory with matching name, or None if not found
    """
    factories = _discover_factories()
    for factory in factories:
        if factory.name().lower() == name.lower():
            return factory
    return None


def find_factory_by_scheme(scheme: str) -> BuilderFactory | None:
    """
    Finds the first factory that supports the given scheme.
    Factories are checked in priority order.

    Args:
        scheme: The scheme to find a factory for

    Returns:
        The first factory that supports the scheme, or None if none found
    """
    factories = _discover_factories()
    for factory in factories:
        if factory.supports_scheme(scheme):
            return factory
    return None


def find_factory_for_wrapping(env_dir: str | Path) -> BuilderFactory | None:
    """
    Finds the first factory that can wrap the given environment directory.
    Factories are checked in priority order (highest priority first).

    Args:
        env_dir: The directory to find a factory for

    Returns:
        The first factory that can wrap the directory, or None if none found
    """
    factories = _discover_factories()
    for factory in factories:
        if factory.can_wrap(env_dir):
            return factory
    return None


def can_wrap(env_dir: str | Path) -> bool:
    """
    Checks if the given directory can be wrapped as a known environment type.

    Args:
        env_dir: The directory to check

    Returns:
        True if the directory can be wrapped by any known builder
    """
    return find_factory_for_wrapping(env_dir) is not None


def env_type(env_dir: str | Path) -> str | None:
    """
    Returns the environment type name for the given directory.

    Args:
        env_dir: The directory to check

    Returns:
        The environment type name (e.g., "pixi", "mamba", "uv"), or None if not a known environment
    """
    factory = find_factory_for_wrapping(env_dir)
    return factory.name() if factory else None


def _discover_factories() -> list[BuilderFactory]:
    """
    Discover all BuilderFactory implementations via entry points.

    Returns:
        List of factories sorted by priority (highest first)
    """
    global _BUILDERS
    if _BUILDERS is not None:
        return _BUILDERS

    factories: list[BuilderFactory] = []

    # Try modern importlib.metadata (Python 3.8+)
    try:
        from importlib.metadata import entry_points
    except ImportError:
        # Fall back to importlib_metadata for older Python
        try:
            from importlib_metadata import entry_points
        except ImportError:
            # If no entry point support, use hardcoded defaults
            from .pixi import PixiBuilderFactory
            from .mamba import MambaBuilderFactory
            from .uv import UvBuilderFactory

            _BUILDERS = sorted(
                [
                    PixiBuilderFactory(),
                    MambaBuilderFactory(),
                    UvBuilderFactory(),
                ],
                key=lambda f: f.priority(),
                reverse=True,
            )
            return _BUILDERS

    # Load from entry points
    eps = entry_points()
    # Handle both old and new entry_points() API
    if hasattr(eps, "select"):
        # New API (Python 3.10+)
        builder_eps = eps.select(group="appose.builders")
    else:
        # Old API (Python 3.8-3.9)
        builder_eps = eps.get("appose.builders", [])

    for ep in builder_eps:
        try:
            factory_class = ep.load()
            factories.append(factory_class())
        except Exception as e:
            print(
                f"Warning: Failed to load builder factory {ep.name}: {e}",
                file=sys.stderr,
            )

    # If no entry points found, fall back to hardcoded defaults
    if not factories:
        from .pixi import PixiBuilderFactory
        from .mamba import MambaBuilderFactory
        from .uv import UvBuilderFactory

        factories = [
            PixiBuilderFactory(),
            MambaBuilderFactory(),
            UvBuilderFactory(),
        ]

    # Sort by priority (highest first)
    factories.sort(key=lambda f: f.priority(), reverse=True)
    _BUILDERS = factories
    return factories
