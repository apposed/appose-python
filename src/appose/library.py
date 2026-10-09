# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Worker-side support for library code registered via Service.import_library.

A library is a module (single source file) or package (directory of source
files) whose source code the service sends to the worker. Once registered,
the library is importable by its name from any task, via a normal `import`
statement, and lives in sys.modules like any other module. Its module-level
state therefore persists across tasks, making it a natural home for expensive
objects such as loaded models, without any need for task.export.

Registration does not import the library; the first `import` statement does.
"""

from __future__ import annotations

import importlib.abc
import sys
import threading
from importlib.machinery import ModuleSpec
from pathlib import Path

try:
    from importlib.resources.abc import TraversableResources
except ImportError:  # Python < 3.11
    from importlib.abc import TraversableResources


class _Library:
    def __init__(
        self, name: str, files: dict[str, str], origin: str, package: bool
    ) -> None:
        self.name = name
        # Relative POSIX path (e.g. "__init__.py", "sub/mod.py") -> source code.
        self.files = files
        # Location of the library on the service side, for __file__ and tracebacks.
        self.origin = origin
        self.package = package

    def locate(self, fullname: str) -> tuple[str, bool] | None:
        """
        Find the source file for the given (sub)module of this library.

        Returns:
            A (relative path, is package) pair, or None if not found.
        """
        if not self.package:
            return (next(iter(self.files)), False) if fullname == self.name else None
        parts = fullname.split(".")[1:]
        prefix = "/".join(parts) + "/" if parts else ""
        if any(f.startswith(prefix) for f in self.files):
            # NB: A directory without __init__.py is still a (sub)package.
            return prefix + "__init__.py", True
        if "/".join(parts) + ".py" in self.files:
            return "/".join(parts) + ".py", False
        return None

    def source(self, relpath: str) -> str:
        return self.files.get(relpath, "")

    def filename(self, relpath: str) -> str:
        return f"{self.origin}/{relpath}" if self.package else self.origin


class _LibraryResources(TraversableResources):
    def __init__(self, path: Path) -> None:
        self._path = path

    def files(self) -> Path:
        return self._path


class _LibraryLoader(importlib.abc.SourceLoader):
    def __init__(self, library: _Library, relpath: str, is_package: bool) -> None:
        self._library = library
        self._relpath = relpath
        self._is_package = is_package

    def get_filename(self, fullname: str) -> str:
        return self._library.filename(self._relpath)

    def get_data(self, path: str) -> bytes:
        # NB: SourceLoader requests source by filename; we always know which.
        return self._library.source(self._relpath).encode("utf-8")

    def is_package(self, fullname: str) -> bool:
        return self._is_package

    def get_resource_reader(self, fullname: str) -> TraversableResources | None:
        # NB: Resources are read from the package's directory on disk, so they
        # are available only for packages registered by path.
        if not self._is_package:
            return None
        path = Path(self.get_filename(fullname)).parent
        return _LibraryResources(path) if path.is_dir() else None


class _LibraryFinder(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.libraries: dict[str, _Library] = {}

    def find_spec(self, fullname, path=None, target=None) -> ModuleSpec | None:
        library = self.libraries.get(fullname.split(".")[0])
        if library is None:
            return None
        located = library.locate(fullname)
        if located is None:
            return None
        relpath, is_package = located
        loader = _LibraryLoader(library, relpath, is_package)
        # NB: We avoid spec_from_file_location (also used by spec_from_loader),
        # which sets a package's __path__ to the origin directory, letting the
        # standard path-based finder bypass us and read submodules from disk.
        spec = ModuleSpec(
            fullname,
            loader,
            origin=loader.get_filename(fullname),
            is_package=is_package,
        )
        spec.has_location = True
        return spec


_finder = _LibraryFinder()
_lock = threading.Lock()


def register(
    name: str, files: dict[str, str], origin: str, package: bool = False
) -> None:
    """
    Make library code importable in this process under the given name.

    Registering a library whose source is unchanged is a no-op, so any
    already-imported module (and the state it holds) is retained. If the
    source has changed, the stale module is evicted from sys.modules, so
    that the next import picks up the new code.

    Args:
        name: The top-level module name to import the library as.
        files: Mapping from relative POSIX path to source code. For a
            single-file module, this has exactly one entry: the file's name.
        origin: Path of the library on the service side.
        package: True if the library is a package (directory), False if it is
            a single-file module.
    """
    with _lock:
        if _finder not in sys.meta_path:
            # NB: Registered libraries take precedence over installed modules,
            # since registration is an explicit request for this exact code.
            sys.meta_path.insert(0, _finder)
        existing = _finder.libraries.get(name)
        if existing is not None and existing.files == files:
            return
        _finder.libraries[name] = _Library(name, files, origin, package)
        for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
            del sys.modules[mod]
        importlib.invalidate_caches()
