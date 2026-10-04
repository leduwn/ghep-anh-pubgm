#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Realistic microbenchmark for source image ingestion stages."""

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

from core.ingest import compute_sha256, read_image_cv2, write_image_cv2, ImageIngestor


def generate_high_entropy_image(width: int, height: int, seed: int = 42) -> np.ndarray:
    """Generates realistic synthetic game screenshot with gradients, geometric cards, and high entropy noise."""
    rng = np.random.default_rng(seed)

    # Base gradient background
    y_grad = np.linspace(20, 60, height, dtype=np.uint8)[:, None]
    x_grad = np.linspace(20, 50, width, dtype=np.uint8)[None, :]
    base = np.zeros((height, width, 3), dtype=np.uint8)
    base[:, :, 0] = (y_grad * 0.7 + x_grad * 0.3).astype(np.uint8)
    base[:, :, 1] = (y_grad * 0.5 + x_grad * 0.5).astype(np.uint8)
    base[:, :, 2] = (y_grad * 0.4 + x_grad * 0.6).astype(np.uint8)

    # Add realistic texture noise
    noise = rng.integers(-15, 15, size=(height, width, 3), dtype=np.int16)
    blended = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Draw simulated UI card rectangles with high entropy content
    num_cards = 8
    for i in range(num_cards):
        cx = int((i % 4) * (width / 4) + 30)
        cy = int((i // 4) * (height / 3) + 50)
        cw = int(width / 4 - 60)
        ch = int(height / 3 - 80)
        if cx + cw < width and cy + ch < height:
            card_noise = rng.integers(50, 220, size=(ch, cw, 3), dtype=np.uint8)
            blended[cy:cy + ch, cx:cx + cw] = card_noise
            cv2.rectangle(blended, (cx, cy), (cx + cw, cy + ch), (220, 180, 50), 2)
            cv2.putText(blended, f"ITEM {i+1}", (cx + 10, cy + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    return blended


def run_benchmark_for_file(file_path: Path, iterations: int = 20) -> dict:
    file_size_kb = file_path.stat().st_size / 1024.0
    ingestor = ImageIngestor(thumb_max_dim=320)

    stat_times = []
    hash_times = []
    decode_times = []
    thumb_times = []
    total_times = []

    with tempfile.TemporaryDirectory() as td:
        thumb_dir = Path(td)
        for idx in range(iterations):
            t_start = time.perf_counter()

            # 1. Stat
            t0 = time.perf_counter()
            _ = file_path.stat().st_mtime
            stat_times.append((time.perf_counter() - t0) * 1000.0)

            # 2. SHA-256
            t0 = time.perf_counter()
            sha = compute_sha256(file_path)
            hash_times.append((time.perf_counter() - t0) * 1000.0)

            # 3. Decode
            t0 = time.perf_counter()
            img = read_image_cv2(file_path)
            decode_times.append((time.perf_counter() - t0) * 1000.0)

            # 4. Thumbnail
            t0 = time.perf_counter()
            if img is not None:
                h, w = img.shape[:2]
                scale = min(320 / float(max(w, h)), 1.0)
                tw, th = max(1, round(w * scale)), max(1, round(h * scale))
                thumb = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
                thumb_target = thumb_dir / f"th_{idx}.jpg"
                write_image_cv2(thumb_target, thumb, ext=".jpg")
            thumb_times.append((time.perf_counter() - t0) * 1000.0)

            total_times.append((time.perf_counter() - t_start) * 1000.0)

    def calc_stats(arr):
        s = sorted(arr)
        p95_idx = int(len(s) * 0.95)
        return statistics.median(s), s[p95_idx]

    return {
        "file_size_kb": file_size_kb,
        "iterations": iterations,
        "stat": calc_stats(stat_times),
        "hash": calc_stats(hash_times),
        "decode": calc_stats(decode_times),
        "thumb": calc_stats(thumb_times),
        "total": calc_stats(total_times),
    }


def main():
    print("=" * 70)
    print("           AUTO-CUT-NEXT REALISTIC INGEST MICROBENCHMARK")
    print("=" * 70)

    configs = [
        ("1920x1080 PNG", 1920, 1080, ".png"),
        ("2778x1284 PNG", 2778, 1284, ".png"),
        ("1920x1080 JPEG", 1920, 1080, ".jpg"),
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        for label, w, h, ext in configs:
            img = generate_high_entropy_image(w, h, seed=42)
            fpath = td / f"bench_{w}x{h}{ext}"
            write_image_cv2(fpath, img, ext=ext)

            res = run_benchmark_for_file(fpath, iterations=20)
            med_tot, p95_tot = res["total"]
            med_dec, p95_dec = res["decode"]
            med_hsh, p95_hsh = res["hash"]
            med_thm, p95_thm = res["thumb"]

            print(f"\n[+] Target: {label}")
            print(f"    File Size:   {res['file_size_kb']:.1f} KB  ({res['iterations']} iterations)")
            print(f"    SHA-256:     median = {med_hsh:6.2f} ms | p95 = {p95_hsh:6.2f} ms")
            print(f"    Decode:      median = {med_dec:6.2f} ms | p95 = {p95_dec:6.2f} ms")
            print(f"    Thumbnail:   median = {med_thm:6.2f} ms | p95 = {p95_thm:6.2f} ms")
            print(f"    TOTAL:       median = {med_tot:6.2f} ms | p95 = {p95_tot:6.2f} ms")

    print("\n" + "=" * 70)
    print("Benchmark complete.")


if __name__ == "__main__":
    main()
