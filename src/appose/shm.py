# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
TODO
"""

from __future__ import annotations

import ctypes
import mmap
import os
import threading
import warnings
import weakref
from math import prod
from multiprocessing import resource_tracker, shared_memory
from typing import TYPE_CHECKING, Any, Callable

from .util import message

if TYPE_CHECKING:
    from typing import Self


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
        if create:
            _created.add(self.name)
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

    def view(self, offset: int = 0, length: int | None = None) -> SharedMemoryView:
        """
        Create a view of a region of this shared memory block.

        The view keeps the block's memory mapped for as long as the view, or
        any NumPy array built on it, is alive, even after the block is closed.

        Args:
            offset: The region's starting position within the block, in bytes.
            length: The region's length in bytes, or None to extend it
                to the end of the block's requested size.
        """
        if length is None:
            length = self.rsize - offset
        return SharedMemoryView(self._mmap, self.name, self.rsize, offset, length)

    def unlink(self) -> None:
        _created.discard(self.name)
        if message._worker_mode:
            # NB: This block was unregistered from the resource_tracker upon
            # construction; unregistering it again would make the tracker
            # complain. So we unlink it directly, as the superclass would.
            _unlink_untracked(self._name)
        else:
            super().unlink()

    def close(self) -> None:
        try:
            super().close()
        except BufferError:
            if self._buf is not None:
                # Someone still uses this block's buffer directly.
                raise
            # NB: Views of this block still pin its mapping, which stays
            # open until the last of them is garbage collected.
            self._mmap = None
            super().close()

    def _detach(self) -> mmap.mmap:
        """
        Close this handle, but keep its memory mapping open, for use by views
        of regions of the block. The mapping stays valid, even after the block
        is unlinked, until the last object referencing it is garbage collected.
        """
        # HACK: Reach into the superclass's internals, since
        # close() would refuse to unmap memory still in use.
        mapping = self._mmap
        self._buf.release()
        self._buf = None
        self._mmap = None
        self.close()
        return mapping

    def dispose(self) -> None:
        if self._unlink_on_dispose:
            self.unlink()
        else:
            self.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.dispose()


class SharedMemoryView:
    """
    A region of a shared memory block: length bytes, starting offset bytes
    into the block. Create one with SharedMemory.view(offset, length).

    The view keeps the block's memory mapped for as long as the view, or any
    NumPy array built on it (e.g. via numpy.asarray(view)), is alive.

    A view of a managed region (see NDArray) holds a reference to the region,
    which it gives up once disposed of or garbage collected.
    """

    def __init__(
        self,
        mapping: mmap.mmap,
        name: str,
        rsize: int,
        offset: int,
        length: int,
        managed: bool = False,
    ):
        _check_region(name, rsize, offset, length)
        self.name: str = name
        self.rsize: int = rsize
        self.offset: int = offset
        self.length: int = length
        self.managed: bool = managed
        # NB: Pinning the region keeps the mapping open, and gives us its address.
        self._pin = (ctypes.c_char * length).from_buffer(mapping, offset)
        # For a managed region: gives up this view's reference to it, once.
        self._release: Callable[[], Any] | None = None
        # Whether this region holds a copy made while encoding a message.
        self._copy = False

    @property
    def size(self) -> int:
        return self.length

    @property
    def buf(self) -> memoryview:
        return memoryview(self._pin).cast("B")

    @property
    def __array_interface__(self) -> dict[str, Any]:
        # NB: Exposing the data by address, rather than by buffer, makes the
        # NumPy arrays built on this view reference it (via their bases), and
        # thus keeps the view alive exactly as long as any of those arrays.
        return {
            "version": 3,
            "shape": (self.length,),
            "typestr": "|u1",
            "data": (ctypes.addressof(self._pin), False),
        }

    def dispose(self) -> None:
        """
        For a managed region, give up this view's reference to it now, rather
        than once the view is garbage collected. Otherwise, do nothing: the
        mapping stays open until this view is garbage collected.

        After disposing a view, do not use it, nor any array built on it.
        """
        release, self._release = self._release, None
        if release is not None:
            release()

    def __str__(self):
        return (
            f"SharedMemoryView(name='{self.name}', rsize={self.rsize}, "
            f"offset={self.offset}, length={self.length})"
        )

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

    def __init__(
        self,
        dtype: str,
        shape: list[int],
        shm: SharedMemory | SharedMemoryView | None = None,
        managed: bool = False,
    ):
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
            managed: When creating the shared memory, whether to allocate it
                from the service's managed memory, rather than creating a block
                that the application manages itself. A managed array may be
                sent to any number of processes, which share its data in place;
                it is freed once no process uses it anymore. In a worker, the
                service allocates it, on request.
        """
        self.dtype: str = _normalize_dtype(dtype)
        self.shape: list[int] = shape
        nbytes = prod(shape) * _bytes_per_element(self.dtype)
        self.shm: SharedMemory | SharedMemoryView
        if shm is not None:
            if managed:
                raise ValueError("Only new shared memory can be allocated as managed")
            self.shm = shm
        elif managed:
            from . import memory

            self.shm = memory.allocate(nbytes)
        else:
            self.shm = SharedMemory(create=True, rsize=nbytes)

    def __str__(self):
        return (
            f"NDArray("
            f"dtype='{self.dtype}', "
            f"shape={self.shape}, "
            f"shm='{self.shm.name}' ({self.shm.rsize}))"
        )

    def __array__(self, dtype=None, copy=None):
        """
        Support numpy.asarray(nda), which wraps the array data as a NumPy
        ndarray without copying it; the NumPy array uses the same SharedMemory.
        Requires the numpy package to be installed.
        """
        try:
            import numpy
        except ModuleNotFoundError:
            raise ImportError("NumPy is not available.")
        if isinstance(self.shm, SharedMemoryView):
            nbytes = prod(self.shape) * _bytes_per_element(self.dtype)
            arr = numpy.asarray(self.shm)[:nbytes].view(self.dtype)
        else:
            arr = numpy.ndarray(prod(self.shape), dtype=self.dtype, buffer=self.shm.buf)
        arr = arr.reshape(self.shape)
        if dtype is None:
            dtype = arr.dtype
        if copy is False and numpy.dtype(dtype) != arr.dtype:
            raise ValueError(
                f"Cannot convert NDArray from {arr.dtype} to {dtype} without copying"
            )
        return arr.astype(dtype, copy=bool(copy))

    def ndarray(self):
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
    def copy_of(cls, arr, managed: bool = False) -> NDArray:
        """
        Create an NDArray in new shared memory, holding a copy of the given
        NumPy array.

        The data is copied value by value, so the source array may be in any
        byte order and memory layout (e.g. a big-endian array, or a transposed
        view); the copy is always C-ordered, in native byte order.

        Args:
            arr: The NumPy array to copy.
            managed: Whether to allocate the copy from the service's managed
                memory; see the NDArray constructor.
        """
        nda = cls(arr.dtype.name, list(arr.shape), managed=managed)
        try:
            nda.__array__()[...] = arr
        except BaseException:
            nda.shm.dispose()
            raise
        return nda

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.shm.dispose()


