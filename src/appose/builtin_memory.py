# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
The builtin memory backend: the service owns all managed memory, in slabs of
fixed-size slots, and counts the references to each region; workers ask the
service for memory, and tell it when they are done with what they received.

See docs/design-shared-memory.md in apposed/appose.
"""

from __future__ import annotations

import queue
import threading
import weakref
from typing import Any, Callable

from . import memory
from .memory import MemoryBackend, MemoryLink, Peer
from .shm import SharedMemory, SharedMemoryView, _attach_view, _check_region

# The service function by which workers allocate managed memory.
ALLOCATE = "_appose_allocate"


def _fields(view: SharedMemoryView) -> dict[str, Any]:
    return {
        "name": view.name,
        "rsize": view.rsize,
        "offset": view.offset,
        "length": view.length,
    }


def _region_of(ref: dict[str, Any]) -> tuple[str, int, int, int]:
    name, rsize = ref["name"], ref["rsize"]
    offset = ref.get("offset", 0)
    length = ref.get("length", rsize - offset)
    _check_region(name, rsize, offset, length)
    return name, rsize, offset, length


# -- Service side --


class _Slab:
    """A shared memory block divided into fixed-size slots."""

    def __init__(self, slot_size: int, slots: int) -> None:
        self.block = SharedMemory(create=True, rsize=slot_size * slots)
        self.slot_size = slot_size
        self.free = list(range(slots - 1, -1, -1))
        self.slots = slots


class _Region:
    """A managed region: a slot of a slab, and who holds it."""

    def __init__(self, slab: _Slab, slot: int) -> None:
        self.slab = slab
        self.slot = slot
        self.offset = slot * slab.slot_size
        # Number of views of the region in this process.
        self.views = 0
        # Number of references held by each peer, e.g. each worker.
        self.peers: dict[Any, int] = {}


class SlabMemory(MemoryBackend):
    """
    The service side of the builtin backend: slabs of fixed-size slots, and
    the number of references to each slot's region. A region is freed once no
    view of it remains in this process, and no peer holds a reference to it.
    """

    # Slots are aligned to (and sized in multiples of) this many bytes.
    ALIGN = 64

    # The size beyond which a slab gets no more slots.
    MAX_SLAB_BYTES = 64 * 1024 * 1024

    def __init__(self) -> None:
        self._slabs: dict[int, list[_Slab]] = {}
        self._regions: dict[tuple[str, int], _Region] = {}
        self._lock = threading.Lock()
        # NB: Finalizers of collected views queue their regions here, for a
        # thread to process, so that no finalizer ever waits for the lock.
        self._collected: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None

    def allocate(self, nbytes: int) -> SharedMemoryView:
        slot_size = max(-(-nbytes // self.ALIGN) * self.ALIGN, self.ALIGN)
        with self._lock:
            slabs = self._slabs.setdefault(slot_size, [])
            slab = next((s for s in slabs if s.free), None)
            if slab is None:
                # NB: Each new slab of a slot size holds twice as many slots
                # as the last, up to MAX_SLAB_BYTES: one-off arrays take a
                # block each, while many arrays of one size share few blocks.
                most = max(1, self.MAX_SLAB_BYTES // slot_size)
                slab = _Slab(slot_size, min(2 ** len(slabs), most))
                slabs.append(slab)
            region = _Region(slab, slab.free.pop())
            self._regions[(slab.block.name, region.offset)] = region
            return self._view(region, nbytes)

    def link(self, peer: Peer) -> MemoryLink:
        return _ServiceLink(self, peer)

    def resolve(self, name: str, offset: int, length: int) -> SharedMemoryView:
        """Return a new view of the given managed region of this process."""
        with self._lock:
            region = self._regions.get((name, offset))
            if region is None or length > region.slab.slot_size:
                raise ValueError(
                    f"No such managed shared memory region: {name} at {offset}"
                )
            return self._view(region, length)

    def lend(self, views: list[SharedMemoryView], peer: Any) -> None:
        """Count a reference held by the given peer to each given region."""
        with self._lock:
            for view in views:
                if view._release is None:
                    raise ValueError(f"{view} was already disposed of")
                region = self._regions[(view.name, view.offset)]
                region.peers[peer] = region.peers.get(peer, 0) + 1

    def release(self, peer: Any, regions: list[dict[str, Any]]) -> None:
        """Count the given references as returned by the given peer."""
        with self._lock:
            for r in regions:
                region = self._regions.get((r["name"], r["offset"]))
                count = None if region is None else region.peers.get(peer)
                if count is None:
                    continue
                if count > 1:
                    region.peers[peer] = count - 1
                else:
                    del region.peers[peer]
                    self._free_if_unused(region)

    def drop(self, peer: Any) -> None:
        """Forget all references held by the given peer, e.g. once it is gone."""
        with self._lock:
            for region in list(self._regions.values()):
                if region.peers.pop(peer, None) is not None:
                    self._free_if_unused(region)

    def _view(self, region: _Region, length: int) -> SharedMemoryView:
        slab = region.slab
        view = SharedMemoryView(
            slab.block._mmap,
            slab.block.name,
            slab.block.rsize,
            region.offset,
            length,
            True,
        )
        region.views += 1
        finalizer = weakref.finalize(view, self._collected.put, region)
        finalizer.atexit = False
        view._release = finalizer
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._loop, name="Appose-Memory", daemon=True
            )
            self._thread.start()
        return view

    def _loop(self) -> None:
        while True:
            region = self._collected.get()
            with self._lock:
                region.views -= 1
                self._free_if_unused(region)

    def _free_if_unused(self, region: _Region) -> None:
        if region.views > 0 or region.peers:
            return
        slab = region.slab
        del self._regions[(slab.block.name, region.offset)]
        slab.free.append(region.slot)
        if len(slab.free) == slab.slots:
            # The slab is empty: retire it.
            self._slabs[slab.slot_size].remove(slab)
            slab.block.unlink()
            slab.block.close()


class _ServiceLink(MemoryLink):
    """The builtin backend's link from the service to one worker."""

    def __init__(self, memory: SlabMemory, peer: Peer) -> None:
        self._memory = memory
        # NB: Workers allocate managed memory by calling this function.
        peer.export(ALLOCATE, memory.allocate)

    def describe(self, view: SharedMemoryView) -> dict[str, Any]:
        return _fields(view)

    def sent(self, views: list[SharedMemoryView]) -> None:
        self._memory.lend(views, self)

    def resolve(self, ref: dict[str, Any]) -> SharedMemoryView:
        # NB: A worker refers to a region of the service's own memory.
        name, _, offset, length = _region_of(ref)
        return self._memory.resolve(name, offset, length)

    def released(self, regions: list[dict[str, Any]]) -> None:
        self._memory.release(self, regions)

    def close(self) -> None:
        self._memory.drop(self)


