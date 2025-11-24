# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

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