message.register_encoder(
    SharedMemory,
    "shm",
    lambda shm: {"name": shm.name, "rsize": shm.rsize},
)
message.register_encoder(
    SharedMemoryView,
    "shm",
    lambda view: {
        "name": view.name,
        "rsize": view.rsize,
        "offset": view.offset,
        "length": view.length,
    },
)
message.register_encoder(
    NDArray,
    "ndarray",
    lambda nda: {"dtype": nda.dtype, "shape": nda.shape, "shm": nda.shm},
)


def _managed_view_of(arr) -> SharedMemoryView | None:
    """
    Return the view of the managed region the given NumPy array spans
    exactly, if any, so that the array can be sent by reference.
    """
    base = arr
    while getattr(base, "base", None) is not None and not isinstance(
        base, SharedMemoryView
    ):
        base = base.base
    if not isinstance(base, SharedMemoryView) or not base.managed:
        return None
    if (
        not arr.flags.c_contiguous
        or not arr.dtype.isnative
        or arr.nbytes != base.length
    ):
        return None
    if arr.__array_interface__["data"][0] != ctypes.addressof(base._pin):
        return None
    return base


# Names of the shared memory blocks created by this process, not yet unlinked.
_created: set[str] = set()

# Memory mappings of shared memory blocks attached by this process, by name,
# so that all regions of a block share one mapping. An entry lasts as long as
# any view of its block (or any NumPy array built on one) is alive.
_mappings: weakref.WeakValueDictionary[str, mmap.mmap] = weakref.WeakValueDictionary()
_mappings_lock = threading.Lock()


def _check_region(name: str, rsize: int, offset: int, length: int) -> None:
    if offset < 0 or length < 0 or offset + length > max(rsize, 1):
        raise ValueError(
            f"Region [{offset}, {offset + length}) does not fit "
            f"in shared memory block {name} of size {rsize}"
        )


def _attach_view(
    name: str, rsize: int, offset: int, length: int, managed: bool = False
) -> SharedMemoryView:
    """
    Attach to a region of the named shared memory block. All regions of a
    block attached by this process share one mapping of it.
    """
    with _mappings_lock:
        mapping = _mappings.get(name)
        if mapping is None:
            block = SharedMemory(name=name, rsize=rsize)
            if not message._worker_mode and os.name == "posix" and name not in _created:
                # NB: The block's creator unlinks it, not this process.
                resource_tracker.unregister(block._name, "shared_memory")
            mapping = block._detach()
            _mappings[name] = mapping
    return SharedMemoryView(mapping, name, rsize, offset, length, managed)


def _decode_shm(m: dict[str, Any]):
    """
    Decode an unmanaged shared memory reference: a whole block, or a region
    of one. (Managed references are decoded by the memory backend's link.)
    """
    if not any(key in m for key in ("offset", "length")):
        # A plain block reference, as always.
        return SharedMemory(name=m["name"], rsize=m["rsize"])
    name, rsize = m["name"], m["rsize"]
    offset = m.get("offset", 0)
    length = m.get("length", rsize - offset)
    _check_region(name, rsize, offset, length)
    return _attach_view(name, rsize, offset, length)


def _decode_ndarray(m: dict[str, Any]):
    """
    Decode an array. A managed array becomes a NumPy array, if NumPy is
    available; any other array becomes an NDArray, which can be viewed as a
    NumPy array via numpy.asarray(nda).
    """
    shm = m["shm"]
    if isinstance(shm, SharedMemoryView) and shm.managed:
        try:
            import numpy
        except ModuleNotFoundError:
            pass
        else:
            dtype = _normalize_dtype(m["dtype"])
            nbytes = prod(m["shape"]) * _bytes_per_element(dtype)
            return numpy.asarray(shm)[:nbytes].view(dtype).reshape(m["shape"])
    return NDArray(m["dtype"], m["shape"], shm)


def _unlink_untracked(name: str) -> None:
    """
    Unlink the named shared memory block (on POSIX; elsewhere, a block
    lives until its last handle is closed), bypassing the resource tracker.
    """
    if os.name == "posix":
        import _posixshmem

        try:
            _posixshmem.shm_unlink(name)
        except FileNotFoundError:
            pass


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
