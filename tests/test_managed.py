# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for managed shared memory: the service's slabs of slots, and the
reference counts by which it frees them; and for NumPy arrays and shared
memory regions sent between processes.
"""

from __future__ import annotations

import gc
import json
import time

import numpy
import pytest

import appose
from appose import TaskException, memory
from appose.shm import NDArray, SharedMemoryView
from appose.util import message
from tests.test_base import maybe_debug
from tests.test_base import shm_unlinked as unlinked

# This process's memory backend (the builtin one, in a service).
_memory = memory.backend()


class NullPeer(memory.Peer):
    """A peer for tests of a memory link without a worker process."""

    def export(self, name, obj):
        pass


class BlockNames:
    """Debug listener collecting the names of managed blocks on the wire."""

    def __init__(self):
        self.names: set[str] = set()

    def __call__(self, line: str) -> None:
        start = line.find("{")
        if start < 0:
            return
        try:
            data = json.loads(line[start:])
        except ValueError:
            return
        self._collect(data)

    def _collect(self, data) -> None:
        if isinstance(data, dict):
            if data.get("appose_type") == "shm" and data.get("managed"):
                self.names.add(data["name"])
            for v in data.values():
                self._collect(v)
        elif isinstance(data, list):
            for v in data:
                self._collect(v)


def eventually(condition, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        gc.collect()
        time.sleep(0.02)
    return True


def assert_all_freed(names: BlockNames) -> None:
    """Assert that no managed region remains, and its blocks are unlinked."""
    assert names.names, "no managed regions were sent"
    assert eventually(lambda: not _memory._regions), _memory._regions
    for name in names.names:
        assert eventually(lambda name=name: unlinked(name)), name


def numpy_service():
    service = appose.system().python().init("import numpy")
    maybe_debug(service)
    names = BlockNames()
    service.debug(names)
    return service, names


def test_numpy_input_output():
    service, names = numpy_service()
    with service:
        arr = numpy.arange(24, dtype=numpy.float32).reshape(2, 3, 4)
        task = service.task(
            """
