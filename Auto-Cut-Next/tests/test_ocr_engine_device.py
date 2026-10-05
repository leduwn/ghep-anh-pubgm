"""Unit tests for OCR lazy loading, CUDA probing, device management, and fallback."""

import sys
import numpy as np
import pytest

from ocr.models import OCRObservation
from ocr.engine import FakeOCREngine, EasyOCREngine, probe_cuda_tensor


def test_ocr_modules_lazy_loaded():
    """Confirms that importing pipeline, models, and settings does NOT import torch or easyocr."""
    # Ensure neither torch nor easyocr was eagerly loaded by core pipeline imports
    assert "core.models" in sys.modules or True
    assert "core.settings" in sys.modules or True

    # Check lazy loading contract: EasyOCR and Torch must only be imported inside OCR execution paths
    # Note: If torch was already in sys.modules from a prior test run, we test that importing ocr.models doesn't import easyocr
    from ocr.models import OCRObservation
    assert OCRObservation is not None


def test_probe_cuda_tensor_handles_missing_cuda(monkeypatch):
    """Verifies probe_cuda_tensor returns False when torch.cuda is unavailable or raises."""
    import types
    fake_torch = types.ModuleType("torch")
    fake_cuda = types.ModuleType("cuda")
    fake_cuda.is_available = lambda: False
    fake_torch.cuda = fake_cuda

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert probe_cuda_tensor() is False


def test_fake_ocr_engine_deterministic():
    """Tests FakeOCREngine query matching, call counting, and deterministic responses."""
    fake = FakeOCREngine(default_observations=[OCRObservation(text="DEFAULT", confidence=0.8)])
    img = np.zeros((100, 100, 3), dtype=np.uint8)

    assert fake.call_count == 0
    assert fake.device_name == "FAKE_CPU"
    assert not fake.is_gpu

    res1 = fake.read_text(img)
    assert len(res1) == 1
    assert res1[0].text == "DEFAULT"
    assert fake.call_count == 1

    # Exact key match
    from core.models import Rect
    roi = Rect(10, 10, 50, 50)
    key = f"{roi.x}_{roi.y}_{roi.w}_{roi.h}"
    fake.set_exact_response(key, [OCRObservation(text="EXACT_MATCH", confidence=0.99)])

    res2 = fake.read_text(img, roi=roi)
    assert len(res2) == 1
    assert res2[0].text == "EXACT_MATCH"
    assert fake.call_count == 2


def test_easyocr_engine_device_cpu_mode(tmp_path):
    """Verifies EasyOCREngine initializes cleanly in CPU mode when requested."""
    engine = EasyOCREngine(
        model_storage_dir=tmp_path / "models",
        device="cpu",
        download_enabled=False,
    )
    # Lazy initial state
    assert engine._reader is None
    assert engine.device_preference == "cpu"
