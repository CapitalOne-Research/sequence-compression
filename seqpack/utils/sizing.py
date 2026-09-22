from __future__ import annotations

import json
import sys
from decimal import Decimal

import numpy as np


def _convert_keys_to_native(obj):
    """Recursively convert all dictionary keys to native Python types."""
    if isinstance(obj, dict):
        return {
            (k.item() if hasattr(k, 'item') else k): _convert_keys_to_native(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_convert_keys_to_native(item) for item in obj]
    return obj

def _ensure_list(values):
    """Convert string representations of lists or numpy arrays to Python lists."""
    if isinstance(values, str):
        try:
            parsed = json.loads(values)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    if hasattr(values, 'tolist'):
        return values.tolist()
    return values

def get_json_byte_size(data) -> int:
    """Return the UTF-8 byte length of *data* serialised as compact JSON.

    This is the single canonical size-measurement function used across
    both the pandas and Spark encoding paths.  It accepts any
    JSON-serialisable object (dict, list, scalar, etc.).

    Compact means ``separators=(',', ':')`` – no extra spaces or tabs.
    Measures the true UTF-8 byte length, independent of how `convert_to_json`
    (which favours ASCII-safe ``\\uXXXX`` escapes for the actual wire format)
    happens to encode non-ASCII characters -- otherwise a string's measured
    size would be ~2x its real size, skewing which encoding scheme "wins".
    """
    converted = _convert_keys_to_native(data)
    compact = json.dumps(converted, separators=(',', ':'), default=_json_default, ensure_ascii=False)
    return len(compact.encode("utf-8"))

def convert_to_json(data):
    """Convert data to JSON string with compact formatting."""
    return json.dumps(data, separators=(',', ':'), default=_json_default)

def make_json_serializable(obj):
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_json_serializable(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    if hasattr(obj, 'tolist'):
        return make_json_serializable(obj.tolist())
    return obj

def _json_default(obj):
    """JSON serializer fallback for numpy types."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def get_key_sizes(data: dict) -> dict:
    """
    Calculate the size of each key-value pair in a dictionary.

    Args:
        data: The dictionary to measure.

    Returns:
        Dictionary mapping each key to its size in bytes.
    """
    sizes = {}
    for key, value in data.items():
        pair = {key: value}
        sizes[key] = get_json_byte_size(pair)
    return sizes
