"""OCR engine abstractions, lazy EasyOCR reader with GPU probe, and CPU fallback."""

from __future__ import annotations

import gc
import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Optional, Union

import numpy as np

from core.constants import DEFAULT_WORKSPACE_DIR
from core.models import Rect
from .models import OCRObservation

logger = logging.getLogger("auto_cut.ocr.engine")


class OCREngine(ABC):
    """Abstract interface for optical character recognition engines."""

    @abstractmethod
    def read_text(
        self,
        image: np.ndarray,
        roi: Optional[Rect] = None,
        allowlist: Optional[str] = None,
        paragraph: bool = False,
    ) -> list[OCRObservation]:
        """Performs text recognition on an image or specified sub-ROI."""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_gpu(self) -> bool:
        """Indicates whether inference is currently running on GPU."""
        raise NotImplementedError

    @property
    @abstractmethod
    def device_name(self) -> str:
        """Name of the active computing device (e.g. 'CUDA:0', 'CPU')."""
        raise NotImplementedError

    def close(self) -> None:
        """Releases underlying resources, model weights, and device memory."""
        pass


def probe_cuda_tensor() -> bool:
    """Proactively verifies that CUDA is functional via a real tensor operation."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        # Execute real CUDA allocation to catch broken runtimes, DLL mismatches, or OOM
        test_tensor = torch.zeros((1,), device="cuda")
        del test_tensor
        torch.cuda.synchronize()
        return True
    except Exception as exc:
        logger.warning(f"CUDA proactive probe failed: {exc}. Falling back to CPU.")
        return False


class EasyOCREngine(OCREngine):
    """Production EasyOCR engine with lazy loading, proactive CUDA probing, and CPU fallback."""

    def __init__(
        self,
        model_storage_dir: Optional[Union[str, Path]] = None,
        device: str = "auto",  # "auto", "gpu", "cpu"
        languages: Optional[list[str]] = None,
        download_enabled: bool = True,
        on_gpu_fallback: Optional[Callable[[str], None]] = None,
    ):
        storage_base = Path(model_storage_dir) if model_storage_dir else (DEFAULT_WORKSPACE_DIR / "models" / "easyocr")
        self.model_storage_dir = storage_base.resolve()
        self.model_storage_dir.mkdir(parents=True, exist_ok=True)

        self.device_preference = device.lower().strip()
        self.languages = languages or ["vi", "en"]
        self.download_enabled = download_enabled
        self.on_gpu_fallback = on_gpu_fallback

        self._lock = threading.Lock()
        self._reader: Any = None
        self._active_device: str = "uninitialized"
        self._is_gpu: bool = False
        self._failed_gpu: bool = False

    def _init_reader(self) -> None:
        """Lazily imports EasyOCR and initializes the central reader."""
        if self._reader is not None:
            return

        with self._lock:
            if self._reader is not None:
                return

            # Lazy import
            import easyocr

            use_gpu = False
            if self.device_preference in {"auto", "gpu"} and not self._failed_gpu:
                if probe_cuda_tensor():
                    use_gpu = True
                else:
                    logger.info("CUDA not functional; initializing EasyOCR on CPU.")

            try:
                self._reader = easyocr.Reader(
                    self.languages,
                    gpu=use_gpu,
                    model_storage_directory=str(self.model_storage_dir),
                    download_enabled=self.download_enabled,
                    verbose=False,
                )
                self._is_gpu = use_gpu
                self._active_device = "cuda" if use_gpu else "cpu"
                logger.info(f"EasyOCR reader initialized on {self._active_device.upper()} (dir={self.model_storage_dir})")
            except Exception as exc:
                if use_gpu:
                    logger.warning(f"Failed to initialize EasyOCR on GPU: {exc}. Retrying on CPU.")
                    self._failed_gpu = True
                    self._reader = easyocr.Reader(
                        self.languages,
                        gpu=False,
                        model_storage_directory=str(self.model_storage_dir),
                        download_enabled=self.download_enabled,
                        verbose=False,
                    )
                    self._is_gpu = False
                    self._active_device = "cpu"
                    if self.on_gpu_fallback:
                        self.on_gpu_fallback(f"GPU init failed: {exc}")
                else:
                    raise

    def _switch_to_cpu(self, reason: str) -> None:
        """Safely deallocates GPU weights and switches to CPU reader."""
        with self._lock:
            logger.warning(f"Switching EasyOCR to CPU: {reason}")
            self._failed_gpu = True
            self._reader = None
            self._is_gpu = False
            self._active_device = "cpu"

            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

            import easyocr
            self._reader = easyocr.Reader(
                self.languages,
                gpu=False,
                model_storage_directory=str(self.model_storage_dir),
                download_enabled=self.download_enabled,
                verbose=False,
            )
            if self.on_gpu_fallback:
                self.on_gpu_fallback(reason)

    @property
    def is_gpu(self) -> bool:
        if self._reader is None:
            self._init_reader()
        return self._is_gpu

    @property
    def device_name(self) -> str:
        if self._reader is None:
            self._init_reader()
        return self._active_device.upper()

    def read_text(
        self,
        image: np.ndarray,
        roi: Optional[Rect] = None,
        allowlist: Optional[str] = None,
        paragraph: bool = False,
    ) -> list[OCRObservation]:
        """Runs EasyOCR on region, handling GPU exception fallback and single retry."""
        if image is None or image.size == 0:
            return []

        self._init_reader()

        # Prepare sub-crop and offset coordinates
        offset_x, offset_y = 0, 0
        crop = image
        if roi is not None and not roi.is_empty:
            h, w = image.shape[:2]
            clamped = roi.clamp(w, h)
            if clamped.is_empty:
                return []
            crop = image[clamped.y:clamped.bottom, clamped.x:clamped.right]
            offset_x, offset_y = clamped.x, clamped.y

        kwargs: dict[str, Any] = {"paragraph": paragraph}
        if allowlist is not None:
            kwargs["allowlist"] = allowlist

        raw_results = None
        with self._lock:
            try:
                raw_results = self._reader.readtext(crop, **kwargs)
            except Exception as exc:
                if self._is_gpu:
                    logger.warning(f"Runtime GPU OCR failed: {exc}. Retrying on CPU.")
                    self._switch_to_cpu(f"Runtime GPU inference exception: {exc}")
                    # Single retry of the failed region on CPU
                    raw_results = self._reader.readtext(crop, **kwargs)
                else:
                    logger.error(f"CPU OCR failed: {exc}")
                    raise

        if not raw_results:
            return []

        observations: list[OCRObservation] = []
        for item in raw_results:
            # item format: (bbox, text, prob)
            try:
                raw_box = item[0]
                text = str(item[1]).strip()
                conf = float(item[2])
                # Shift box coordinates back to full image space
                shifted_box = [[float(pt[0] + offset_x), float(pt[1] + offset_y)] for pt in raw_box]
                observations.append(OCRObservation(text=text, box=shifted_box, confidence=conf))
            except (IndexError, ValueError) as parse_exc:
                logger.debug(f"Skipping malformed raw OCR observation: {item} ({parse_exc})")

        return observations

    def close(self) -> None:
        with self._lock:
            self._reader = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass


class FakeOCREngine(OCREngine):
    """Deterministic, thread-safe fake OCR engine for offline unit and integration tests."""

    def __init__(self, default_observations: Optional[list[OCRObservation]] = None):
        self._lock = threading.Lock()
        self.default_observations = default_observations or []
        self._responses: dict[str, list[OCRObservation]] = {}
        self._patterns: list[tuple[str, list[OCRObservation]]] = []
        self.call_count: int = 0
        self.last_roi: Optional[Rect] = None

    @property
    def is_gpu(self) -> bool:
        return False

    @property
    def device_name(self) -> str:
        return "FAKE_CPU"

    def set_exact_response(self, key: str, observations: list[OCRObservation]) -> None:
        with self._lock:
            self._responses[key] = observations

    def add_pattern_response(self, pattern: str, observations: list[OCRObservation]) -> None:
        with self._lock:
            self._patterns.append((pattern, observations))

    def read_text(
        self,
        image: np.ndarray,
        roi: Optional[Rect] = None,
        allowlist: Optional[str] = None,
        paragraph: bool = False,
    ) -> list[OCRObservation]:
        with self._lock:
            self.call_count += 1
            self.last_roi = roi

            if image is None or image.size == 0:
                return []

            # Check exact match if key stored
            roi_key = f"{roi.x}_{roi.y}_{roi.w}_{roi.h}" if roi else "full"
            if roi_key in self._responses:
                return [
                    OCRObservation(text=o.text, box=o.box, confidence=o.confidence)
                    for o in self._responses[roi_key]
                ]

            return [
                OCRObservation(text=o.text, box=o.box, confidence=o.confidence)
                for o in self.default_observations
            ]
