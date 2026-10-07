#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic script for GunDetector calibration against real PUBG Gun Lab screenshots.

READ-ONLY on input directory. Never modifies legacy directories.
Outputs debug summaries and visual overlays to Auto-Cut-Next/workspace/gun_debug/.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

# Ensure Auto-Cut-Next is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
NEXT_ROOT = SCRIPT_DIR.parent
REPO_ROOT = NEXT_ROOT.parent

if str(NEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXT_ROOT))

from core.constants import Category
from core.ingest import read_image_cv2
from core.models import Rect
from core.serialization import to_json_native
from detectors import ClassificationContext, ScreenClassifier
from detectors.detection_context import DetectionContext
from detectors.gun_detector import GunDetector
from ocr.gun_ocr import resolve_gun_rois


def find_supported_images(input_dir: Path) -> list[Path]:
    """Discovers all supported image formats in input_dir."""
    extensions = {".png", ".jpg", ".jpeg"}
    images: list[Path] = []
    for f in input_dir.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            images.append(f)
    return sorted(images, key=lambda p: p.name)


def inspect_gun_screen(
    image_path: Path,
    out_dir: Path,
    classifier: ScreenClassifier,
    gun_detector: GunDetector,
) -> dict[str, Any]:
    """Runs detailed multi-signal inspection on a single screenshot."""
    img_bgr = read_image_cv2(image_path)
    if img_bgr is None:
        return {"filename": image_path.name, "error": "Failed to read image"}

    orig_h, orig_w = img_bgr.shape[:2]
    context = DetectionContext(img_bgr, source_id=image_path.stem)
    cl_ctx = ClassificationContext(img_bgr)
    cl_res = classifier.classify(cl_ctx)

    info: dict[str, Any] = {
        "filename": image_path.name,
        "width": orig_w,
        "height": orig_h,
        "classified_category": cl_res.category,
        "classifier_confidence": round(cl_res.confidence, 4),
        "is_gun": cl_res.category == Category.GUN.value,
    }

    if cl_res.category != Category.GUN.value:
        return info

    # 1. Run standard current GunDetector
    det_res = gun_detector.detect(context, classification=cl_res)
    info["current_detector"] = {
        "detected": det_res.detected,
        "confidence": det_res.confidence,
        "reasons": det_res.reasons,
        "fallback_recommended": det_res.fallback_recommended,
        "candidates_count": len(det_res.candidates),
    }

    # 2. Inspect raw contours in scan space (current detector space)
    scan_w = context.scan_w
    scan_h = context.scan_h
    right_ratio = 0.52
    x_min = int(round(scan_w * right_ratio))
    y_max = int(round(scan_h * 0.80))
    right_roi_scan = context.scan_bgr[:y_max, x_min:]

    hsv_scan = cv2.cvtColor(right_roi_scan, cv2.COLOR_BGR2HSV)
    lower_scan = np.array(gun_detector.ORANGE_LOWER, dtype=np.uint8)
    upper_scan = np.array(gun_detector.ORANGE_UPPER, dtype=np.uint8)
    mask_scan = cv2.inRange(hsv_scan, lower_scan, upper_scan)
    kernel_3x3 = np.ones((3, 3), np.uint8)
    mask_scan_morphed = cv2.morphologyEx(mask_scan, cv2.MORPH_CLOSE, kernel_3x3)
    contours_scan, _ = cv2.findContours(mask_scan_morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_card_w = int(round(scan_w * 0.15))
    min_card_h = int(round(scan_h * 0.12))
    max_card_w = int(round(scan_w * 0.45))
    max_card_h = int(round(scan_h * 0.45))
    min_area = min_card_w * min_card_h

    scan_contours_log: list[dict[str, Any]] = []
    for cnt in contours_scan:
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        area = rw * rh
        aspect = float(rw) / float(max(1, rh))
        card_mask_crop = mask_scan_morphed[ry:ry + rh, rx:rx + rw]
        orange_ratio = float(np.count_nonzero(card_mask_crop)) / float(max(1, area))

        # Check why passed/rejected
        rejections: list[str] = []
        if area < min_area:
            rejections.append(f"area ({area}) < min_area ({min_area})")
        if not (min_card_w <= rw <= max_card_w and min_card_h <= rh <= max_card_h):
            rejections.append(f"size ({rw}x{rh}) outside bounds [{min_card_w}..{max_card_w}, {min_card_h}..{max_card_h}]")
        if not (1.45 <= aspect <= 2.65):
            rejections.append(f"aspect ({aspect:.2f}) not in [1.45, 2.65]")
        if orange_ratio > 0.50:
            rejections.append(f"orange_ratio ({orange_ratio:.2f}) > 0.50")

        scan_contours_log.append({
            "bbox": [rx, ry, rw, rh],
            "area": area,
            "aspect": round(aspect, 3),
            "orange_ratio": round(orange_ratio, 3),
            "rejections": rejections,
            "passed_current": len(rejections) == 0,
        })

    info["scan_contours_found"] = len(contours_scan)
    info["scan_contours_log"] = scan_contours_log

    # 3. Inspect legacy catsung.py logic on original resolution
    right_portion_orig = img_bgr[:, int(round(orig_w * 0.60)):]
    hsv_orig = cv2.cvtColor(right_portion_orig, cv2.COLOR_BGR2HSV)
    catsung_lower = np.array([5, 120, 120], dtype=np.uint8)
    catsung_upper = np.array([30, 255, 255], dtype=np.uint8)
    mask_orig = cv2.inRange(hsv_orig, catsung_lower, catsung_upper)
    mask_orig_morphed = cv2.morphologyEx(mask_orig, cv2.MORPH_CLOSE, kernel_3x3)
    contours_orig, _ = cv2.findContours(mask_orig_morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    catsung_contours_log: list[dict[str, Any]] = []
    catsung_min_area = 20_000
    best_catsung_rect = None
    best_catsung_area = 0

    for cnt in contours_orig:
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        area = rw * rh
        aspect = float(rw) / float(max(1, rh))
        rejections = []
        if area < catsung_min_area:
            rejections.append(f"area ({area}) < {catsung_min_area}")
        if not (1.6 <= aspect <= 2.4):
            rejections.append(f"aspect ({aspect:.2f}) not in [1.6, 2.4]")

        if len(rejections) == 0 and area > best_catsung_area:
            best_catsung_area = area
            best_catsung_rect = (rx, ry, rw, rh)

        catsung_contours_log.append({
            "bbox": [rx, ry, rw, rh],
            "area": area,
            "aspect": round(aspect, 3),
            "rejections": rejections,
            "passed_catsung": len(rejections) == 0,
        })

    info["catsung_contours_found"] = len(contours_orig)
    info["catsung_best_rect"] = best_catsung_rect
    info["catsung_contours_log"] = catsung_contours_log

    # 4. Multi-signal HSV range analysis on original resolution (test broader thresholds)
    # Test Saturation/Value lower bound variation: S=80, V=80 vs S=120, V=120
    test_hsv_ranges = [
        ("hsv_5_80_80", (5, 80, 80), (32, 255, 255)),
        ("hsv_5_100_100", (5, 100, 100), (32, 255, 255)),
        ("hsv_5_120_120", (5, 120, 120), (30, 255, 255)),
    ]
    hsv_tests_summary: dict[str, Any] = {}
    for name, low, up in test_hsv_ranges:
        t_mask = cv2.inRange(hsv_orig, np.array(low, dtype=np.uint8), np.array(up, dtype=np.uint8))
        t_morphed = cv2.morphologyEx(t_mask, cv2.MORPH_CLOSE, kernel_3x3)
        t_cnts, _ = cv2.findContours(t_morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_candidates = []
        for c in t_cnts:
            cx, cy, cw, ch = cv2.boundingRect(c)
            c_area = cw * ch
            c_asp = float(cw) / float(max(1, ch))
            if c_area >= 15_000 and 1.4 <= c_asp <= 2.6:
                valid_candidates.append({"rect": [cx, cy, cw, ch], "area": c_area, "aspect": round(c_asp, 3)})
        hsv_tests_summary[name] = {
            "total_contours": len(t_cnts),
            "valid_candidates": valid_candidates,
        }
    info["hsv_tests"] = hsv_tests_summary

    # 5. Generate visual debug overlay
    overlay = img_bgr.copy()
    # Draw catsung candidate if found
    if best_catsung_rect is not None:
        cx, cy, cw, ch = best_catsung_rect
        gx = int(round(orig_w * 0.60)) + cx
        cv2.rectangle(overlay, (gx, cy), (gx + cw, cy + ch), (0, 255, 0), 3)
        cv2.putText(overlay, f"CAT: {cw}x{ch}", (gx, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # Save visual debug image
    debug_img_path = out_dir / f"{image_path.stem}_debug.jpg"
    cv2.imwrite(str(debug_img_path), overlay)
    info["debug_image"] = str(debug_img_path)

    return info


def run_diagnostics(input_path_str: str) -> dict[str, Any]:
    """Runs diagnostics on all images in input directory and produces summary report."""
    input_dir = Path(input_path_str).resolve()
    if not input_dir.is_dir():
        alt = REPO_ROOT / input_path_str
        if alt.is_dir():
            input_dir = alt.resolve()
        else:
            raise FileNotFoundError(f"Input directory does not exist: {input_path_str}")

    image_files = find_supported_images(input_dir)
    out_dir = NEXT_ROOT / "workspace" / "gun_debug"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("PUBG GUN DETECTOR DIAGNOSTIC SUITE")
    print(f"Input directory (READ-ONLY): {input_dir}")
    print(f"Output directory:            {out_dir}")
    print(f"Total images found:          {len(image_files)}")
    print("=" * 80)

    classifier = ScreenClassifier()
    gun_detector = GunDetector()

    results: list[dict[str, Any]] = []
    gun_count = 0
    current_passed_count = 0
    catsung_passed_count = 0

    for img_path in image_files:
        info = inspect_gun_screen(img_path, out_dir, classifier, gun_detector)
        results.append(info)

        if info.get("is_gun"):
            gun_count += 1
            curr_pass = info.get("current_detector", {}).get("detected", False)
            cat_pass = info.get("catsung_best_rect") is not None
            if curr_pass:
                current_passed_count += 1
            if cat_pass:
                catsung_passed_count += 1

            print(f"[{gun_count:02d}] {info['filename']} ({info['width']}x{info['height']})")
            print(f"     Current GunDetector: detected={curr_pass}")
            if not curr_pass:
                reasons = info.get("current_detector", {}).get("reasons", [])
                print(f"     Current Rejection Reasons: {reasons}")
                # Print why contours failed in scan space
                scan_cnts = info.get("scan_contours_log", [])
                if scan_cnts:
                    print(f"     Top scan contours ({len(scan_cnts)} total):")
                    for sc in sorted(scan_cnts, key=lambda c: c["area"], reverse=True)[:3]:
                        print(f"       bbox={sc['bbox']}, area={sc['area']}, aspect={sc['aspect']}, rejections={sc['rejections']}")
                else:
                    print("     No scan contours found with current ORANGE mask!")

            print(f"     Catsung reference:   detected={cat_pass} rect={info.get('catsung_best_rect')}")
            for hsv_k, hsv_v in info.get("hsv_tests", {}).items():
                print(f"     {hsv_k}: valid_candidates={len(hsv_v.get('valid_candidates', []))}")
            print("-" * 60)

    summary = {
        "timestamp": time.time(),
        "input_directory": str(input_dir),
        "total_images": len(image_files),
        "gun_images_count": gun_count,
        "current_gun_detector_passed": current_passed_count,
        "catsung_reference_passed": catsung_passed_count,
        "results": results,
    }

    summary_json_path = out_dir / "summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(to_json_native(summary), f, indent=2)

    print("=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f"Total GUN images classified:    {gun_count}")
    print(f"Current GunDetector detected:    {current_passed_count} / {gun_count}")
    print(f"Catsung reference detected:      {catsung_passed_count} / {gun_count}")
    print(f"Summary JSON saved to:          {summary_json_path}")
    print("=" * 80)

    return summary


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "Cắt/input"
    run_diagnostics(target)
