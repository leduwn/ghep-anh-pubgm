"""Micro-benchmark for Milestone 5 OCR subsystem, parsers, cache, and badge presence check."""

from __future__ import annotations

import gc
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

from core.models import DetectedAsset, Rect
from ocr.cache import OCRCache, build_ocr_cache_key
from ocr.engine import FakeOCREngine
from ocr.gun_ocr import GunOCRExtractor
from ocr.models import OCRObservation, UIDCandidate
from ocr.parsers import (
    parse_gun_level,
    parse_gun_name,
    parse_kill_counter,
    parse_progress_level,
    parse_uid,
)
from ocr.preprocessing import check_counter_badge_presence
from ocr.uid_ocr import resolve_uid_consensus


def benchmark_parsers(iterations: int = 5000):
    print("=" * 60)
    print("1. PURE PARSER BENCHMARKS")
    print("=" * 60)

    # 1. Progress Level Parser
    sample_texts = ["Tiến độ: 3/3", "Cấp 4/7", "Tiến độ: 7/7", "I/5", "Invalid string without numbers"]
    t0 = time.perf_counter()
    for _ in range(iterations):
        for text in sample_texts:
            parse_progress_level(text)
    t_elapsed = time.perf_counter() - t0
    ops = (iterations * len(sample_texts)) / t_elapsed
    print(f"Level Progress Parser:     {ops:10.1f} ops/s  ({t_elapsed*1000/(iterations*len(sample_texts)):.4f} ms/op)")

    # 2. Gun Name Parser
    obs_samples = [
        [OCRObservation(text="M416 Băng Giá", confidence=0.98)],
        [OCRObservation(text="AKIVI Hoả Ngục", confidence=0.90)],
        [OCRObservation(text="AUG Hoàng Kim", confidence=0.95)],
        [OCRObservation(text="Sung Luc Khac", confidence=0.80)],
    ]
    t0 = time.perf_counter()
    for _ in range(iterations):
        for obs in obs_samples:
            parse_gun_name(obs)
    t_elapsed = time.perf_counter() - t0
    ops = (iterations * len(obs_samples)) / t_elapsed
    print(f"Gun Name Parser:           {ops:10.1f} ops/s  ({t_elapsed*1000/(iterations*len(obs_samples)):.4f} ms/op)")

    # 3. UID Parser
    uid_samples = [
        [OCRObservation(text="UID: 5123456789", confidence=0.96)],
        [OCRObservation(text="U1D: 5l2345678O", confidence=0.92)],
        [OCRObservation(text="RANDOM_TEXT_NO_ID", confidence=0.50)],
    ]
    t0 = time.perf_counter()
    for _ in range(iterations):
        for obs in uid_samples:
            parse_uid(obs, source_id="s1")
    t_elapsed = time.perf_counter() - t0
    ops = (iterations * len(uid_samples)) / t_elapsed
    print(f"UID Parser:                {ops:10.1f} ops/s  ({t_elapsed*1000/(iterations*len(uid_samples)):.4f} ms/op)")

    # 4. Multi-Source Consensus Resolver
    cands = [
        UIDCandidate(uid="5123456789", confidence=0.92, source_id="s1", raw_text="UID: 5123456789"),
        UIDCandidate(uid="5123456789", confidence=0.95, source_id="s2", raw_text="UID: 5123456789"),
    ]
    t0 = time.perf_counter()
    for _ in range(iterations):
        resolve_uid_consensus(cands)
    t_elapsed = time.perf_counter() - t0
    ops = iterations / t_elapsed
    print(f"UID Consensus Resolver:    {ops:10.1f} ops/s  ({t_elapsed*1000/iterations:.4f} ms/op)")
    print()


def benchmark_badge_presence(iterations: int = 1000):
    print("=" * 60)
    print("2. VISUAL BADGE PRESENCE CHECK BENCHMARK")
    print("=" * 60)

    # Synthetic ROI
    roi_bgr = np.zeros((100, 200, 3), dtype=np.uint8)
    roi_bgr[:] = (0, 180, 255)
    for i in range(15):
        cv2.line(roi_bgr, (i * 12, 0), (i * 12, 100), (255, 255, 255), 2)

    t0 = time.perf_counter()
    for _ in range(iterations):
        check_counter_badge_presence(roi_bgr)
    t_elapsed = time.perf_counter() - t0
    fps = iterations / t_elapsed
    ms_per_check = (t_elapsed / iterations) * 1000.0
    print(f"Badge Check (Canny + Saturation): {fps:8.1f} checks/s ({ms_per_check:.3f} ms/check)")
    print()


def benchmark_two_level_cache(iterations: int = 5000):
    print("=" * 60)
    print("3. TWO-LEVEL CACHE LATENCY BENCHMARK")
    print("=" * 60)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cache = OCRCache(cache_dir=td, memory_capacity=1000)
        obs = [OCRObservation(text="M416", confidence=0.99)]
        key = build_ocr_cache_key("sha_test", Rect(0, 0, 100, 100), route="benchmark")
        cache.put(key, obs)

        # Memory Hit
        t0 = time.perf_counter()
        for _ in range(iterations):
            cache.get(key)
        t_elapsed = time.perf_counter() - t0
        ops = iterations / t_elapsed
        print(f"Memory LRU Hit:            {ops:10.1f} reads/s ({t_elapsed*1000/iterations:.4f} ms/read)")

        # Clear memory to force Disk Hit
        cache.memory_cache.clear()
        t0 = time.perf_counter()
        for _ in range(iterations // 5):
            cache.disk_cache.get(key)
        t_elapsed = time.perf_counter() - t0
        disk_ops = (iterations // 5) / t_elapsed
        print(f"DiskCache JSON Read:       {disk_ops:10.1f} reads/s ({t_elapsed*1000/(iterations//5):.4f} ms/read)")
        print()


def benchmark_end_to_end_extractor(iterations: int = 500):
    print("=" * 60)
    print("4. SIMULATED FAKE OCR PIPELINE (OFFLINE / SYNTHETIC)")
    print("=" * 60)

    fake_engine = FakeOCREngine(default_observations=[
        OCRObservation(text="Tiến độ: 3/3", confidence=0.95),
        OCRObservation(text="M416 Băng Giá", confidence=0.98),
        OCRObservation(text="1284", confidence=0.96),
    ])

    extractor = GunOCRExtractor(engine=fake_engine)
    dummy_img = np.zeros((720, 1280, 3), dtype=np.uint8)
    asset = DetectedAsset(
        id="test_gun_asset",
        source_id="src_1",
        category="GUN",
        crop_rect=Rect(700, 150, 300, 200),
        native_width=300,
        native_height=200,
        detector="gun_workshop_detector",
        detector_version="1.0.0",
    )

    t0 = time.perf_counter()
    for _ in range(iterations):
        res = extractor.extract(dummy_img, source_sha256="sha_bench", asset=asset)
    t_elapsed = time.perf_counter() - t0
    ops = iterations / t_elapsed
    print(f"Simulated Fake OCR Pipeline: {ops:8.1f} assets/s ({(t_elapsed/iterations)*1000.0:.3f} ms/asset)")
    print("=" * 60)


if __name__ == "__main__":
    benchmark_parsers()
    benchmark_badge_presence()
    benchmark_two_level_cache()
    benchmark_end_to_end_extractor()
