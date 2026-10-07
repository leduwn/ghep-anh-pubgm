"""Robust JSON-native serialization utilities for Auto-Cut-Next."""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False


def to_json_native(value: Any) -> Any:
    """Recursively converts arbitrary data structures to JSON-native types.

    Ensures NumPy scalars, arrays, Paths, Enums, and custom objects are converted
    to standard Python int, float, bool, str, list, dict, and None.
    Preserves numeric semantics (e.g. np.int32(5) -> 5, not "5").
    """
    if value is None:
        return None

    # NumPy types handling
    if _NUMPY_AVAILABLE:
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return [to_json_native(v) for v in value.tolist()]

    # Generic NumPy / duck-typed scalar handling if numpy not imported or subclassed
    if hasattr(value, "dtype") and hasattr(value, "item") and callable(value.item):
        try:
            item_val = value.item()
            if isinstance(item_val, bool):
                return bool(item_val)
            if isinstance(item_val, int):
                return int(item_val)
            if isinstance(item_val, float):
                return float(item_val)
        except Exception:
            pass

    # Python primitive types (check bool before int!)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return value

    # Path objects
    if isinstance(value, Path):
        return str(value)

    # Enum objects
    if isinstance(value, enum.Enum):
        return to_json_native(value.value)

    # Dictionaries
    if isinstance(value, dict):
        return {str(k): to_json_native(v) for k, v in value.items()}

    # Sequences / Sets
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_native(item) for item in value]

    # Objects with explicit to_dict() method
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return to_json_native(value.to_dict())

    # Dataclasses
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return to_json_native(dataclasses.asdict(value))

    return value
