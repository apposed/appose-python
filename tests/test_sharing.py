# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Showcase of the ways to share array data between processes.

Each test is a small, realistic scenario. Read them as examples:

- Managed memory, handed off: send an array and stop using it, and the
  receiver has it to itself. Plain NumPy arrays travel this way: copied
  into the service's managed memory once, then shared by reference.
- Managed memory, shared: keep using an array after sending it, and every
  holder views the same memory. Use it for cached image cells, or output
  images that workers write into.
- Unmanaged memory: a block the application creates and frees itself,
  e.g. a buffer reused across many calls, or a worker's own ring buffer.

The service owns all managed memory, and frees each region once no process
uses it anymore. See the "Sharing Arrays Between Processes" page of the
Appose docs.
"""

from __future__ import annotations

import gc
import time

import numpy

import appose
from appose import NDArray, memory
from tests.test_base import maybe_debug
from tests.test_base import shm_unlinked as unlinked

# This process's memory backend (the builtin one, in a service).
_memory = memory.backend()


def python_service():
    service = appose.system().python().init("import numpy")
    maybe_debug(service)
    return service


def eventually(condition, timeout: float = 5) -> bool:
    """Waits for the condition, collecting garbage meanwhile."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        gc.collect()
        time.sleep(0.02)
    return True


def all_freed() -> bool:
    """Whether the service has freed all of its managed memory."""
    return eventually(lambda: not _memory._regions)


# -- Managed memory, handed off --


def test_handoff_result():
    """
    A worker thresholds an image, and hands the resulting mask back.

    The image travels as a plain NumPy array: copied once into managed
    memory, which the worker receives as a NumPy array it may modify freely,
    since the service no longer refers to it. Likewise, the mask comes back
    as a NumPy array of the service's own. Each region is freed once its
    last holder is done with it.
    """
    image = numpy.linspace(0, 1, 16, dtype=numpy.float32).reshape(4, 4)
    with python_service() as worker:
        task = worker.task(
            "image *= 2  # The worker's own copy: modify at will.\nimage > 1",
            {"image": image},
        ).wait_for()

    mask = task.result()
    assert isinstance(mask, numpy.ndarray)
    assert mask.dtype == bool
    numpy.testing.assert_array_equal(mask, image * 2 > 1)
    assert image.max() == 1  # The service's original is unaffected.
    del task, mask
    assert all_freed()


def test_handoff_chunks_from_reader():
    """
    A worker pulls chunks of a large image from a reader in the service.

    The reader decodes each chunk straight into a managed array, so the chunk
    is never copied: the worker receives it, as a NumPy array, and the chunk
    is freed once the worker is done with it.
    """

    class ChunkReader:
        def read(self, index):
            chunk = NDArray("uint16", [64, 64], managed=True)
            numpy.asarray(chunk)[:] = index  # E.g. decompress into the chunk.
            return chunk

    with python_service() as worker:
        task = worker.task(
            "[int(reader.read(i).sum()) for i in range(3)]",
            {"reader": ChunkReader()},
        ).wait_for()
    assert task.result() == [0, 64 * 64, 2 * 64 * 64]
    assert all_freed()


# -- Managed memory, shared --


class CellCache:
    """
    A service-side cache of image cells, each loaded once into managed
    memory, so that any number of workers can view it in place.
    """

    def __init__(self):
        self.cells: dict[int, NDArray] = {}
        self.loads = 0

    def cell(self, index):
        if index not in self.cells:
            cell = NDArray("float32", [32, 32], managed=True)
            numpy.asarray(cell)[:] = index  # E.g. load from disk.
            self.cells[index] = cell
            self.loads += 1
        return self.cells[index]

    def evict(self, index):
        self.cells.pop(index).shm.dispose()