task.outputs["kind"] = type(arr).__name__
task.outputs["doubled"] = arr * 2
task.outputs["nested"] = {"list": [arr[0], arr[1]]}
""",
            {"arr": arr},
        ).wait_for()

        assert task.outputs["kind"] == "ndarray"
        doubled = task.outputs["doubled"]
        assert isinstance(doubled, numpy.ndarray)
        assert doubled.dtype == numpy.float32
        numpy.testing.assert_array_equal(doubled, arr * 2)
        first, second = task.outputs["nested"]["list"]
        numpy.testing.assert_array_equal(first, arr[0])
        numpy.testing.assert_array_equal(second, arr[1])

        # The arrays received are copies of the originals, so writes stay local.
        doubled[:] = 0
        assert arr.sum() > 0

        del task, doubled, first, second
        assert_all_freed(names)


def test_numpy_edge_cases():
    service, _ = numpy_service()
    with service:
        arrays = {
            "empty": numpy.zeros((0, 3), dtype=numpy.uint8),
            "scalar": numpy.array(7, dtype=numpy.int16),
            "big_endian": numpy.arange(6).astype(">u2"),
            "transposed": numpy.arange(6, dtype=numpy.int64).reshape(2, 3).T,
            "bool": numpy.array([True, False, True]),
        }
        task = service.task(
            "{k: v for k, v in inputs.items()}",
            {"inputs": arrays},
        ).wait_for()
        for key, expected in arrays.items():
            actual = task.outputs[key]
            assert isinstance(actual, numpy.ndarray), key
            assert actual.shape == expected.shape, key
            assert actual.dtype.name == expected.dtype.name, key
            assert actual.dtype.isnative, key
            numpy.testing.assert_array_equal(actual, expected)


def test_numpy_scalars():
    service, _ = numpy_service()
    with service:
        task = service.task(
            "type(x).__name__, numpy.float32(2.5), numpy.int64(3)",
            {"x": numpy.int32(42)},
        ).wait_for()
        assert task.result() == ["int", 2.5, 3]


def test_numpy_unsupported_dtype():
    service, _ = numpy_service()
    with service:
        with pytest.raises(ValueError, match="Unsupported dtype"):
            service.task("x", {"x": numpy.array(["a", "b"])}).start()
        with pytest.raises(TaskException, match="Unsupported dtype"):
            service.task("numpy.array([1, None])").wait_for()


def test_held_while_in_use():
    """A region stays allocated while any process uses any array built on it."""
    service, names = numpy_service()
    with service:
        service.task(
            "task.export(kept=arr[1:, ::2].T)",
            {"arr": numpy.arange(12, dtype=numpy.int32).reshape(3, 4)},
        ).wait_for()

        # The worker keeps a view of the array, so the region stays allocated.
        time.sleep(0.2)
        gc.collect()
        assert len(_memory._regions) == 1
        kept = service.task("kept.tolist()").wait_for().result()
        assert kept == [[4, 8], [6, 10]]

        service.task("task.export(kept=None)").wait_for()
        assert_all_freed(names)


def test_sent_by_reference():
    """An array spanning a managed region is sent by reference; others are copied."""
    data = NDArray("int16", [4, 4], managed=True)
    whole = numpy.asarray(data)
    managed: list = []
    link = _memory.link(NullPeer())
    sent = json.loads(
        message.encode({"x": whole, "y": whole[1:]}, link=link, managed=managed)
    )
    assert sent["x"]["shm"]["name"] == data.shm.name
    assert sent["y"]["shm"]["name"] != data.shm.name
    assert len(managed) == 2
    for view in managed:
        view.dispose()
    data.shm.dispose()
    del data, whole, managed, view
    assert eventually(lambda: not _memory._regions)


def test_unmanaged_ndarray_shared():
    """An NDArray created by the application is shared in place, unmanaged."""
    service, _ = numpy_service()
    with service, NDArray("int32", [2, 3]) as nda:
        view = numpy.asarray(nda)
        view[:] = 1
        task = service.task(
            "numpy.asarray(x)[:] += 1\ntype(x).__name__",
            {"x": nda},
        ).wait_for()
        assert task.result() == "NDArray"
        numpy.testing.assert_array_equal(view, numpy.full((2, 3), 2))
        assert not _memory._regions


def test_managed_ndarray_from_service_object():
    """A service object can return a managed array it filled, with no copying."""
    service, names = numpy_service()
    with service:

        class Source:
            def load(self, index):
                nda = NDArray("uint16", [4, 4], managed=True)
                numpy.asarray(nda)[:] = index
                return nda

        task = service.task(
            "[(type(c).__name__, int(c.sum())) for c in map(source.load, range(3))]",
            {"source": Source()},
        ).wait_for()
        assert task.result() == [["ndarray", 0], ["ndarray", 16], ["ndarray", 32]]
        assert_all_freed(names)


def test_worker_allocates_via_service():
    """A worker's managed array is allocated by the service, on request."""
    service, names = numpy_service()
    with service:
        task = service.task(
            "from appose import NDArray\n"
            "nda = NDArray('int32', [3], managed=True)\n"
            "numpy.asarray(nda)[:] = 7\n"
            "nda.shm.name"
        ).wait_for()
        assert task.result() in names.names
        assert_all_freed(names)


def test_numpy_service_proxy():
    """NumPy arrays travel both ways when a worker calls a service object."""
    service, names = numpy_service()
    with service:

        class Scaler:
            def scale(self, arr, factor):
                assert isinstance(arr, numpy.ndarray)
                return arr * factor

        task = service.task(
            "scaler.scale(numpy.arange(4), 3).tolist()", {"scaler": Scaler()}
        ).wait_for()
        assert task.result() == [0, 3, 6, 9]
        assert_all_freed(names)


def test_numpy_without_managed_support():
    """Without the service's managed memory, a worker proxies NumPy arrays."""
    service, _ = numpy_service()
    with service:
        task = service.task(
            "from appose.util import message\n"
            "message._worker_instance._memory_link = None\n"
            "numpy.arange(3)"
        ).wait_for()
        assert type(task.result()).__name__ == "ProxyObject"


