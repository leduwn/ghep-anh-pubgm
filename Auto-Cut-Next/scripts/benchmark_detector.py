#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Microbenchmark for generic card grid detector, quality pipeline, and perceptual dedup."""

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

from detectors import (
    DetectionContext,
    GenericDetector,
    CardGeometryProfile,
    compute_phash,
    AccountDeduplicator,
)


def generate_synthetic_grid_screen(
    width: int,
    height: int,
    rows: int = 3,
    cols: int = 3,
    seed: int = 42,
) -> np.ndarray:
    """Generates realistic synthetic inventory screen with grid cards and textures."""
    rng = np.random.default_rng(seed)

    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = (180, 180, 180)  # Light gray background

    card_w = int(round(120 * (width / 1920.0)))
    card_h = int(round(120 * (height / 1080.0)))
    step_x = int(round(145 * (width / 1920.0)))
    step_y = int(round(145 * (height / 1080.0)))

    start_x = int(round(1000 * (width / 1920.0)))
    start_y = int(round(150 * (height / 1080.0)))

    for r in range(rows):
        cy = start_y + r * step_y
        for c in range(cols):
            cx = start_x + c * step_x
            if cx + card_w <= width and cy + card_h <= height:
                # Dark tile background
                img[cy:cy + card_h, cx:cx + card_w] = (35, 30, 25)
                # Inner card texture/content
                noise = rng.integers(50, 200, size=(card_h - 20, card_w - 20, 3), dtype=np.uint8)
                img[cy + 10:cy + card_h - 10, cx + 10:cx + card_w - 10] = noise
                # Border
                cv2.rectangle(img, (cx, cy), (cx + card_w, cy + card_h), (80, 80, 80), 2)

    return img



def run_benchmarks():
    targets = [
        ("1-Row 3-Tiles (1920x1080)", 1920, 1080, 1, 3),
        ("3-Rows 3-Cols (1920x1080)", 1920, 1080, 3, 3),
        ("3-Rows 3-Cols Native (2778x1284)", 2778, 1284, 3, 3),
    ]

    print("=" * 75)
    print("         AUTO-CUT-NEXT GENERIC DETECTOR MICROBENCHMARK")
    print("=" * 75)

    iterations = 25
    warmup = 5
    detector = GenericDetector()

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)

        for label, w, h, r_cnt, c_cnt in targets:
            img = generate_synthetic_grid_screen(w, h, rows=r_cnt, cols=c_cnt)
            img_path = temp_dir / f"grid_{w}_{h}_{r_cnt}x{c_cnt}.png"
            cv2.imencode(".png", img)[1].tofile(str(img_path))
            file_size_kb = img_path.stat().st_size / 1024.0

            # Warm-up
            for _ in range(warmup):
                data = img_path.read_bytes()
                arr = np.frombuffer(data, np.uint8)
                decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                ctx = DetectionContext(decoded)
                detector.detect_grid(ctx)
                ctx.close()

            decode_times = []
            context_times = []
            cand_times = []
            grid_times = []
            quality_times = []
            fingerprint_times = []
            total_times = []

            for _ in range(iterations):
                t0 = time.perf_counter()

                # Decode
                t_dec0 = time.perf_counter()
                data = img_path.read_bytes()
                arr = np.frombuffer(data, np.uint8)
                decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                t_dec1 = time.perf_counter()

                # Context prep
                t_ctx0 = time.perf_counter()
                ctx = DetectionContext(decoded)
                t_ctx1 = time.perf_counter()

                # Candidate discovery
                t_c0 = time.perf_counter()
                candidates = detector.grid_detector.discover_candidates(ctx, detector.profile)
                t_c1 = time.perf_counter()

                # Grid reconstruction
                t_g0 = time.perf_counter()
                ordered = detector.grid_detector.reconstruct_grid(candidates, detector.profile, ctx.scan_w, ctx.scan_h)
                t_g1 = time.perf_counter()

                # Quality evaluation
                t_q0 = time.perf_counter()
                for r_scan, _, _ in ordered:
                    orig_r = ctx.scan_to_original_rect(r_scan)
                    tile = ctx.crop_original(orig_r)
                    detector.quality_evaluator.evaluate(tile)
                t_q1 = time.perf_counter()

                # Fingerprint (pHash)
                t_f0 = time.perf_counter()
                for r_scan, _, _ in ordered:
                    orig_r = ctx.scan_to_original_rect(r_scan)
                    tile = ctx.crop_original(orig_r)
                    compute_phash(tile)
                t_f1 = time.perf_counter()

                t_total = time.perf_counter()
                ctx.close()

                decode_times.append((t_dec1 - t_dec0) * 1000.0)
                context_times.append((t_ctx1 - t_ctx0) * 1000.0)
                cand_times.append((t_c1 - t_c0) * 1000.0)
                grid_times.append((t_g1 - t_g0) * 1000.0)
                quality_times.append((t_q1 - t_q0) * 1000.0)
                fingerprint_times.append((t_f1 - t_f0) * 1000.0)
                total_times.append((t_total - t0) * 1000.0)

            def p95(data: list[float]) -> float:
                return float(np.percentile(data, 95))

            print(f"\nBenchmark Target: {label}")
            print(f"File Size:        {file_size_kb:.1f} KB | Cards: {r_cnt * c_cnt} | Iterations: {iterations}")
            print(f"Stage                  Median (ms)     P95 (ms)")
            print(f"--------------------------------------------------")
            print(f"Decode:               {statistics.median(decode_times):10.2f}     {p95(decode_times):10.2f}")
            print(f"Context Prep (Resize):{statistics.median(context_times):10.2f}     {p95(context_times):10.2f}")
            print(f"Candidate Discovery:  {statistics.median(cand_times):10.2f}     {p95(cand_times):10.2f}")
            print(f"Grid Reconstruction:  {statistics.median(grid_times):10.2f}     {p95(grid_times):10.2f}")
            print(f"Quality Check:        {statistics.median(quality_times):10.2f}     {p95(quality_times):10.2f}")
            print(f"pHash Fingerprint:    {statistics.median(fingerprint_times):10.2f}     {p95(fingerprint_times):10.2f}")
            print(f"End-to-End Total:     {statistics.median(total_times):10.2f}     {p95(total_times):10.2f}")

    print("\n" + "=" * 75)


if __name__ == "__main__":
    run_benchmarks()

