# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

import ctypes
import json

import numpy
import pytest

import appose
from appose.service import TaskStatus
from appose.shm import (
    NDArray,
    SharedMemory,
    SharedMemoryView,
    _bytes_per_element,
    _normalize_dtype,
)
from appose.util import message

ndarray_inspect = """
task.outputs["rsize"] = data.shm.rsize
task.outputs["size"] = data.shm.size
task.outputs["dtype"] = data.dtype
task.outputs["shape"] = data.shape
task.outputs["sum"] = sum(v for v in data.shm.buf)
"""


def test_ndarray():
    env = appose.system()
    with (
        env.python() as service,
        appose.SharedMemory(create=True, rsize=2 * 2 * 20 * 25) as shm,
    ):
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


def test_dtype_standard_names():
    for dtype, size in [
        ("int8", 1),
        ("int16", 2),
        ("int32", 4),
        ("int64", 8),
        ("uint8", 1),
        ("uint16", 2),
        ("uint32", 4),
        ("uint64", 8),
        ("float16", 2),
        ("float32", 4),
        ("float64", 8),
        ("complex64", 8),
        ("complex128", 16),
        ("bool", 1),
    ]:
        assert dtype == _normalize_dtype(dtype)
        assert size == _bytes_per_element(dtype)


def test_dtype_short_forms():
    for short, name in [
        ("i1", "int8"),
        ("i2", "int16"),
        ("i4", "int32"),
        ("i8", "int64"),
        ("u1", "uint8"),
        ("u2", "uint16"),
        ("u4", "uint32"),
        ("u8", "uint64"),
        ("f2", "float16"),
        ("f4", "float32"),
        ("f8", "float64"),
        ("c8", "complex64"),
        ("c16", "complex128"),
        ("b1", "bool"),
        ("?", "bool"),
    ]:
        assert name == _normalize_dtype(short)
        assert name == _normalize_dtype("=" + short)
        assert name == _normalize_dtype("|" + short)


def test_dtype_explicit_byte_order():
    for dtype, name in [
        ("<u2", "uint16"),
        (">u2", "uint16"),
        ("<f4", "float32"),
        (">c16", "complex128"),
        ("<?", "bool"),
        ("<uint16", "uint16"),
        (">float32", "float32"),
    ]:
        with pytest.raises(ValueError, match=f"native byte order; use '{name}'"):
            _normalize_dtype(dtype)


def test_dtype_unsupported():
    for dtype in [
        "",
        "=",
        "==u2",
        "|=u2",
        "=uint16",
        "|uint8",
        "uint",
        "u3",
        "f16",
        "c32",
        "?1",
        "l",
        "g",
        "longdouble",
        "float128",
        "intp",
        "U10",
        "<U10",
        ">i3",
        "datetime64[ns]",
        "object",
        "FLOAT32",
    ]:
        with pytest.raises(ValueError, match="Unsupported dtype"):
            _normalize_dtype(dtype)


def test_ndarray_normalizes_dtype():
    with appose.NDArray("=u2", [3, 5]) as data:
        assert "uint16" == data.dtype
        assert 3 * 5 * 2 == data.shm.rsize


def test_copy_of_big_endian():
    # A big-endian array, as produced by some image readers.
    src = (numpy.arange(3 * 4 * 5).reshape(3, 4, 5) * 1000).astype(">u2")
    with pytest.raises(ValueError, match="use 'uint16'"):
        appose.NDArray(str(src.dtype), list(src.shape))
    with appose.NDArray.copy_of(src) as data:
        assert "uint16" == data.dtype
        assert [3, 4, 5] == data.shape
        assert 3 * 4 * 5 * 2 == data.shm.rsize
        dst = numpy.asarray(data)
        assert dst.dtype.isnative
        assert numpy.array_equal(src, dst)


def test_copy_of_non_contiguous():
    src = numpy.arange(24, dtype="float32").reshape(2, 3, 4).transpose(2, 0, 1)
    with appose.NDArray.copy_of(src) as data:
        assert "float32" == data.dtype
        assert [4, 2, 3] == data.shape
        assert numpy.array_equal(src, numpy.asarray(data))


def test_copy_of_unsupported():
    with pytest.raises(ValueError, match="Unsupported dtype: datetime64"):
        appose.NDArray.copy_of(numpy.zeros(3, dtype="datetime64[ns]"))


def test_asarray_zero_copy():
    with appose.NDArray("float32", [2, 3]) as data:
        arr = numpy.asarray(data)
        assert "float32" == arr.dtype.name
        assert (2, 3) == arr.shape
        arr[1, 2] = 42
        assert 42 == numpy.asarray(data)[1, 2]

        copied = numpy.array(data)
        copied[0, 0] = 7
        assert 0 == numpy.asarray(data)[0, 0]

        converted = numpy.asarray(data, dtype="float64")
        assert "float64" == converted.dtype.name
        assert 42 == converted[1, 2]


def test_ndarray_deprecated():
    with appose.NDArray("uint8", [4]) as data:
        with pytest.warns(DeprecationWarning, match="numpy.asarray"):
            arr = data.ndarray()
        arr[0] = 9
        assert 9 == numpy.asarray(data)[0]


def test_region_round_trip():
    """An unmanaged region of a block encodes as such, and decodes to a view of it."""
    with SharedMemory(create=True, rsize=64) as block:
        block.buf[16:24] = bytes(range(8))
        region = block.view(16, 8)
        encoded = message.encode({"nda": NDArray("uint8", [2, 4], region)})
        shm = json.loads(encoded)["nda"]["shm"]
        assert shm["offset"] == 16 and shm["length"] == 8
        assert "managed" not in shm

        nda = message.decode(encoded)["nda"]
        assert isinstance(nda, NDArray)
        assert isinstance(nda.shm, SharedMemoryView)
        assert numpy.asarray(nda).tolist() == [[0, 1, 2, 3], [4, 5, 6, 7]]

        # Regions of one block share a single mapping.
        other = message.decode(message.encode({"shm": block.view(0, 16)}))["shm"]
        assert isinstance(other, SharedMemoryView)
        base = ctypes.addressof(nda.shm._pin) - nda.shm.offset
        assert ctypes.addressof(other._pin) - other.offset == base
        del nda, other, region


def test_region_bounds():
    with (
        SharedMemory(create=True, rsize=64) as block,
        pytest.raises(ValueError, match="does not fit"),
    ):
        block.view(60, 8)
