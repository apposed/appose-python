# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

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
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

from ..environment import Environment
from ..scheme import (
    Scheme,
    from_content as scheme_from_content,
    from_name as scheme_from_name,
)
from ..util.filepath import appose_envs_dir


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
            noun = "build" if builder is None else f"{builder.env_type()} build"
            verb = "interrupted" if isinstance(cause, KeyboardInterrupt) else "failed"
            message = f"{noun} {verb}"
        super().__init__(message)
        self.builder: Builder | None = builder
        self.__cause__: Exception | None = cause


class Builder(ABC):
    """
    Base class for all Appose environment builders.

    Builders are responsible for creating and configuring Appose environments.

    The type parameter enables fluent method chaining to return the concrete
    builder type without requiring subclasses to override every method.
    """

    @abstractmethod
    def env_type(self) -> str:
        """
        Get the environment type constructed by this builder (e.g., "pixi", "mamba", "uv").

        Returns:
            The builder's associated environment type.
        """
        ...

    @abstractmethod
    def build(self) -> Environment:
        """
        Build the environment. This is the terminator method for any fluid building chain.

        Returns:
            The newly constructed Appose Environment

        Raises:
            BuildException: If the build fails due to I/O errors, interruption,
                or other build-related issues
        """
        ...

    def rebuild(self) -> Environment:
        """
        Rebuild the environment from scratch.

        Deletes the existing environment directory (if it exists) and rebuilds it
        using the current builder configuration. This is more robust than trying to
        update an existing environment in place.

        This method is a shorthand for delete() then build().

        Returns:
            The newly rebuilt Environment

        Raises:
            BuildException: If the build fails
        """
        try:
            self.delete()
        except Exception as e:
            raise BuildException(self, cause=e)
        return self.build()

    @abstractmethod
    def delete(self) -> None:
        """
        Delete the builder's linked environment directory, if any.

        Raises:
            OSError: If something goes wrong during deletion
        """
        ...

    @abstractmethod
    def wrap(self, env_dir: str | Path) -> Environment:
        """
        Wrap an existing environment directory, detecting and using any
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

    @abstractmethod
    def env(self, **vars: str) -> Builder:
        """
        Set environment variables to be passed to worker processes.

        Args:
            vars: Dictionary of environment variable names to values

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def name(self, env_name: str) -> Builder:
        """
        Set the name for the environment.
        The environment will be created in the standard Appose environments directory with this name.

        Args:
            env_name: The name for the environment

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def base(self, env_dir: str | Path) -> Builder:
        """
        Set the base directory for the environment.
        For many builders, this overrides any name specified via name().

        Args:
            env_dir: The directory for the environment

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def channels(self, *channels: str) -> Builder:
        """
        Add channels/repositories to search for packages.

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
        Specify a configuration file to build from.

        Reads the file content immediately and delegates to content().

        Args:
            path: Path to configuration file (e.g., "pixi.toml", "environment.yml")

        Returns:
            This builder instance, for fluent-style programming

        Raises:
            BuildException: If the file cannot be read
        """
        try:
            file_path = Path(path)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.content(content)
        except Exception as e:
            raise BuildException(self, cause=e)

    def url(self, url: str) -> Builder:
        """
        Specify a URL to fetch configuration content from.

        Reads the URL content immediately and delegates to content().

        Args:
            url: URL to configuration file

        Returns:
            This builder instance, for fluent-style programming

        Raises:
            BuildException: If the URL cannot be read
        """
        try:
            with urlopen(url) as response:
                content = response.read().decode("utf-8")
            return self.content(content)
        except Exception as e:
            raise BuildException(self, cause=e)

    @abstractmethod
    def content(self, content: str) -> Builder:
        """
        Specify configuration file content to build from.

        The scheme will be auto-detected from content syntax.

        Args:
            content: Configuration file content

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def scheme(self, scheme: str) -> Builder:
        """
        Explicitly specify the scheme for the configuration.

        This overrides auto-detection.

        Args:
            scheme: The scheme (e.g., "pixi.toml", "environment.yml", "requirements.txt")

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def subscribe_progress(self, subscriber: ProgressConsumer) -> Builder:
        """
        Register a callback to be invoked when progress happens during environment building.

        Args:
            subscriber: Function to call with (title, current, maximum) when progress happens

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def subscribe_output(self, subscriber: Callable[[str], None]) -> Builder:
        """
        Register a callback to be invoked when output is generated during environment building.

        Args:
            subscriber: Function to call with output strings

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def subscribe_error(self, subscriber: Callable[[str], None]) -> Builder:
        """
        Register a callback to be invoked when errors occur during environment building.

        Args:
            subscriber: Function to call with error strings

        Returns:
            This builder instance, for fluent-style programming
        """
        ...

    @abstractmethod
    def flags(self, *flags: str) -> Builder:
        """
        Add command-line flags to be passed to the underlying tool during build operations.

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
        return self.subscribe_output(
            lambda msg: print(msg, file=sys.stdout, end="")
        ).subscribe_error(lambda msg: print(msg, file=sys.stderr, end=""))


class BuilderFactory(ABC):
    """
    Factory base class for creating builder instances.

    Implementations are discovered at runtime via entry points and managed by
    the Builders utility class.
    """

    @abstractmethod
    def create_builder(self) -> Builder:
        """
        Create a new builder instance with no configuration.
        Configuration should be provided via the fluent API (e.g., content, scheme).

        Returns:
            A new builder instance.
        """
        ...

    @abstractmethod
    def env_type(self) -> str:
        """
            Get the environment type handled by this builder (e.g., "pixi", "mamba", "uv").

        Returns:
                The builder's associated environment type.
        """
        ...

    @abstractmethod
    def supports_scheme(self, scheme: str) -> bool:
        """
        Check if this builder supports the given scheme.

        Args:
            scheme: The scheme to check (e.g., "environment.yml", "conda", "pypi")

        Returns:
            True if this builder supports the scheme
        """
        ...

    @abstractmethod
    def priority(self) -> float:
        """
        Return the priority of this builder for scheme resolution.

        Higher priority builders are preferred when multiple builders support the same scheme.

        Returns:
            The priority value (higher = more preferred)
        """
        ...

    @abstractmethod
    def can_wrap(self, env_dir: str | Path) -> bool:
        """
        Check if this builder can wrap the given existing environment directory.

        Args:
            env_dir: The directory to check

        Returns:
            True if this builder can wrap the directory
        """
        ...


class BaseBuilder(Builder):
    """
    Base class for environment builders.
    Provides common implementation for the Builder protocol.
    """

    def __init__(self):
        self._progress_subscribers: list[ProgressConsumer] = []
        self._output_subscribers: list[Callable[[str], None]] = []
        self._error_subscribers: list[Callable[[str], None]] = []
        self._env_vars: dict[str, str] = {}
        self._channels: list[str] = []
        self._flags: list[str] = []
        self._env_name: str | None = None
        self._env_dir: Path | None = None
        self._content: str | None = None
        self._scheme: Scheme | None = None

    def delete(self) -> None:
        """Default implementation: delete env_dir if it exists."""
        dir_path = self._env_dir
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

    def env(self, **vars: str) -> BaseBuilder:
        """Set environment variables."""
        self._env_vars.update(vars)
        return self

    def name(self, env_name: str) -> BaseBuilder:
        """Set the environment name."""
        self._env_name = env_name
        return self

    def base(self, env_dir: str | Path) -> BaseBuilder:
        """Set the base directory."""
        self._env_dir = Path(env_dir)
        return self

    def channels(self, *channels: str) -> BaseBuilder:
        """Add channels."""
        self._channels.extend(channels)
        return self

    def content(self, content: str) -> BaseBuilder:
        """Set configuration content."""
        self._content = content
        return self

    def scheme(self, scheme: str | Scheme) -> BaseBuilder:
        """Set the explicit scheme."""
        self._scheme = (
            scheme if isinstance(scheme, Scheme) else scheme_from_name(scheme)
        )
        return self

    def subscribe_progress(self, subscriber: ProgressConsumer) -> BaseBuilder:
        """Register a progress callback."""
        self._progress_subscribers.append(subscriber)
        return self

    def subscribe_output(self, subscriber: Callable[[str], None]) -> BaseBuilder:
        """Register an output callback."""
        self._output_subscribers.append(subscriber)
        return self

    def subscribe_error(self, subscriber: Callable[[str], None]) -> BaseBuilder:
        """Register an error callback."""
        self._error_subscribers.append(subscriber)
        return self

    def flags(self, *flags: str) -> BaseBuilder:
        """Add command-line flags."""
        self._flags.extend(flags)
        return self

    # -- Helper methods --

    def _resolve_env_dir(self) -> Path:
        """Determine the environment directory path."""
        if self._env_dir:
            return self._env_dir

        # No explicit environment directory set; fall back to
        # a subfolder of the Appose-managed environments directory.
        dir_name = (
            self._env_name
            if self._env_name is not None
            # No explicit environment name set; extract name from the source content.
            else (self._resolve_scheme().env_name(self._content))
        )

        return Path(appose_envs_dir()) / dir_name

    def _resolve_scheme(self) -> Scheme:
        """Determine the scheme, detecting from content if needed."""
        if self._scheme:
            return self._scheme
        if self._content:
            return scheme_from_content(self._content)
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

        class BuiltEnvironment(Environment):
            """A simple Environment implementation."""

            def __init__(
                self,
                base_path: str,
                bin_paths: list[str],
                launch_args: list[str],
                env_vars: dict[str, str],
                builder: Builder,
            ):
                super().__init__(base_path)
                self._bin_paths: list[str] = bin_paths
                self._launch_args: list[str] = launch_args
                self._env_vars: dict[str, str] = env_vars
                self._builder: Builder = builder

            def bin_paths(self) -> list[str]:
                return self._bin_paths

            def launch_args(self) -> list[str]:
                return self._launch_args

            def env_vars(self) -> dict[str, str]:
                return self._env_vars

            def builder(self) -> Builder:
                return self._builder

        return BuiltEnvironment(base, bin_paths, launch_args, self._env_vars, self)


class SimpleBuilder(BaseBuilder):
    """
    Builder for simple environments without package management.
    Simple environments don't install packages; they use whatever executables
    are found via configured binary paths.
    """

    def __init__(self):
        super().__init__()
        self._custom_bin_paths: list[str] = []

    def bin_paths(self, *paths: str) -> SimpleBuilder:
        """
        Append additional binary paths to search for executables.

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
        Append the current process's system PATH directories to the environment's binary paths.

        Returns:
            This builder instance
        """
        system_path = os.environ.get("PATH", "").split(os.pathsep)
        self._custom_bin_paths.extend(system_path)
        return self

    def inherit_running_java(self) -> SimpleBuilder:
        """
        Configure the environment to use the same Java installation as the parent process.

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
            self._env_vars["JAVA_HOME"] = java_home
        return self

    def env_type(self) -> str:
        return "custom"

    def build(self) -> Environment:
        """Build the simple environment."""
        base = self._resolve_env_dir()
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

    def name(self, env_name: str) -> SimpleBuilder:
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

    def _resolve_env_dir(self) -> Path:
        """Override to default to current directory."""
        return self._env_dir if self._env_dir else Path(".")


