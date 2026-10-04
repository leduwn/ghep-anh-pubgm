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


def run_account_dedup_benchmark(temp_dir: Path):
    print("\n" + "=" * 75)
    print("      MULTI-SCREENSHOT ACCOUNT DEDUPLICATION BENCHMARK")
    print("=" * 75)

    num_screens = 3
    rows, cols = 3, 3
    cards_per_screen = rows * cols
    total_cards = num_screens * cards_per_screen

    screen_paths = []
    for s_idx in range(num_screens):
        seed = 42 if s_idx < 2 else 99
        img = generate_synthetic_grid_screen(1920, 1080, rows=rows, cols=cols, seed=seed)
        p = temp_dir / f"account_screen_{s_idx}.png"
        cv2.imencode(".png", img)[1].tofile(str(p))
        screen_paths.append(p)

    detector = GenericDetector()
    deduplicator = AccountDeduplicator()

    all_assets = []
    source_indices = {}
    source_images = {}

    for s_idx, p in enumerate(screen_paths):
        s_id = f"source_{s_idx}"
        source_indices[s_id] = s_idx
        data = p.read_bytes()
        arr = np.frombuffer(data, np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        source_images[s_id] = bgr
        ctx = DetectionContext(bgr, source_id=s_id, source_sha256=f"sha_{s_idx}")
        grid_res = detector.detect_grid(ctx)
        assets = detector.create_assets_from_candidates(
            grid_res.candidates,
            context=ctx,
            category="ITEM_SET",
            detector_version="2.1.0",
        )
        all_assets.extend(assets)
        ctx.close()

    iterations = 20

    # 1. Benchmark Naive Multi-Decode (decoding source image per card)
    naive_decode_times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        tiles = {}
        for asset in all_assets:
            s_idx = source_indices[asset.source_id]
            p = screen_paths[s_idx]
            d = p.read_bytes()
            img_bgr = cv2.imdecode(np.frombuffer(d, np.uint8), cv2.IMREAD_COLOR)
            r = asset.crop_rect
            tiles[asset.id] = img_bgr[r.y:r.y + r.h, r.x:r.x + r.w]
        t1 = time.perf_counter()
        naive_decode_times.append((t1 - t0) * 1000.0)

    # 2. Benchmark Single-Pass Grouped Decode (M3.1 optimization)
    single_pass_times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        tiles = {}
        grouped = {}
        for a in all_assets:
            grouped.setdefault(a.source_id, []).append(a)

        for sid, a_list in grouped.items():
            s_idx = source_indices[sid]
            p = screen_paths[s_idx]
            d = p.read_bytes()
            img_bgr = cv2.imdecode(np.frombuffer(d, np.uint8), cv2.IMREAD_COLOR)
            for a in a_list:
                r = a.crop_rect
                tiles[a.id] = img_bgr[r.y:r.y + r.h, r.x:r.x + r.w].copy()
            del img_bgr
        t1 = time.perf_counter()
        single_pass_times.append((t1 - t0) * 1000.0)

    # 3. Benchmark Perceptual Hash + MAE Dedup Algorithm
    extracted_tiles = {}
    for a in all_assets:
        bgr = source_images[a.source_id]
        r = a.crop_rect
        extracted_tiles[a.id] = bgr[r.y:r.y + r.h, r.x:r.x + r.w]

    dedup_algo_times = []
    dup_counts = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        updated, d_count = deduplicator.deduplicate_session_assets(
            all_assets,
            source_tiles=extracted_tiles,
            source_indices=source_indices,
        )
        t1 = time.perf_counter()
        dedup_algo_times.append((t1 - t0) * 1000.0)
        dup_counts.append(d_count)

    def p95(data: list[float]) -> float:
        return float(np.percentile(data, 95))

    med_naive = statistics.median(naive_decode_times)
    med_single = statistics.median(single_pass_times)
    speedup = med_naive / med_single if med_single > 0 else 1.0

    print(f"\nScenario: {num_screens} Screens x {cards_per_screen} Cards = {total_cards} Total Cards")
    print(f"Duplicates Identified: {dup_counts[0]}")
    print(f"\nDecoding Strategy Comparison (Iterations: {iterations}):")
    print(f"  Naive Multi-Decode (27 decodes):     Median {med_naive:6.2f} ms | P95 {p95(naive_decode_times):6.2f} ms")
    print(f"  Single-Pass Decode (3 decodes):      Median {med_single:6.2f} ms | P95 {p95(single_pass_times):6.2f} ms")
    print(f"  Single-Decode Efficiency Gain:       {speedup:6.1f}x faster")
    print(f"\nPerceptual Dedup Algorithm (pHash + MAE):")
    print(f"  Clustering & Comparison Time:        Median {statistics.median(dedup_algo_times):6.2f} ms | P95 {p95(dedup_algo_times):6.2f} ms")
    print(f"  End-to-End Account Dedup Time:       Median {med_single + statistics.median(dedup_algo_times):6.2f} ms")
    print("=" * 75)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        run_benchmarks()
        run_account_dedup_benchmark(Path(td))


