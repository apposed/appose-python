# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions for encoding and decoding messages.
"""

from __future__ import annotations

import json
from typing import Any, Callable

Args = dict[str, Any]

_encoders: dict[type, tuple[str, Any]] = {}
_decoders: dict[str, Any] = {}


def register(obj_type: type, appose_type: str, encoder, decoder) -> None:
    """
    Register encoder and decoder functions for a custom Appose type.

    When encoding, if an object is an instance of ``obj_type``, ``encoder``
    is called with the object and its return value is wrapped as
    ``{"appose_type": appose_type, "data": <encoded>}``.

    When decoding, if a JSON object has the given ``appose_type``, ``decoder``
    is called with the ``"data"`` field value and should return the
    reconstructed Python object.

    :param obj_type: The Python type to encode.
    :param appose_type: The ``appose_type`` string used on the wire.
    :param encoder: Callable ``(obj) -> JSON-compatible value``.
    :param decoder: Callable ``(data) -> obj``.
    """
    _encoders[obj_type] = (appose_type, encoder)
    _decoders[appose_type] = decoder


# Flag indicating whether this process is running as an Appose worker.
# Set to True by python_worker.Worker.__init__().
_worker_mode = False

# Counter for auto-generated proxy variable names.
_proxy_counter = 0

# Reference to the worker instance, needed for auto-exporting.
_worker_instance = None


def encode(data: Args, exporter: Callable[[Any], Args] | None = None) -> str:
    """
    Encode the given data as a single line of JSON.

    Args:
        data: The data to encode.
        exporter: Optional function to call for objects that are not
            JSON-serializable. It must return a JSON-serializable
            reference to the object (e.g. a service_object dict).
    """
    return json.dumps(
        data, cls=_ApposeJSONEncoder, separators=(",", ":"), exporter=exporter
    )


def decode(the_json: str) -> Args:
    return json.loads(the_json, object_hook=_appose_object_hook)


class _ApposeJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, exporter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._exporter = exporter

    def default(self, obj):
        for obj_type, (appose_type, encoder) in _encoders.items():
            if isinstance(obj, obj_type):
                return {"appose_type": appose_type, **encoder(obj)}

        # A proxy to a service object travels back as a reference to it,
        # rather than being wrapped in another layer of proxying.
        from .proxy import ServiceProxy

        if isinstance(obj, ServiceProxy):
            return {"appose_type": "service_object", "var_name": obj._var}

        if self._exporter is not None:
            return self._exporter(obj)

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
    if atype == "worker_object":
        # Keep worker_object dicts as-is for now.
        # They will be converted to proxies by proxify_worker_objects().
        return obj
    if atype == "service_object":
        if _worker_mode and _worker_instance is not None:
            # Worker side: wrap the reference in a proxy that forwards
            # attribute accesses and calls back to the service.
            from .proxy import ServiceProxy

            return ServiceProxy(_worker_instance, obj["var_name"])
        # Service side: keep service_object dicts as-is for now.
        # They will be resolved by proxify_worker_objects().
        return obj
    if atype in _decoders:
        return _decoders[atype](obj)
    return obj


def proxify_worker_objects(data: Any, service: Any) -> Any:
    """
    Recursively convert worker_object dicts to ProxyObject instances,
    and service_object dicts back to the service objects they reference.

    This is called on task outputs and on worker calls after JSON
    deserialization to convert any worker_object references into actual
    proxy objects.

    Args:
        data: The data structure (potentially) containing worker_object
            and/or service_object dicts.
        service: The Service instance to use for creating proxies.

    Returns:
        The data with worker_object dicts replaced by ProxyObject instances,
        and service_object dicts replaced by the original service objects.
    """
    if isinstance(data, dict):
        if data.get("appose_type") == "worker_object":
            # Convert this worker_object dict to a ProxyObject.
            from .proxy import create

            var_name = data["var_name"]
            return create(service, var_name, queue=None)
        elif data.get("appose_type") == "service_object":
            # Resolve this service_object dict to the object it references.
            return service._exports[data["var_name"]]
        else:
            # Recursively process dict values.
            return {k: proxify_worker_objects(v, service) for k, v in data.items()}
    elif isinstance(data, list):
        # Recursively process list elements.
        return [proxify_worker_objects(item, service) for item in data]
    else:
        # Primitive value, return as-is.
        return data