class DynamicBuilder(BaseBuilder):
    """
    Dynamic builder that auto-detects the appropriate specific builder
    based on configuration content and scheme.
    """

    def __init__(self):
        super().__init__()
        self._env_type: str | None = None

    def builder(self, env_type: str) -> DynamicBuilder:
        """
        Specify the preferred builder to use.

        Args:
            env_type: The builder's environment type (e.g., "pixi", "mamba", "uv")

        Returns:
            This builder instance, for fluent-style programming.
        """
        self._env_type = env_type
        return self

    def env_type(self) -> str:
        return self._env_type if self._env_type is not None else "dynamic"

    def build(self) -> Environment:
        """Build by delegating to the appropriate builder."""
        delegate = self._create_builder()
        self._copy_config_to_delegate(delegate)
        return delegate.build()

    def rebuild(self) -> Environment:
        """Rebuild by delegating to the appropriate builder."""
        delegate = self._create_builder()
        self._copy_config_to_delegate(delegate)
        return delegate.rebuild()

    def _copy_config_to_delegate(self, delegate: Builder) -> None:
        """Copy configuration from dynamic builder to delegate."""
        delegate.env(**self._env_vars)
        if self._env_name:
            delegate.name(self._env_name)
        if self._env_dir:
            delegate.base(self._env_dir)
        if self._content:
            delegate.content(self._content)
        if self._scheme:
            delegate.scheme(self._scheme.name())
        delegate.channels(*self._channels)
        delegate.flags(*self._flags)
        for subscriber in self._progress_subscribers:
            delegate.subscribe_progress(subscriber)
        for subscriber in self._output_subscribers:
            delegate.subscribe_output(subscriber)
        for subscriber in self._error_subscribers:
            delegate.subscribe_error(subscriber)

    def _create_builder(self) -> Builder:
        """Create the appropriate builder based on name and scheme."""
        # Find the builder matching the specified name, if any
        if self._env_type:
            factory = find_factory_by_env_type(self._env_type)
            if factory is None:
                raise ValueError(f"Unknown builder: {self._env_type}")
            return factory.create_builder()

        # Detect scheme from content if content is provided but scheme is not.
        actual_scheme = self._scheme
        if actual_scheme is None and self._content:
            actual_scheme = self._resolve_scheme()

        # Find the highest-priority builder that supports this scheme.
        if actual_scheme is not None:
            factory = find_factory_by_scheme(actual_scheme.name())
            if factory is None:
                raise ValueError(f"No builder supports scheme: {actual_scheme.name()}")
            return factory.create_builder()

        raise ValueError("Content and/or scheme must be provided for dynamic builder")


_BUILDERS: list[BuilderFactory] | None = None


def find_factory_by_env_type(env_type: str) -> BuilderFactory | None:
    """
    Find the first factory capable of building a particular type of environment.
    Factories are checked in priority order.

    Args:
        env_type: The environment type to target.

    Returns:
        A factory supporting the environment type, or None if not found.
    """
    factories = _discover_factories()
    for factory in factories:
        if factory.env_type().lower() == env_type.lower():
            return factory
    return None


def find_factory_by_scheme(scheme: str) -> BuilderFactory | None:
    """
    Find the first factory that supports the given scheme.
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
    Find the first factory that can wrap the given environment directory.
    Factories are checked in priority order.

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
    Check if the given directory can be wrapped as a known environment type.

    Args:
        env_dir: The directory to check

    Returns:
        True if the directory can be wrapped by any known builder
    """
    return find_factory_for_wrapping(env_dir) is not None


def env_type(env_dir: str | Path) -> str | None:
    """
    Return the environment type name for the given directory.

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
