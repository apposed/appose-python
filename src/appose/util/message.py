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

# Counter for auto-generated proxy variable names.
_proxy_counter = 0

# Reference to the worker instance, needed for auto-exporting.
_worker_instance = None


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

        # If in worker mode and object is not JSON-serializable,
        # auto-export it and return a worker_object reference.
        if _worker_mode:
            global _proxy_counter
            var_name = f"_appose_auto_{_proxy_counter}"
            _proxy_counter += 1

            # Export the object so it persists for future tasks.
            if _worker_instance is not None:
                _worker_instance.exports[var_name] = obj

            return {
                "appose_type": "worker_object",
                "var_name": var_name,
            }

        return super().default(obj)


def _appose_object_hook(obj: dict):
    atype = obj.get("appose_type")
    if atype == "shm":
        # Attach to existing shared memory block.
        return SharedMemory(name=(obj["name"]), rsize=(obj["rsize"]))
    elif atype == "ndarray":
        return NDArray(obj["dtype"], obj["shape"], obj["shm"])
    elif atype == "worker_object":
        # Keep worker_object dicts as-is for now.
        # They will be converted to proxies by proxify_worker_objects().
        return obj
    else:
        return obj


def proxify_worker_objects(data: Any, service: Any) -> Any:
    """
    Recursively convert worker_object dicts to ProxyObject instances.

    This is called on task outputs after JSON deserialization to convert
    any worker_object references into actual proxy objects.

    Args:
        data: The data structure (potentially) containing worker_object dicts.
        service: The Service instance to use for creating proxies.

    Returns:
        The data with worker_object dicts replaced by ProxyObject instances.
    """
    if isinstance(data, dict):
        if data.get("appose_type") == "worker_object":
            # Convert this worker_object dict to a ProxyObject.
            from .proxy import create

            var_name = data["var_name"]
            return create(service, var_name, queue=None)
        else:
            # Recursively process dict values.
            return {k: proxify_worker_objects(v, service) for k, v in data.items()}
    elif isinstance(data, list):
        # Recursively process list elements.
        return [proxify_worker_objects(item, service) for item in data]
    else:
        # Primitive value, return as-is.
        return data