def test_slabs():
    """Slots of one size share slabs, which double in size, and retire once empty."""
    views = [_memory.allocate(1000) for _ in range(7)]
    blocks = {v.name for v in views}
    assert len(blocks) == 3  # Slabs of 1, 2 and 4 slots.
    assert all(v.offset % _memory.ALIGN == 0 for v in views)
    for view in views:
        view.dispose()
    del views, view
    assert eventually(lambda: not _memory._regions)
    assert eventually(lambda: all(unlinked(name) for name in blocks))


def test_output_after_close():
    """Outputs of a task finishing after the service is closed still arrive."""
    service, names = numpy_service()
    with service:
        task = service.task("import time\ntime.sleep(0.5)\nnumpy.arange(5) * 3").start()
    service.wait_for()
    result = task.result()
    assert result.tolist() == [0, 3, 6, 9, 12]

    # The service holds the result's region, even with the worker gone.
    assert len(_memory._regions) == 1
    del task, result
    assert_all_freed(names)


def test_worker_crash():
    """If the worker dies, the service drops its references."""
    service, names = numpy_service()
    task = service.task(
        "task.export(kept=arr)\nimport time\ntime.sleep(30)",
        {"arr": numpy.ones(4)},
    )
    task.start()
    time.sleep(0.5)
    gc.collect()
    assert len(_memory._regions) == 1
    service.kill()
    service.wait_for()
    del task
    assert_all_freed(names)


def test_encode_failure_frees_copies():
    """Copies of NumPy arrays made for a message are freed if encoding fails."""
    managed: list = []
    with pytest.raises(ValueError, match="Unsupported dtype"):
        message.encode(
            {"good": numpy.arange(3), "bad": numpy.array(["x"])},
            link=_memory.link(NullPeer()),
            managed=managed,
        )
    assert len(managed) == 1
    name = managed[0].name
    del managed
    assert eventually(lambda: not _memory._regions)
    assert eventually(lambda: unlinked(name))


def test_managed_ndarray_dispose():
    """A managed NDArray never sent is freed once disposed of."""
    with NDArray("float32", [8], managed=True) as nda:
        assert isinstance(nda.shm, SharedMemoryView)
        assert nda.shm.managed
        numpy.asarray(nda)[:] = 1
        name = nda.shm.name
    assert eventually(lambda: not _memory._regions)
    assert eventually(lambda: unlinked(name))


def test_disposed_region_not_sent():
    nda = NDArray("int8", [4], managed=True)
    nda.shm.dispose()
    with pytest.raises(ValueError, match="already disposed"):
        message.encode({"x": nda}, link=_memory.link(NullPeer()), managed=[])


def test_unknown_managed_region():
    """The service rejects references to managed regions it does not have."""
    encoded = json.dumps(
        {
            "shm": {
                "appose_type": "shm",
                "name": "psm_bogus",
                "rsize": 64,
                "offset": 0,
                "length": 8,
                "managed": True,
            }
        }
    )
    with pytest.raises(ValueError, match="No such managed shared memory region"):
        message.decode(encoded, _memory.link(NullPeer()))


class TokenLink(memory.MemoryLink):
    """A toy memory link, which refers to views by tokens of its own."""

    def __init__(self):
        self.views: dict[str, SharedMemoryView] = {}
        self.sent_views: list = []

    def describe(self, view):
        token = f"token-{len(self.views)}"
        self.views[token] = view
        return {"token": token}

    def sent(self, views):
        self.sent_views.extend(views)

    def resolve(self, ref):
        return self.views[ref["token"]]


def test_link_routes_managed_references():
    """Managed references are described and resolved by the memory link alone."""
    link = TokenLink()
    data = NDArray("uint8", [4], managed=True)
    numpy.asarray(data)[:] = 9
    managed: list = []
    encoded = message.encode({"x": data}, link=link, managed=managed)
    shm = json.loads(encoded)["x"]["shm"]
    assert shm == {"appose_type": "shm", "token": "token-0", "managed": True}
    assert managed == [data.shm]

    decoded = message.decode(encoded, link)["x"]
    assert numpy.asarray(decoded).tolist() == [9, 9, 9, 9]

    # Without a link, managed memory cannot be sent or received.
    with pytest.raises(ValueError, match="no managed memory"):
        message.encode({"x": data})
    with pytest.raises(ValueError, match="none on this connection"):
        message.decode(encoded)
    data.shm.dispose()
