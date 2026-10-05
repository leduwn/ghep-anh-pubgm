"""Micro-benchmark for Milestone 4 specialized detectors and zero-redecode fallback."""

from __future__ import annotations

import gc
import os
import sys
import time
from pathlib import Path
import cv2
import numpy as np

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import Category
from core.models import ClassificationResult
from detectors.detection_context import DetectionContext
from detectors.gun_detector import GunDetector
from detectors.vehicle_detector import VehicleDetector
from detectors.outfit_detector import OutfitDetector
from detectors.equipment_detector import EquipmentDetector
from detectors.accessory_detector import AccessoryDetector
from detectors.inventory_detector import InventoryDetector
from detectors.router import CategoryRouter


def generate_synthetic_screen(category: str, w: int = 1920, h: int = 1080) -> np.ndarray:
    """Generates synthetic test screens tailored to categories."""
    img = np.full((h, w, 3), 25, dtype=np.uint8)

    if category == Category.GUN.value:
        # Workshop card
        card_x, card_y, card_w, card_h = int(0.60 * w), int(0.25 * h), int(0.25 * w), int(0.22 * h)
        cv2.rectangle(img, (card_x, card_y), (card_x + card_w, card_y + card_h), (30, 140, 240), 8)
        cv2.rectangle(img, (card_x + 8, card_y + 8), (card_x + card_w - 8, card_y + card_h - 8), (75, 75, 75), -1)

    elif category == Category.VEHICLE.value:
        # Vehicle gallery column
        col_x = int(0.70 * w)
        card_w = int(0.16 * w)
        card_h = int(card_w / 2.62)
        for i in range(3):
            cy = int(0.18 * h) + i * (card_h + 30)
            cv2.rectangle(img, (col_x, cy), (col_x + card_w, cy + card_h), (180, 180, 180), 2)
            cv2.rectangle(img, (col_x + 3, cy + 3), (col_x + card_w - 3, cy + card_h - 3), (70, 70, 70), -1)

    elif category == Category.OUTFIT.value:
        # Character edges in lobby
        char_x = int(0.30 * w)
        cv2.rectangle(img, (char_x - 120, int(0.10 * h)), (char_x + 120, int(0.85 * h)), (100, 100, 100), -1)
        for y in range(int(0.15 * h), int(0.80 * h), 25):
            cv2.line(img, (char_x - 100, y), (char_x + 100, y), (200, 200, 200), 2)

    elif category in (Category.HELMET.value, Category.BACKPACK.value, Category.MASK.value):
        # 3x3 equipment grid
        start_x = int(0.62 * w)
        start_y = int(0.25 * h)
        tw = int(0.06 * w)
        th = int(0.10 * h)
        for r in range(3):
            for c in range(3):
                tx = start_x + c * (tw + 15)
                ty = start_y + r * (th + 15)
                cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (160, 160, 160), 2)
                cv2.rectangle(img, (tx + 3, ty + 3), (tx + tw - 3, ty + th - 3), (80, 80, 80), -1)

    elif category in (Category.GRENADE.value, Category.PARACHUTE.value, Category.EMOTE.value):
        # 2x2 accessory grid
        start_x = int(0.64 * w)
        start_y = int(0.26 * h)
        tw = int(0.06 * w)
        th = int(0.10 * h)
        for r in range(2):
            for c in range(2):
                tx = start_x + c * (tw + 15)
                ty = start_y + r * (th + 15)
                cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (160, 160, 160), 2)
                cv2.rectangle(img, (tx + 3, ty + 3), (tx + tw - 3, ty + th - 3), (80, 80, 80), -1)

    elif category in (Category.ITEM_SET.value, Category.MISC.value):
        # 2x3 inventory grid
        start_x = int(0.62 * w)
        start_y = int(0.20 * h)
        tw = int(0.06 * w)
        th = int(0.10 * h)
        for r in range(2):
            for c in range(3):
                tx = start_x + c * (tw + 15)
                ty = start_y + r * (th + 15)
                cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (160, 160, 160), 2)
                cv2.rectangle(img, (tx + 3, ty + 3), (tx + tw - 3, ty + th - 3), (80, 80, 80), -1)

    return img


def benchmark_detector(name: str, fn, runs: int = 20) -> tuple[float, float, float]:
    """Runs a function repeatedly and returns mean, p50, and p95 latencies in ms."""
    # Warmup
    for _ in range(3):
        fn()

    durations: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        durations.append((time.perf_counter() - t0) * 1000.0)

    durations.sort()
    mean_val = float(np.mean(durations))
    p50_val = durations[len(durations) // 2]
    p95_val = durations[int(len(durations) * 0.95)]
    return mean_val, p50_val, p95_val


def run_benchmarks():
    print("=" * 70)
    print("      MILESTONE 4: SPECIALIZED DETECTOR BENCHMARKS (1080p)")
    print("=" * 70)

    router = CategoryRouter()

    benchmarks = [
        ("GunDetector (Workshop Card)", Category.GUN.value, router.gun_detector.detect),
        ("VehicleDetector (3 Cards)", Category.VEHICLE.value, router.vehicle_detector.detect),
        ("OutfitDetector (Character Lobby)", Category.OUTFIT.value, router.outfit_detector.detect),
        ("EquipmentDetector (3x3 Grid)", Category.HELMET.value, lambda ctx: router.equipment_detector.detect(ctx, classification=ClassificationResult(Category.HELMET.value, 0.9))),
        ("AccessoryDetector (2x2 Grid)", Category.GRENADE.value, lambda ctx: router.accessory_detector.detect(ctx, classification=ClassificationResult(Category.GRENADE.value, 0.9))),
        ("InventoryDetector (2x3 Grid)", Category.ITEM_SET.value, lambda ctx: router.inventory_detector.detect(ctx, classification=ClassificationResult(Category.ITEM_SET.value, 0.9))),
    ]

    print(f"{'Detector / Scenario':<36} | {'Mean (ms)':<10} | {'p50 (ms)':<10} | {'p95 (ms)':<10}")
    print("-" * 72)

    for desc, cat, det_fn in benchmarks:
        img = generate_synthetic_screen(cat)
        ctx = DetectionContext(img, source_id="bench_src", max_scan_dim=1280)
        mean_ms, p50_ms, p95_ms = benchmark_detector(desc, lambda: det_fn(ctx), runs=20)
        print(f"{desc:<36} | {mean_ms:10.2f} | {p50_ms:10.2f} | {p95_ms:10.2f}")
        ctx.close()

    print("-" * 72)
    print("SHARED-CONTEXT FALLBACK OVERHEAD BENCHMARK")
    print("-" * 72)

    # Blank screen classified as GUN -> GunDetector fails -> GenericGridDetector runs on same context
    blank_img = np.full((1080, 1920, 3), 20, dtype=np.uint8)
    blank_ctx = DetectionContext(blank_img, source_id="bench_blank", max_scan_dim=1280)
    class_gun = ClassificationResult(Category.GUN.value, 0.9)

    mean_fb, p50_fb, p95_fb = benchmark_detector(
        "Router Fallback (Gun -> Generic)",
        lambda: router.route(blank_ctx, classification=class_gun),
        runs=20,
    )
    print(f"{'Router Fallback (Zero-Redecode)':<36} | {mean_fb:10.2f} | {p50_fb:10.2f} | {p95_fb:10.2f}")
    blank_ctx.close()

    print("=" * 70)
    print("Benchmark complete.")


if __name__ == "__main__":
    run_benchmarks()
