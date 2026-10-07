#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validation script for real PUBG screenshots in Cắt/input against Milestone 1-5 pipeline.

READ-ONLY on input directory. Never writes to legacy directories.
Outputs session and debug reports under Auto-Cut-Next/workspace/real_fixture_validation/.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Ensure Auto-Cut-Next is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
NEXT_ROOT = SCRIPT_DIR.parent
REPO_ROOT = NEXT_ROOT.parent

if str(NEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXT_ROOT))

from core.constants import Category, Decision, DetectionStatus
from core.ingest import read_image_cv2
from core.models import Rect
from core.session import WorkspaceManager
from core.serialization import to_json_native
from app.pipeline import AutoCutPipeline
from ocr.gun_ocr import resolve_gun_rois


def find_supported_images(input_dir: Path) -> list[Path]:
    """Discovers all supported image formats in input_dir."""
    extensions = {".png", ".jpg", ".jpeg"}
    images: list[Path] = []
    for f in input_dir.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            images.append(f)
    return sorted(images, key=lambda p: p.name)


def validate_real_fixtures(input_path_str: str) -> dict[str, Any]:
    """Runs ingestion, classification, and detection against real screenshots."""
    # Resolve input directory
    input_dir = Path(input_path_str).resolve()
    if not input_dir.is_dir():
        # Try relative to repo root
        alt = REPO_ROOT / input_path_str
        if alt.is_dir():
            input_dir = alt.resolve()
        else:
            raise FileNotFoundError(f"Input directory does not exist: {input_path_str}")

    image_files = find_supported_images(input_dir)
    if not image_files:
        print(f"No supported images found in {input_dir}")
        return {"error": "No images found", "input_dir": str(input_dir)}

    # Set up isolated workspace under Auto-Cut-Next/workspace/real_fixture_validation
    out_dir = NEXT_ROOT / "workspace" / "real_fixture_validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    ws = WorkspaceManager(out_dir)
    pipeline = AutoCutPipeline(workspace=ws)
    account_id = "real_pubg_validation"

    print("=" * 80)
    print(f"REAL PUBG FIXTURE VALIDATION — {len(image_files)} IMAGES")
    print(f"Source Directory (READ-ONLY): {input_dir}")
    print(f"Output Workspace:             {out_dir}")
    print("=" * 80)

    # 1. Ingest
    session = pipeline.ingest_sources(account_id, image_files)
    ingested_count = len(session.sources)
    print(f"[1/3] Ingested: {ingested_count}/{len(image_files)} sources")

    # 2. Classify
    t0_class = time.perf_counter()
    session = pipeline.classify_session(account_id)
    t_class = time.perf_counter() - t0_class
    print(f"[2/3] Classified: {len(session.classifications)} sources ({t_class:.2f}s)")

    # 3. Detect
    t0_det = time.perf_counter()
    session = pipeline.detect_session(account_id)
    t_det = time.perf_counter() - t0_det
    print(f"[3/3] Detection completed: {len(session.assets)} total assets ({t_det:.2f}s)")
    print("-" * 80)

    # Compile report metrics
    class_summary: dict[str, int] = Counter()
    decision_summary: dict[str, int] = Counter()
    det_status_summary: dict[str, int] = Counter()
    detector_summary: dict[str, int] = Counter()

    sources_report: list[dict[str, Any]] = []
    gun_sources_report: list[dict[str, Any]] = []

    for s_id, src in sorted(session.sources.items(), key=lambda item: item[1].filename):
        cl = session.classifications.get(s_id)
        det = session.detections.get(s_id)

        cat_val = cl.category if cl else "UNKNOWN"
        dec_val = cl.decision if cl else "UNKNOWN"
        class_summary[cat_val] += 1
        decision_summary[dec_val] += 1

        det_st = det.status if det else "NONE"
        det_status_summary[det_st] += 1

        primary_det = det.primary_detector if det else "none"
        final_det = det.detector if det else "none"
        detector_summary[final_det] += 1

        # Assets for this source
        src_assets = [a for a in session.assets if a.source_id == s_id]
        active_assets = [a for a in src_assets if not (a.locked or a.empty or a.partial or a.duplicate)]

        s_entry: dict[str, Any] = {
            "source_id": s_id,
            "filename": src.filename,
            "width": src.width,
            "height": src.height,
            "category": cat_val,
            "confidence": cl.confidence if cl else 0.0,
            "decision": dec_val,
            "primary_detector": primary_det,
            "final_detector": final_det,
            "fallback_attempted": det.fallback_attempted if det else False,
            "fallback_used": det.fallback_used if det else False,
            "detection_status": det_st,
            "asset_count": len(src_assets),
            "active_count": len(active_assets),
            "locked_count": sum(1 for a in src_assets if a.locked),
            "empty_count": sum(1 for a in src_assets if a.empty),
            "partial_count": sum(1 for a in src_assets if a.partial),
            "duplicate_count": sum(1 for a in src_assets if a.duplicate),
            "review_count": sum(1 for a in src_assets if a.review_required),
        }
        sources_report.append(s_entry)

        # Print per-source summary
        print(f"\n{src.filename} ({src.width}x{src.height})")
        print(f"  Classification: {cat_val} ({cl.confidence:.2f}) -> {dec_val}" if cl else "  Classification: None")
        if det:
            print(f"  Detection:      {final_det} [status={det_st}] | assets={len(src_assets)} (active={len(active_assets)}, empty={sum(1 for a in src_assets if a.empty)})")
            if det.fallback_attempted:
                print(f"                  fallback_attempted={det.fallback_attempted}, fallback_used={det.fallback_used}")

        # Specialized GUN report
        if cat_val == Category.GUN.value or any(a.category == Category.GUN.value for a in src_assets):
            gun_assets = [a for a in src_assets if a.category == Category.GUN.value]
            for ga in gun_assets:
                lvl_roi, nm_roi, cnt_roi = resolve_gun_rois(ga, (src.height, src.width))
                lvl_valid = (lvl_roi.x >= 0 and lvl_roi.y >= 0 and lvl_roi.right <= src.width and lvl_roi.bottom <= src.height)
                nm_valid = (nm_roi.x >= 0 and nm_roi.y >= 0 and nm_roi.right <= src.width and nm_roi.bottom <= src.height)
                cnt_valid = (cnt_roi.x >= 0 and cnt_roi.y >= 0 and cnt_roi.right <= src.width and cnt_roi.bottom <= src.height)

                content_sc = ga.metadata.get("content_score", 0.0) if ga.metadata else 0.0

                g_entry = {
                    "filename": src.filename,
                    "asset_id": ga.id,
                    "crop_rect": ga.crop_rect.to_dict(),
                    "content_score": round(float(content_sc), 4),
                    "empty": ga.empty,
                    "review_required": ga.review_required,
                    "level_roi_valid": lvl_valid,
                    "name_roi_valid": nm_valid,
                    "counter_roi_valid": cnt_valid,
                }
                gun_sources_report.append(g_entry)
                print(f"  Gun Asset:      content_score={content_sc:.2f}, empty={ga.empty}, review={ga.review_required}")
                print(f"                  ROIs valid: level={lvl_valid}, name={nm_valid}, counter={cnt_valid}")

    # Build report object
    report = {
        "timestamp": time.time(),
        "input_directory": str(input_dir),
        "total_sources_scanned": len(image_files),
        "total_ingested": ingested_count,
        "classification_summary": dict(class_summary),
        "decision_summary": dict(decision_summary),
        "detection_status_summary": dict(det_status_summary),
        "detector_summary": dict(detector_summary),
        "total_assets_detected": len(session.assets),
        "total_active_assets": sum(1 for a in session.assets if not (a.locked or a.empty or a.partial or a.duplicate)),
        "total_empty_assets": sum(1 for a in session.assets if a.empty),
        "total_duplicate_assets": sum(1 for a in session.assets if a.duplicate),
        "total_review_required": sum(1 for a in session.assets if a.review_required),
        "gun_assets": gun_sources_report,
        "sources": sources_report,
    }

    # Save machine-readable JSON
    report_json_path = out_dir / "report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(to_json_native(report), f, indent=2)

    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print(f"Categories detected:    {dict(class_summary)}")
    print(f"Decisions:              {dict(decision_summary)}")
    print(f"Detection Statuses:     {dict(det_status_summary)}")
    print(f"Detectors used:         {dict(detector_summary)}")
    print(f"Total Assets:           {len(session.assets)}")
    print(f"GUN Assets analyzed:    {len(gun_sources_report)}")
    for g in gun_sources_report:
        print(f"  - {g['filename']}: empty={g['empty']}, content_score={g['content_score']}")
    print(f"\nReport saved to: {report_json_path}")
    print("=" * 80)

    return report


if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "Cắt/input"
    validate_real_fixtures(target_dir)
