###
# #%L
# Appose: multi-language interprocess plugins with shared memory ndarrays.
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
from multiprocessing.shared_memory import SharedMemory

import numpy
from typing import Any, Dict, Sequence, Tuple

Args = Dict[str, Any]

def _encode(value: Any) -> Any:
    if isinstance(value, numpy.ndarray):


def encode(data: Args) -> str:
    return json.dumps({name: _encode(value) for name, value in data.items()})


def decode(the_json: str) -> Args:
    return json.loads(the_json)


def ndarray(shape: Sequence[int], dtype: "numpy.dtype", shm_name: str = None) -> Tuple[str, "numpy.ndarray"]:
    """
    Create an ndarray in shared memory, without initializing any element values.

    :param shape: int or tuple of ints
        Shape of the new array, e.g., `(2, 3)` or `2`.
    :param dtype: data-type, optional
        The desired data-type for the array, e.g., `numpy.int8`.
    :param shm_name: TODO
    :return: (shm.name, ndarray) pair
    """

    # Allocate shared memory matching size of numpy array.
    size = numpy.prod(shape) * dtype.itemsize
    if shm_name is None:
        shm = SharedMemory(create=True, size=size)
    else:
        shm = SharedMemory(name=shm_name, create=False, size=size)

    # NB: If this Python process closes, the memory will
    # be destroyed even if other processes are using it.
    #
    # https://github.com/python/cpython/issues/82300
    # ^ "resource tracker destroys shared memory segments
    #    when other processes should still have valid access"
    #
    # https://stackoverflow.com/q/64915548
    # ^ this shows how to use the undocumented unregister function
    #   of resource_tracker to prevent Python from destroying shared
    #   memory segments when the creating process shuts down.

    # Construct an ndarray around the shared memory block.
    ndarray: numpy.ndarray = numpy.frombuffer(shm.buf, dtype=dtype).reshape(shape)
    ndarray.data

    # Ugh. No way that I know to attach the shm_name to the numpy.ndarray.
    # Would be better if we could return one object that knows its name.
    # However, barring that, we can have an internal weak map here from
    # ndarray -> SharedMemory  so that one can query the name of the
    # shared memory of an ndarray created using the ndarray function.
    # With this, we can reconstruct ndarrays passed between processes.

    # However, I'm tempted to purge the numpy dependency completely from
    # Appose, in favor of only SharedMemory objects. And it's the responsibility
    # of the calling code to wrap those into whatever structure they need.
    # For Java this could be direct ByteBuffers, for Python this could be
    # ndarrays or really anything that can be wrapped around a memoryview.
    return shm.name, ndarray
