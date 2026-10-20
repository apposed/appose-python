# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
TODO
"""

from __future__ import annotations

import warnings
from math import prod
from multiprocessing import resource_tracker, shared_memory
from typing import TYPE_CHECKING

from .util import message

if TYPE_CHECKING:
    from typing import Self

    import numpy
    import numpy.typing as npt


class SharedMemory(shared_memory.SharedMemory):
    """
    An enhanced version of Python's multiprocessing.shared_memory.SharedMemory
    class which can be used with a `with` statement. When the program flow
    exits the `with` block, this class's `dispose()` method will be invoked,
    which might call `close()` or `unlink()` depending on the value of its
    `unlink_on_dispose` flag.
    """

    def __init__(self, name: str | None = None, create: bool = False, rsize: int = 0):
        """
        Create a new shared memory block, or attach to an existing one.

        Args:
            name: The unique name for the requested shared memory, specified as a
                string. If create is True (i.e. a new shared memory block) and
                no name is given, a novel name will be generated.
            create: Whether a new shared memory block is created (True)
                or an existing one is attached to (False).
            rsize: Requested size in bytes. The true allocated size will be at least
                this much, but may be rounded up to the next block size multiple,
                depending on the running platform.
        """
        super().__init__(name=name, create=create, size=rsize)
        self.rsize: int = rsize
        self._unlink_on_dispose: bool = create
        if message._worker_mode:
            # HACK: Remove this shared memory block from the resource_tracker,
            # which would otherwise want to clean up shared memory blocks
            # after all known references are done using them.
            #
            # There is one resource_tracker per Python process, and they will
            # each try to delete shared memory blocks known to them when they
            # are shutting down, even when other processes still need them.
            #
            # As such, the rule Appose follows is: let the service process
            # always handle cleanup of shared memory blocks, regardless of
            # which process initially allocated it.
            try:
                resource_tracker.unregister(self._name, "shared_memory")
            except ModuleNotFoundError:
                # Unfortunately, on (some?) Windows systems, we see the error:
                #
                # Traceback (most recent call last):
                #   File "...\site-packages\appose\types.py", line 97, in decode
                #     return json.loads(the_json, object_hook=_appose_object_hook)
                #   File "...\lib\json\__init__.py", line 359, in loads
                #     return cls(**kw).decode(s)
                #   File "...\lib\json\decoder.py", line 337, in decode
                #     obj, end = self.raw_decode(s, idx=_w(s, 0).end())
                #   File "...\lib\json\decoder.py", line 353, in raw_decode
                #     obj, end = self.scan_once(s, idx)
                #   File "...\site-packages\appose\types.py", line 177, in _appose_object_hook
                #     return SharedMemory(name=(obj["name"]), size=(obj["size"]))
                #   File "...\site-packages\appose\types.py", line 63, in __init__
                #     resource_tracker.unregister(self._name, "shared_memory")
                #   File "...\lib\multiprocessing\resource_tracker.py", line 159, in unregister
                #     self._send('UNREGISTER', name, rtype)
                #   File "...\lib\multiprocessing\resource_tracker.py", line 162, in _send
                #     self.ensure_running()
                #   File "...\lib\multiprocessing\resource_tracker.py", line 129, in ensure_running
                #     pid = util.spawnv_passfds(exe, args, fds_to_pass)
                #   File "...\lib\multiprocessing\util.py", line 448, in spawnv_passfds
                #     import _posixsubprocess
                # ModuleNotFoundError: No module named '_posixsubprocess'
                #
                # A bug in Python? Regardless: we guard against it here.
                # See also: https://github.com/imglib/imglib2-appose/issues/1
                pass

    def unlink_on_dispose(self, value: bool) -> None:
        """
        Set whether the `unlink()` method should be invoked to destroy
        the shared memory block when the `dispose()` method is called.

        Note: dispose() is the method called when exiting a `with` block.

        By default, shared memory objects constructed with `create=True`
        will behave this way, whereas shared memory objects constructed
        with `create=False` will not. But this method allows to override
        the behavior.
        """
        self._unlink_on_dispose = value

    def dispose(self) -> None:
        if self._unlink_on_dispose:
            self.unlink()
        else:
            self.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.dispose()


class NDArray:
    """
    Data structure for a multi-dimensional array.
    The array contains elements of a data type, arranged in
    a particular shape, and flattened into SharedMemory.
    """

    def __init__(self, dtype: str, shape: list[int], shm: SharedMemory | None = None):
        """
        Create an NDArray.

        Args:
            dtype: The type of the data elements; e.g. int8, uint8, float32, float64.
                NumPy-style short forms (e.g. u2, f4, |u1, =c8) are also accepted,
                and normalized to the standard name (e.g. uint16, float32).
                Explicit byte orders (< or >) are rejected: Appose arrays
                always use the machine's native byte order. To match a NumPy
                array, pass arr.dtype.name, not str(arr.dtype), which keeps a
                non-native byte order; or use copy_of to copy the array.
            shape: The dimensional extents; e.g. a stack of 7 image planes
                with resolution 512x512 would have shape [7, 512, 512].
            shm: The SharedMemory containing the array data, or None to create it.
        """
        self.dtype: str = _normalize_dtype(dtype)
        self.shape: list[int] = shape
        self.shm: SharedMemory = (
            SharedMemory(
                create=True, rsize=prod(shape) * _bytes_per_element(self.dtype)
            )
            if shm is None
            else shm
        )

    def __str__(self):
        return (
            f"NDArray("
            f"dtype='{self.dtype}', "
            f"shape={self.shape}, "
            f"shm='{self.shm.name}' ({self.shm.rsize}))"
        )

    def __array__(
        self, dtype: npt.DTypeLike = None, copy: bool | None = None
    ) -> numpy.ndarray:
        """
        Support numpy.asarray(nda), which wraps the array data as a NumPy
        ndarray without copying it; the NumPy array uses the same SharedMemory.
        Requires the numpy package to be installed.
        """
        try:
            import numpy
        except ModuleNotFoundError:
            raise ImportError("NumPy is not available.")
        arr = numpy.ndarray(
            prod(self.shape), dtype=self.dtype, buffer=self.shm.buf
        ).reshape(self.shape)
        if dtype is None:
            dtype = arr.dtype
        if copy is False and numpy.dtype(dtype) != arr.dtype:
            raise ValueError(
                f"Cannot convert NDArray from {arr.dtype} to {dtype} without copying"
            )
        return arr.astype(dtype, copy=bool(copy))

    def ndarray(self) -> numpy.ndarray:
        """
        Create a NumPy ndarray object for working with the array data.
        No array data is copied; the NumPy array wraps the same SharedMemory.
        Requires the numpy package to be installed.

        Deprecated: use numpy.asarray(nda) instead.
        """
        warnings.warn(
            "NDArray.ndarray() is deprecated; use numpy.asarray(nda) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.__array__()

    @classmethod
    def copy_of(cls, arr: numpy.ndarray) -> NDArray:
        """
        Create an NDArray in new shared memory, holding a copy of the given
        NumPy array.

        The data is copied value by value, so the source array may be in any
        byte order and memory layout (e.g. a big-endian array, or a transposed
        view); the copy is always C-ordered, in native byte order.

        Args:
            arr: The NumPy array to copy.
        """
        nda = cls(arr.dtype.name, list(arr.shape))
        try:
            nda.__array__()[:] = arr
        except BaseException:
            nda.shm.dispose()
            raise
        return nda

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.shm.dispose()


message.register(
    SharedMemory,
    "shm",
    lambda shm: {"name": shm.name, "rsize": shm.rsize},
    lambda m: SharedMemory(name=m["name"], rsize=m["rsize"]),
)
message.register(
    NDArray,
    "ndarray",
    lambda nda: {"dtype": nda.dtype, "shape": nda.shape, "shm": nda.shm},
    lambda m: NDArray(m["dtype"], m["shape"], m["shm"]),
)


# Standard dtype names, with the number of bytes per element of each.
_DTYPE_SIZES = {
    "int8": 1,
    "int16": 2,
    "int32": 4,
    "int64": 8,
    "uint8": 1,
    "uint16": 2,
    "uint32": 4,
    "uint64": 8,
    "float16": 2,
    "float32": 4,
    "float64": 8,
    "complex64": 8,
    "complex128": 16,
    "bool": 1,
}

# NumPy-style short forms of the standard dtype names.
_DTYPE_ALIASES = {
    "i1": "int8",
    "i2": "int16",
    "i4": "int32",
    "i8": "int64",
    "u1": "uint8",
    "u2": "uint16",
    "u4": "uint32",
    "u8": "uint64",
    "f2": "float16",
    "f4": "float32",
    "f8": "float64",
    "c8": "complex64",
    "c16": "complex128",
    "b1": "bool",
    "?": "bool",
}


def _normalize_dtype(dtype: str) -> str:
    """
    Return the standard name of the given dtype; e.g. "<u2" -> "uint16".

    Accepts standard names (e.g. uint16, float32) as well as NumPy-style
    short forms (e.g. u2, f4). A short form may be prefixed with = (native
    byte order) or | (byte order not applicable), which is ignored. Explicit
    byte orders (< or >) are rejected, so that parsing behaves the same on
    every machine; Appose arrays always use the machine's native byte order.

    Only platform-independent types are supported; e.g. longdouble and
    single-character codes like "l" are rejected, since their sizes vary.
    """
    if dtype in _DTYPE_SIZES:
        return dtype
    if dtype.startswith(("<", ">")):
        name = _DTYPE_ALIASES.get(dtype[1:], dtype[1:])
        if name in _DTYPE_SIZES:
            raise ValueError(
                f"Unsupported dtype: {dtype} "
                "(Appose arrays are always in native byte order; "
                f"use '{name}' instead, e.g. via arr.dtype.name, "
                "or copy a NumPy array into shared memory "
                "via NDArray.copy_of(arr))"
            )
    short = dtype[1:] if dtype.startswith(("=", "|")) else dtype
    if short not in _DTYPE_ALIASES:
        raise ValueError(f"Unsupported dtype: {dtype}")
    return _DTYPE_ALIASES[short]


def _bytes_per_element(dtype: str) -> int:
    """
    Return the number of bytes per element for the given dtype.
    """
    return _DTYPE_SIZES[_normalize_dtype(dtype)]
