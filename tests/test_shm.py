# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

from importlib.util import find_spec

import pytest

import appose
from appose.service import TaskStatus


def _has_module(name):
    return find_spec(name) is not None

ndarray_inspect = """
task.outputs["rsize"] = data.shm.rsize
task.outputs["size"] = data.shm.size
task.outputs["dtype"] = data.dtype
task.outputs["shape"] = data.shape
task.outputs["sum"] = sum(v for v in data.shm.buf)
"""

ndarray_dims_inspect = """
task.outputs["dtype"] = data.dtype
task.outputs["shape"] = data.shape
task.outputs["dims"] = data.dims
"""


def test_ndarray():
    env = appose.system()
    with env.python() as service:
        with appose.SharedMemory(create=True, rsize=2 * 2 * 20 * 25) as shm:
            # Construct the data.
            shm.buf[0] = 123
            shm.buf[456] = 78
            shm.buf[1999] = 210
            data = appose.NDArray("uint16", [2, 20, 25], shm)

            # Run the task.
            task = service.task(ndarray_inspect, {"data": data})
            task.wait_for()

            # Validate the execution result.
            assert TaskStatus.COMPLETE == task.status
            # The requested size is 2*20*25*2=2000, but actual allocated
            # shm size varies by platform; e.g. on macOS it is 16384.
            assert 2 * 20 * 25 * 2 == task.outputs["rsize"]
            assert task.outputs["size"] >= task.outputs["rsize"]
            assert "uint16" == task.outputs["dtype"]
            assert [2, 20, 25] == task.outputs["shape"]
            assert 123 + 78 + 210 == task.outputs["sum"]


def test_ndarray_dims():
    env = appose.system()
    with env.python() as service:
        with appose.SharedMemory(create=True, rsize=2 * 20 * 25) as shm:
            data = appose.NDArray("uint8", [2, 20, 25], shm, dims=["z", "y", "x"])

            task = service.task(ndarray_dims_inspect, {"data": data})
            task.wait_for()

            assert TaskStatus.COMPLETE == task.status
            assert "uint8" == task.outputs["dtype"]
            assert [2, 20, 25] == task.outputs["shape"]
            assert ["z", "y", "x"] == task.outputs["dims"]


def test_ndarray_dims_none():
    """Verify dims is None when not provided (backward compat)."""
    env = appose.system()
    with env.python() as service:
        with appose.SharedMemory(create=True, rsize=2 * 20 * 25) as shm:
            data = appose.NDArray("uint8", [2, 20, 25], shm)

            task = service.task(ndarray_dims_inspect, {"data": data})
            task.wait_for()

            assert TaskStatus.COMPLETE == task.status
            assert task.outputs["dims"] is None


def test_ndarray_dims_length_mismatch():
    with pytest.raises(ValueError, match="dims length"):
        appose.NDArray("uint8", [2, 20, 25], dims=["y", "x"])


@pytest.mark.skipif(
    not _has_module("numpy") or not _has_module("xarray"),
    reason="numpy and xarray required",
)
def test_ndarray_xarray():
    with appose.NDArray("float32", [3, 4], dims=["y", "x"]) as nda:
        arr = nda.ndarray()
        arr[:] = 0
        arr[1, 2] = 42.0

        xa = nda.xarray()
        assert xa.dims == ("y", "x")
        assert xa.shape == (3, 4)
        assert float(xa.sel(y=1, x=2)) == 42.0


@pytest.mark.skipif(
    not _has_module("numpy") or not _has_module("xarray"),
    reason="numpy and xarray required",
)
def test_ndarray_xarray_no_dims():
    """xarray works without dims (uses xarray's default dim names)."""
    with appose.NDArray("float32", [3, 4]) as nda:
        nda.ndarray()[:] = 0
        xa = nda.xarray()
        assert xa.shape == (3, 4)
        assert xa.dims == ("dim_0", "dim_1")
