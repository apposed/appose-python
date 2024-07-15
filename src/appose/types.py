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
from multiprocessing import shared_memory
from typing import Any, Dict

Args = Dict[str, Any]


def encode(data: Args) -> str:
    return json.dumps(data)


def decode(the_json: str) -> Args:
    return json.loads(the_json, object_hook=_appose_object_hook)


class NDArray:
    def __init__(self, shm: shared_memory.SharedMemory, dtype: str, shape):
        self.shm = shm
        self.dtype = dtype
        self.shape = shape

    def __str__(self):
        return (
            f"NDArray("
            f"shm='{self.shm.name}' ({self.shm.size}), "
            f"dtype='{self.dtype}', "
            f"shape={self.shape})"
        )

    def ndarray(self):
        try:
            import math

            import numpy

            num_elements = math.prod(self.shape)
            return numpy.ndarray(
                num_elements, dtype=self.dtype, buffer=self.shm.buf
            ).reshape(self.shape)
        except ModuleNotFoundError:
            raise ImportError("NumPy is not available.")


def _appose_object_hook(obj: Dict):
    type = obj.get("appose_type")
    if type == "shm":
        return shared_memory.SharedMemory(name=(obj["name"]), size=(obj["size"]))
    elif type == "ndarray":
        return NDArray(obj["shm"], obj["dtype"], obj["shape"])
    else:
        return obj
