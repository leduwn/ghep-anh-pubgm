#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Microbenchmark for screen classifier: decode, context prep, signals, decision, total."""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

# Ensure Auto-Cut-Next root is in sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
NEXT_ROOT = SCRIPTS_DIR.parent
if str(NEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXT_ROOT))

from core.ingest import write_image_cv2
from detectors import ClassificationContext, ScreenClassifier


def generate_benchmark_screen(width: int, height: int, seed: int = 42) -> np.ndarray:
    """Creates realistic synthetic PUBG-like game screenshot with tabs and UI cards."""
    rng = np.random.default_rng(seed)

    # Base dark gradient
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = (35, 30, 25)

    # Draw vertical main tab strip (blue indicator)
    scale_x = width / 2778.0
    scale_y = height / 1284.0

    # Right side wardrobe rail & tabs
    tab_x1 = int(round(2530 * scale_x))
    tab_x2 = int(round(2580 * scale_x))
    cv2.rectangle(img, (tab_x1, 0), (tab_x2, height), (45, 40, 35), -1)

    # Blue tab indicator around vehicle tab (y ~ 550)
    ind_y1 = int(round(520 * scale_y))
    ind_y2 = int(round(570 * scale_y))
    cv2.rectangle(img, (tab_x1 + 2, ind_y1), (tab_x2 - 2, ind_y2), (220, 160, 40), -1)  # BGR blue

    # Inventory grid cards
    cols = [(1718, 1939), (1955, 2176), (2191, 2411)]
    for row in range(3):
        cy1 = int(round((210 + row * 267) * scale_y))
        cy2 = int(round((210 + row * 267 + 250) * scale_y))
        for cx1_ref, cx2_ref in cols:
            cx1 = int(round(cx1_ref * scale_x))
            cx2 = int(round(cx2_ref * scale_x))
            if cy2 < height and cx2 < width:
                card_noise = rng.integers(40, 180, size=(cy2 - cy1, cx2 - cx1, 3), dtype=np.uint8)
                img[cy1:cy2, cx1:cx2] = card_noise

    return img



def run_benchmarks():
    resolutions = [
        ("1080p (1920x1080)", 1920, 1080, ".png"),
        ("PUBG Native (2778x1284)", 2778, 1284, ".png"),
        ("1080p JPEG (Q85)", 1920, 1080, ".jpg"),
    ]

    print("=" * 75)
    print("         AUTO-CUT-NEXT SCREEN CLASSIFIER MICROBENCHMARK")
    print("=" * 75)

    iterations = 25
    warmup = 5
    classifier = ScreenClassifier()

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)

        for label, w, h, ext in resolutions:
            img = generate_benchmark_screen(w, h)
            img_path = temp_dir / f"bench_{w}_{h}{ext}"

            if ext == ".jpg":
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                success, buf = cv2.imencode(".jpg", img, encode_param)
                if success:
                    img_path.write_bytes(buf.tobytes())
            else:
                success, buf = cv2.imencode(".png", img)
                if success:
                    img_path.write_bytes(buf.tobytes())

            file_size_kb = img_path.stat().st_size / 1024.0

            # Warm-up
            for _ in range(warmup):
                data = img_path.read_bytes()
                arr = np.frombuffer(data, np.uint8)
                decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                ctx = ClassificationContext(decoded, max_scan_dim=1600)
                classifier.classify(ctx)
                ctx.close()

            decode_times = []
            context_times = []
            classify_times = []
            total_times = []

            for _ in range(iterations):
                t0 = time.perf_counter()

                # 1. Decode
                t_dec0 = time.perf_counter()
                data = img_path.read_bytes()
                arr = np.frombuffer(data, np.uint8)
                decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                t_dec1 = time.perf_counter()

                # 2. Context prep (single downscale to max 1600)
                t_ctx0 = time.perf_counter()
                ctx = ClassificationContext(decoded, max_scan_dim=1600)
                t_ctx1 = time.perf_counter()

                # 3. Classify (signals + decision)
                t_cls0 = time.perf_counter()
                classifier.classify(ctx)
                t_cls1 = time.perf_counter()

                t_total1 = time.perf_counter()
                ctx.close()

                decode_times.append((t_dec1 - t_dec0) * 1000.0)
                context_times.append((t_ctx1 - t_ctx0) * 1000.0)
                classify_times.append((t_cls1 - t_cls0) * 1000.0)
                total_times.append((t_total1 - t0) * 1000.0)

            def p95(data: list[float]) -> float:
                return float(np.percentile(data, 95))

            print(f"\nBenchmark Target: {label}")
            print(f"File Size:        {file_size_kb:.1f} KB | Iterations: {iterations}")
            print(f"Stage                  Median (ms)     P95 (ms)")
            print(f"--------------------------------------------------")
            print(f"Decode:               {statistics.median(decode_times):10.2f}     {p95(decode_times):10.2f}")
            print(f"Context Prep (Resize):{statistics.median(context_times):10.2f}     {p95(context_times):10.2f}")
            print(f"Classify Compute:     {statistics.median(classify_times):10.2f}     {p95(classify_times):10.2f}")
            print(f"End-to-End Total:     {statistics.median(total_times):10.2f}     {p95(total_times):10.2f}")

    print("\n" + "=" * 75)


if __name__ == "__main__":
    run_benchmarks()

