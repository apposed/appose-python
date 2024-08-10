###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 Appose developers.
# %%
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# #L%
###

import json
import re
from math import ceil, prod
from multiprocessing import resource_tracker, shared_memory
from typing import Any, Dict, Sequence, Union

Args = Dict[str, Any]


class SharedMemory(shared_memory.SharedMemory):
    """
    An enhanced version of Python's multiprocessing.shared_memory.SharedMemory
    class which can be used with a `with` statement. When the program flow
    exits the `with` block, this class's `dispose()` method will be invoked,
    which might call `close()` or `unlink()` depending on the value of its
    `unlink_on_dispose` flag.
    """

    def __init__(self, name: str = None, create: bool = False, size: int = 0):
        super().__init__(name=name, create=create, size=size)
        self._unlink_on_dispose = create
        if _is_worker:
            # HACK: Remove this shared memory block from the resource_tracker,
            # which wants to clean up shared memory blocks after all known
            # references are done using them.
            #
            # There is one resource_tracker per Python process, and they will
            # each try to delete shared memory blocks known to them when they
            # are shutting down, even when other processes still need them.
            #
            # As such, the rule Appose follows is: let the service process
            # always handle cleanup of shared memory blocks, regardless of
            # which process initially allocated it.
            resource_tracker.unregister(self._name, "shared_memory")

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

    def __enter__(self) -> "SharedMemory":
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.dispose()


def encode(data: Args) -> str:
    return json.dumps(data, cls=_ApposeJSONEncoder, separators=(",", ":"))


def decode(the_json: str) -> Args:
    return json.loads(the_json, object_hook=_appose_object_hook)


class NDArray:
    """
    Data structure for a multi-dimensional array.
    The array contains elements of a data type, arranged in
    a particular shape, and flattened into SharedMemory.
    """

    def __init__(self, dtype: str, shape: Sequence[int], shm: SharedMemory = None):
        """
        Create an NDArray.
        :param dtype: The type of the data elements; e.g. int8, uint8, float32, float64.
        :param shape: The dimensional extents; e.g. a stack of 7 image planes
                      with resolution 512x512 would have shape [7, 512, 512].
        :param shm: The SharedMemory containing the array data, or None to create it.
        """
        self.dtype = dtype
        self.shape = shape
        self.shm = (
            SharedMemory(
                create=True, size=ceil(prod(shape) * _bytes_per_element(dtype))
            )
            if shm is None
            else shm
        )

    def __str__(self):
        return (
            f"NDArray("
            f"dtype='{self.dtype}', "
            f"shape={self.shape}, "
            f"shm='{self.shm.name}' ({self.shm.size}))"
        )

    def ndarray(self):
        """
        Create a NumPy ndarray object for working with the array data.
        No array data is copied; the NumPy array wraps the same SharedMemory.
        Requires the numpy package to be installed.
        """
        try:
            import numpy

            return numpy.ndarray(
                prod(self.shape), dtype=self.dtype, buffer=self.shm.buf
            ).reshape(self.shape)
        except ModuleNotFoundError:
            raise ImportError("NumPy is not available.")

    def __enter__(self) -> "NDArray":
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.shm.dispose()


class _ApposeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, SharedMemory):
            return {
                "appose_type": "shm",
                "name": obj.name,
                "size": obj.size,
            }
        if isinstance(obj, NDArray):
            return {
                "appose_type": "ndarray",
                "dtype": obj.dtype,
                "shape": obj.shape,
                "shm": obj.shm,
            }
        return super().default(obj)


def _appose_object_hook(obj: Dict):
    atype = obj.get("appose_type")
    if atype == "shm":
        # Attach to existing shared memory block.
        return SharedMemory(name=(obj["name"]), size=(obj["size"]))
    elif atype == "ndarray":
        return NDArray(obj["dtype"], obj["shape"], obj["shm"])
    else:
        return obj


def _bytes_per_element(dtype: str) -> Union[int, float]:
    try:
        bits = int(re.sub("[^0-9]", "", dtype))
    except ValueError:
        raise ValueError(f"Invalid dtype: {dtype}")
    return bits / 8


_is_worker = False


def _set_worker(value: bool) -> None:
    global _is_worker
    _is_worker = value
