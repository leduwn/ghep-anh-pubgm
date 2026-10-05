"""Image preprocessing and visual badge presence filtering for OCR."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from core.models import Rect


def clamp_roi(image_shape: tuple[int, ...], roi: Rect) -> Rect:
    """Clamps a bounding box to image boundaries safely."""
    h, w = image_shape[:2]
    return roi.clamp(w, h)


def extract_roi(image: np.ndarray, roi: Rect) -> np.ndarray:
    """Extracts a sub-crop safely, returning an empty array if invalid."""
    if image is None or image.size == 0 or roi.is_empty:
        return np.empty((0, 0, 3), dtype=np.uint8)
    clamped = clamp_roi(image.shape, roi)
    if clamped.is_empty:
        return np.empty((0, 0, 3), dtype=np.uint8)
    return image[clamped.y:clamped.bottom, clamped.x:clamped.right]


def enhance_text_contrast(crop: np.ndarray) -> np.ndarray:
    """Applies CLAHE and mild bilateral filtering to enhance OCR character legibility."""
    if crop is None or crop.size == 0:
        return crop

    if len(crop.shape) == 3 and crop.shape[2] == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop.copy()

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return enhanced


def check_counter_badge_presence(
    image: np.ndarray,
    counter_roi: Optional[Rect] = None,
    min_edges: int = 300,
    min_color_pixels: int = 500,
) -> Tuple[bool, int, float]:
    """Evaluates whether an elimination tracker badge is visually present and equipped.

    Rejects empty lab backgrounds (edge density < 300) and unequipped/gray badges (color variation < 500).

    Returns:
        tuple[bool, int, float]: (is_present, edge_count, color_pixel_count)
    """
    if image is None or image.size == 0:
        return False, 0, 0.0

    if counter_roi is not None:
        roi = extract_roi(image, counter_roi)
    else:
        roi = image

    if roi.size == 0 or roi.shape[0] < 10 or roi.shape[1] < 10:
        return False, 0, 0.0

    # Ensure 3-channel BGR image
    if len(roi.shape) == 2:
        gray = roi
        roi_bgr = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
    else:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_bgr = roi

    # 1. Edge density check (empty lab backgrounds have virtually zero high-frequency edges)
    edges = cv2.Canny(gray, 40, 120)
    edge_count = int(np.count_nonzero(edges))
    if edge_count < min_edges:
        return False, edge_count, 0.0

    # 2. Color saturation and value check: reject gray, unequipped, or locked badge slots
    diff_rgb = np.max(roi_bgr, axis=2).astype(np.int32) - np.min(roi_bgr, axis=2).astype(np.int32)
    v = np.max(roi_bgr, axis=2)
    high_color_mask = (diff_rgb > 35) & (v > 50)
    color_pixel_count = int(np.count_nonzero(high_color_mask))

    if color_pixel_count < min_color_pixels:
        return False, edge_count, float(color_pixel_count)

    return True, edge_count, float(color_pixel_count)
