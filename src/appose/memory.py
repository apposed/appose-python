# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Managed shared memory: the interface between Appose and the backends that
provide managed memory, and the registry of those backends.

A backend allocates managed memory (see NDArray(..., managed=True)), and
keeps track of which processes use it, freeing it once none does anymore.
Each process uses one backend; the service picks it (by default, "builtin"),
and tells its workers which, so that they use the matching worker side.

Over each connection between a service and a worker, the backend provides a
MemoryLink, through which Appose sends and receives references to managed
memory: the backend decides what a reference consists of on the wire, and
what sending or receiving one entails.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .shm import SharedMemoryView

# The environment variable by which a service tells its workers which
# backend provides managed memory.
ENV_VAR = "APPOSE_SHM"


class Peer(ABC):
    """
    The other end of a connection, as a memory backend may use it.
    """

    def send(self, message: dict[str, Any]) -> None:
        """Send a message (e.g. a RELEASE response) to the peer."""
        raise NotImplementedError

    def call(self, function: str, *args: Any) -> Any:
        """
        Call a function the peer (a service) exports, and return its result.
        Only available in a worker, and never from its receiver thread.
        """
        raise NotImplementedError

    def export(self, name: str, obj: Any) -> None:
        """
        Export an object (e.g. a function) for the peer (a worker) to call.
        Only available in a service.
        """
        raise NotImplementedError


class MemoryLink(ABC):
    """
    Managed memory as used over one connection: from a service to one of its
    workers, or from a worker to its service.
    """

    @abstractmethod
    def describe(self, view: SharedMemoryView) -> dict[str, Any]:
        """
        Return the fields of a reference to the given managed region, to send
        over this link (besides "appose_type" and "managed", which Appose adds).
        Called while encoding a message, which may yet fail.
        """

    def sent(self, views: list[SharedMemoryView]) -> None:
        """
        Record that references to the given managed regions are about to be
        sent over this link: the message is encoded, but not yet written.
        """

    @abstractmethod
    def resolve(self, ref: dict[str, Any]) -> SharedMemoryView:
        """
        Return a view of the managed region that the given reference, received
        over this link, refers to.
        """

    def released(self, regions: list[dict[str, Any]]) -> None:
        """Handle a RELEASE message received over this link."""

    def close(self) -> None:
        """The connection is gone, e.g. the worker terminated."""


class MemoryBackend(ABC):
    """A provider of managed shared memory, for one process."""

    @abstractmethod
    def allocate(self, nbytes: int) -> SharedMemoryView:
        """Allocate a managed region, and return a view of it."""

    @abstractmethod
    def link(self, peer: Peer) -> MemoryLink:
        """Create the link for a new connection to the given peer."""


# Registered backends, by name: functions creating their service side and
# their worker side.
_backends: dict[
    str, tuple[Callable[[], MemoryBackend], Callable[[], MemoryBackend]]
] = {}

# The backend of this process, and its name.
_backend: MemoryBackend | None = None
_backend_name: str | None = None


def register(
    name: str,
    service_side: Callable[[], MemoryBackend],
    worker_side: Callable[[], MemoryBackend],
) -> None:
    """
    Register a memory backend.

    Args:
        name: The backend's name, by which a service tells its workers to use it.
        service_side: Function creating the backend for a service process.
        worker_side: Function creating the backend for a worker process.
    """
    _backends[name] = (service_side, worker_side)


def use(name: str) -> None:
    """
    Make this process use the named memory backend, before it allocates
    or exchanges any managed memory.
    """
    global _backend, _backend_name
    from .util import message

    if name not in _backends:
        raise ValueError(f"No such memory backend: {name}")
    if _backend is not None and _backend_name != name:
        raise RuntimeError(f"This process already uses memory backend {_backend_name}")
    service_side, worker_side = _backends[name]
    _backend = (worker_side if message._worker_mode else service_side)()
    _backend_name = name


def backend() -> MemoryBackend | None:
    """
    Return this process's memory backend: in a service, the builtin one unless
    another was chosen; in a worker, the one its service uses, if supported.
    """
    from .util import message

    if _backend is None and not message._worker_mode:
        use("builtin")
    return _backend


def backend_name() -> str | None:
    """Return the name of this process's memory backend, if any."""
    backend()
    return _backend_name


def use_from_environment() -> None:
    """In a worker, use the memory backend its service announced, if known."""
    name = os.environ.get(ENV_VAR)
    if name in _backends:
        use(name)


def allocate(nbytes: int) -> SharedMemoryView:
    """Allocate a managed region from this process's memory backend."""
    memory = backend()
    if memory is None:
        raise ValueError("No managed shared memory is available in this process")
    return memory.allocate(nbytes)


# NB: Register the builtin backend.
from . import builtin_memory  # noqa: F401