def test_share_cell_cache():
    """
    Two workers process the same cell of a large image, from a cache in the
    service.

    The cache loads the cell into managed memory once, and sends it to each
    worker: both view the very same memory, with no copying. The cache may
    evict the cell while workers still use it; it is freed only once no
    worker uses it anymore.
    """
    cache = CellCache()
    inputs = {"cache": cache}
    with python_service() as worker1, python_service() as worker2:
        # Each worker keeps using the cell after its first task.
        worker1.task("cell = cache.cell(5)\ntask.export(cell=cell)", inputs).wait_for()
        worker2.task("cell = cache.cell(5)\ntask.export(cell=cell)", inputs).wait_for()
        assert cache.loads == 1

        # Both workers view the same memory: one sees what the other writes.
        worker1.task("cell[0, 0] = 42").wait_for()
        assert worker2.task("float(cell[0, 0])").wait_for().result() == 42

        # The cache evicts the cell, but the workers still use it.
        cache.evict(5)
        time.sleep(0.2)
        gc.collect()
        assert len(_memory._regions) == 1

        # Once both workers are done with it, the cell is freed.
        worker1.task("task.export(cell=None)").wait_for()
        worker2.task("task.export(cell=None)").wait_for()
        assert all_freed()


def test_share_output_image():
    """
    A worker segments an image into a label image owned by the service.

    The service sends the worker a managed label image, which the worker
    writes into in place; the service sees the labels, with no copying.
    """
    labels = NDArray("uint16", [8, 8], managed=True)
    with python_service() as worker:
        worker.task(
            "labels[:4] = 1\nlabels[4:] = 2",
            {"labels": labels},
        ).wait_for()
        view = numpy.asarray(labels)
        assert (view[:4] == 1).all() and (view[4:] == 2).all()
    del labels, view
    assert all_freed()


def test_share_relay():
    """
    The service passes an array from one worker on to another.

    The array lives in managed memory, so it is passed on by reference, with
    no copying: the second worker writes into the very array the service
    holds. It stays allocated as long as either of them uses it.
    """
    with python_service() as source, python_service() as consumer:
        data = source.task("numpy.full(5, 3, dtype='int32')").wait_for().result()

        consumer.task("data += 1\ntask.export(kept=data)", {"data": data}).wait_for()
        assert data.tolist() == [4, 4, 4, 4, 4]  # The consumer's write.

        # The service drops the array; the consumer still uses it.
        del data
        time.sleep(0.2)
        gc.collect()
        assert len(_memory._regions) == 1

        # Once the consumer is done with it, it is freed.
        consumer.task("task.export(kept=None)").wait_for()
        assert all_freed()


# -- Unmanaged memory --


def test_unmanaged_buffer():
    """
    The service reuses one buffer across many calls into a worker.

    An NDArray created as usual is unmanaged: shared in place, it lives as
    long as the application wants, here until it disposes of the buffer.
    """
    with python_service() as worker, NDArray("int32", [16]) as buffer:
        for i in range(3):
            worker.task("numpy.asarray(buf)[:] = i", {"buf": buffer, "i": i}).wait_for()
            assert (numpy.asarray(buffer) == i).all()
        name = buffer.shm.name
    assert unlinked(name)


def test_unmanaged_ring_buffer():
    """
    A worker streams frames to the service through a ring buffer it owns.

    The worker writes each frame into the next slot of one block it created,
    and sends the service a view of that slot. Reuse of the slots is a matter
    of timing, and the block lives until the worker frees it.
    """
    setup = (
        "from appose import SharedMemory\n"
        "ring = SharedMemory(create=True, rsize=4 * 16)\n"
        "task.export(ring=ring)\n"
    )
    grab = (
        "from appose import NDArray\n"
        "slot = frame % 4\n"
        "view = NDArray('uint8', [4, 4], ring.view(slot * 16, 16))\n"
        "numpy.asarray(view)[:] = frame  # E.g. copy in a camera frame.\n"
        "view"
    )
    with python_service() as worker:
        worker.task(setup).wait_for()
        for frame in range(6):
            view = worker.task(grab, {"frame": frame}).wait_for().result()
            assert isinstance(view, NDArray)
            assert (numpy.asarray(view) == frame).all()
        name = view.shm.name
        worker.task("ring.unlink()").wait_for()
    assert unlinked(name)
    assert not _memory._regions
