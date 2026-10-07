"""Tests for JSON-native serialization boundary and NumPy type normalization."""

import json
from pathlib import Path
import numpy as np
import pytest

from core.constants import Category
from core.models import AccountSession, DetectedAsset, Rect
from core.serialization import to_json_native
from core.cache import DiskCache
from core.session import WorkspaceManager


def test_to_json_native_scalar_types():
    """Confirms NumPy integer, floating, and bool scalars convert to Python int, float, bool."""
    val_int32 = np.int32(42)
    val_int64 = np.int64(999999999)
    val_float32 = np.float32(3.14)
    val_float64 = np.float64(2.71828)
    val_bool_true = np.bool_(True)
    val_bool_false = np.bool_(False)

    res_int32 = to_json_native(val_int32)
    res_int64 = to_json_native(val_int64)
    res_float32 = to_json_native(val_float32)
    res_float64 = to_json_native(val_float64)
    res_bool_true = to_json_native(val_bool_true)
    res_bool_false = to_json_native(val_bool_false)

    assert isinstance(res_int32, int) and type(res_int32) is int
    assert res_int32 == 42
    assert isinstance(res_int64, int) and type(res_int64) is int
    assert res_int64 == 999999999
    assert isinstance(res_float32, float) and type(res_float32) is float
    assert pytest.approx(res_float32, rel=1e-5) == 3.14
    assert isinstance(res_float64, float) and type(res_float64) is float
    assert pytest.approx(res_float64, rel=1e-5) == 2.71828
    assert isinstance(res_bool_true, bool) and type(res_bool_true) is bool
    assert res_bool_true is True
    assert isinstance(res_bool_false, bool) and type(res_bool_false) is bool
    assert res_bool_false is False


def test_to_json_native_numpy_array():
    """Confirms NumPy arrays convert to native Python lists of primitives."""
    arr_1d = np.array([1, 2, 3], dtype=np.int32)
    res_1d = to_json_native(arr_1d)

    assert isinstance(res_1d, list)
    assert res_1d == [1, 2, 3]
    assert all(type(x) is int for x in res_1d)

    arr_2d = np.array([[1.5, 2.5], [3.5, 4.5]], dtype=np.float32)
    res_2d = to_json_native(arr_2d)

    assert isinstance(res_2d, list)
    assert len(res_2d) == 2
    assert all(isinstance(row, list) for row in res_2d)
    assert all(type(x) is float for row in res_2d for x in row)


def test_to_json_native_path_and_complex_nesting():
    """Confirms Path objects and arbitrarily nested collections normalize correctly."""
    data = {
        "path": Path("/tmp/test/path.png"),
        "nested": {
            "tuple": (np.int32(10), np.float32(20.5)),
            "set": {np.int32(1), np.int32(2)},
            "none_val": None,
            "str_val": "hello",
        },
    }
    normalized = to_json_native(data)
    assert normalized["path"] == str(Path("/tmp/test/path.png"))
    assert isinstance(normalized["nested"]["tuple"], list)
    assert type(normalized["nested"]["tuple"][0]) is int
    assert type(normalized["nested"]["tuple"][1]) is float
    assert isinstance(normalized["nested"]["set"], list)
    assert sorted(normalized["nested"]["set"]) == [1, 2]
    # Verify standard json serialization succeeds
    json_str = json.dumps(normalized)
    assert "hello" in json_str


