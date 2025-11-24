###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2025 Appose developers.
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

"""
Utility functions for encoding and decoding messages.
"""

from __future__ import annotations

import json
from typing import Any

from ..shm import NDArray, SharedMemory

Args = dict[str, Any]

# Flag indicating whether this process is running as an Appose worker.
# Set to True by python_worker.Worker.__init__().
_worker_mode = False


def encode(data: Args) -> str:
    return json.dumps(data, cls=_ApposeJSONEncoder, separators=(",", ":"))


def decode(the_json: str) -> Args:
    return json.loads(the_json, object_hook=_appose_object_hook)


class _ApposeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, SharedMemory):
            return {
                "appose_type": "shm",
                "name": obj.name,
                "rsize": obj.rsize,
            }
        if isinstance(obj, NDArray):
            return {
                "appose_type": "ndarray",
                "dtype": obj.dtype,
                "shape": obj.shape,
                "shm": obj.shm,
            }
        return super().default(obj)


def _appose_object_hook(obj: dict):
    atype = obj.get("appose_type")
    if atype == "shm":
        # Attach to existing shared memory block.
        return SharedMemory(name=(obj["name"]), rsize=(obj["rsize"]))
    elif atype == "ndarray":
        return NDArray(obj["dtype"], obj["shape"], obj["shm"])
    else:
        return obj