# -- Worker side --


class SlabClient(MemoryBackend):
    """
    The worker side of the builtin backend: asks the service for managed
    memory, and tells it when done with the references it received.
    """

    def __init__(self) -> None:
        self._link: _WorkerLink | None = None

    def allocate(self, nbytes: int) -> SharedMemoryView:
        if self._link is None:
            raise ValueError("Not connected to a service")
        view = self._link.peer.call(ALLOCATE, nbytes)
        if not isinstance(view, SharedMemoryView) or not view.managed:
            raise ValueError(f"The service allocated no managed shared memory: {view}")
        return view

    def link(self, peer: Peer) -> MemoryLink:
        self._link = _WorkerLink(peer)
        return self._link


class _WorkerLink(MemoryLink):
    """The builtin backend's link from a worker to its service."""

    def __init__(self, peer: Peer) -> None:
        self.peer = peer
        self._releaser = _Releaser(
            lambda regions: peer.send({"responseType": "RELEASE", "regions": regions})
        )
        self._releaser.start("Appose-Releaser")

    def describe(self, view: SharedMemoryView) -> dict[str, Any]:
        return _fields(view)

    def resolve(self, ref: dict[str, Any]) -> SharedMemoryView:
        view = _attach_view(*_region_of(ref), managed=True)
        self._releaser.track(view)
        return view

    def close(self) -> None:
        self._releaser.stop()


class _Releaser:
    """
    Gives up this process's references to managed regions it received, by
    telling the service in batches, once their views are disposed of or
    garbage collected.
    """

    def __init__(self, send: Callable[[list[dict[str, Any]]], None]) -> None:
        self._send = send
        # NB: SimpleQueue.put is reentrant, so it is safe in finalizers.
        self._queue: queue.SimpleQueue = queue.SimpleQueue()

    def track(self, view: SharedMemoryView) -> None:
        finalizer = weakref.finalize(view, self._queue.put, (view.name, view.offset))
        finalizer.atexit = False
        view._release = finalizer

    def start(self, name: str) -> None:
        threading.Thread(target=self._loop, name=name, daemon=True).start()

    def stop(self) -> None:
        self._queue.put(None)

    def _loop(self) -> None:
        while True:
            batch = [self._queue.get()]
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            regions = [{"name": n, "offset": o} for n, o in filter(None, batch)]
            if regions:
                try:
                    self._send(regions)
                except Exception:  # noqa: BLE001, S110 -- the service is gone, and so are its counts
                    pass
            if None in batch:
                return


memory.register("builtin", SlabMemory, SlabClient)