def test_session_and_asset_numpy_scalars_regression():
    """Regression test: NumPy scalars in asset metadata serialize cleanly without stringification."""
    metadata = {
        "lock_stats": {
            "x": np.int32(10),
            "y": np.int64(20),
            "w": np.int32(30),
            "h": np.int64(40),
            "score": np.float32(0.91),
            "matched": np.bool_(True),
        }
    }

    asset = DetectedAsset(
        id="test_asset_np",
        source_id="src_1",
        category=Category.GUN.value,
        crop_rect=Rect(0, 0, 100, 100),
        native_width=100,
        native_height=100,
        detector="test_detector",
        detector_version="1.0.0",
        confidence=0.95,
        metadata=metadata,
    )

    session = AccountSession(account_id="test_np_session")
    session.add_asset(asset)

    # 1. to_dict() must return JSON-native structure
    data = session.to_dict()

    # 2. json.dumps() must NOT raise TypeError
    serialized_str = json.dumps(data)
    assert serialized_str is not None

    # 3. Check types inside data - must be native numeric/bool, NOT strings!
    asset_data = data["assets"][0]
    lock_stats = asset_data["metadata"]["lock_stats"]

    assert type(lock_stats["x"]) is int
    assert lock_stats["x"] == 10
    assert type(lock_stats["y"]) is int
    assert lock_stats["y"] == 20
    assert type(lock_stats["w"]) is int
    assert lock_stats["w"] == 30
    assert type(lock_stats["h"]) is int
    assert lock_stats["h"] == 40
    assert type(lock_stats["score"]) is float
    assert pytest.approx(lock_stats["score"], rel=1e-5) == 0.91
    assert type(lock_stats["matched"]) is bool
    assert lock_stats["matched"] is True

    # Confirm NOT stringified
    assert not isinstance(lock_stats["w"], str)
    assert not isinstance(lock_stats["score"], str)
    assert not isinstance(lock_stats["matched"], str)


def test_disk_cache_numpy_payload_roundtrip(tmp_path):
    """Confirms DiskCache.set() / get() preserves numeric semantics with NumPy scalars."""
    cache = DiskCache(tmp_path / "cache")
    key = "test_key_np"
    payload = {
        "status": "OK",
        "count": np.int32(42),
        "large_id": np.int64(9876543210),
        "confidence": np.float32(0.8765),
        "is_active": np.bool_(True),
        "array_data": np.array([10, 20, 30], dtype=np.int32),
    }

    # Write using set (alias for put)
    cache.set(key, payload)

    # Read back
    loaded = cache.get(key)
    assert loaded is not None
    assert loaded["status"] == "OK"
    assert type(loaded["count"]) is int
    assert loaded["count"] == 42
    assert type(loaded["large_id"]) is int
    assert loaded["large_id"] == 9876543210
    assert type(loaded["confidence"]) is float
    assert pytest.approx(loaded["confidence"], rel=1e-4) == 0.8765
    assert type(loaded["is_active"]) is bool
    assert loaded["is_active"] is True
    assert loaded["array_data"] == [10, 20, 30]
    assert all(type(x) is int for x in loaded["array_data"])


def test_workspace_manager_save_load_session_with_numpy(tmp_path):
    """Confirms WorkspaceManager saves and reloads sessions containing NumPy metadata cleanly."""
    ws = WorkspaceManager(tmp_path / "workspace")
    account_id = "acc_np_roundtrip"
    session = AccountSession(account_id=account_id)

    asset = DetectedAsset(
        id="a_roundtrip",
        source_id="s_1",
        category=Category.ITEM_SET.value,
        crop_rect=Rect(10, 10, 50, 50),
        native_width=50,
        native_height=50,
        detector="generic_grid_detector",
        detector_version="1.0.0",
        metadata={
            "lock_stats": {
                "w": np.int32(16),
                "h": np.int32(20),
                "area": np.int32(320),
                "iou": np.float32(0.75),
            },
            "flags": [np.bool_(True), np.bool_(False)],
        },
        quality_scores={
            "content": np.float32(0.85),
            "lock": np.float32(0.12),
        },
    )
    session.add_asset(asset)

    # Save session
    saved_path = ws.save_session(session)
    assert saved_path.is_file()

    # Load session
    loaded_session = ws.load_session(account_id)
    assert loaded_session.account_id == account_id
    assert len(loaded_session.assets) == 1

    loaded_asset = loaded_session.assets[0]
    l_stats = loaded_asset.metadata["lock_stats"]
    assert type(l_stats["w"]) is int
    assert l_stats["w"] == 16
    assert type(l_stats["area"]) is int
    assert l_stats["area"] == 320
    assert type(l_stats["iou"]) is float
    assert pytest.approx(l_stats["iou"], rel=1e-4) == 0.75
    assert loaded_asset.metadata["flags"] == [True, False]
    assert type(loaded_asset.quality_scores["content"]) is float
    assert pytest.approx(loaded_asset.quality_scores["content"], rel=1e-4) == 0.85
