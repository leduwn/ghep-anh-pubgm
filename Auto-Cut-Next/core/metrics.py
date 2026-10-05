"""Metrics collection and execution profiling for Auto-Cut-Next."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class MetricsCollector:
    """Collects counters, durations and produces end-of-run performance reports."""
    sources_seen: int = 0
    sources_added: int = 0
    sources_duplicates: int = 0
    sources_forced: int = 0
    sources_failed: int = 0

    classify_seen: int = 0
    classify_cached: int = 0
    classify_processed: int = 0
    classify_auto: int = 0
    classify_review: int = 0
    classify_unknown: int = 0
    classify_errors: int = 0

    detect_sources_seen: int = 0
    detect_sources_processed: int = 0
    detect_sources_cached: int = 0
    detect_sources_deferred: int = 0
    detect_sources_no_grid: int = 0
    detect_sources_errors: int = 0

    # Specialized and Fallback Metrics
    specialized_attempted: int = 0
    specialized_success: int = 0
    specialized_review: int = 0
    fallback_attempted: int = 0
    fallback_success: int = 0
    fallback_selected: int = 0
    gun_detected: int = 0
    vehicle_detected: int = 0
    outfit_detected: int = 0
    equipment_detected: int = 0
    accessory_detected: int = 0
    inventory_detected: int = 0

    candidates_found: int = 0
    assets_created: int = 0

    locked_found: int = 0
    empty_found: int = 0
    partial_found: int = 0

    duplicates_found: int = 0
    detector_review_required: int = 0

    cache_write_errors: int = 0
    cache_corruptions: int = 0
    source_decodes: int = 0

    # OCR Metrics
    ocr_sources_seen: int = 0
    ocr_sources_processed: int = 0
    ocr_sources_cached: int = 0
    ocr_guns_processed: int = 0
    ocr_guns_success: int = 0
    ocr_guns_review: int = 0
    ocr_counters_found: int = 0
    ocr_counters_verified: int = 0
    ocr_uids_found: int = 0
    ocr_uids_conflicts: int = 0
    ocr_gpu_fallbacks: int = 0
    ocr_cache_hits: int = 0
    ocr_cache_misses: int = 0

    sources_classified: int = 0
    sources_unknown: int = 0
    assets_detected: int = 0
    locked_skipped: int = 0
    partial_skipped: int = 0
    review_required: int = 0

    durations: dict[str, float] = field(default_factory=dict)
    start_time: float = field(default_factory=time.perf_counter)

    @property
    def sources_total(self) -> int:
        """Backward-compatible alias for total ingested unique sources."""
        return self.sources_added

    @sources_total.setter
    def sources_total(self, val: int) -> None:
        self.sources_added = val

    @property
    def duplicates_skipped(self) -> int:
        """Backward-compatible alias for sources_duplicates."""
        return self.sources_duplicates

    @duplicates_skipped.setter
    def duplicates_skipped(self, val: int) -> None:
        self.sources_duplicates = val

    @contextmanager
    def timer(self, stage_name: str) -> Generator[None, None, None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            self.durations[stage_name] = self.durations.get(stage_name, 0.0) + elapsed

    @property
    def total_elapsed_seconds(self) -> float:
        return time.perf_counter() - self.start_time

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "         AUTO-CUT-NEXT EXECUTION SUMMARY",
            "=" * 50,
            f"Sources Seen:       {self.sources_seen}",
            f"Sources Added:      {self.sources_added}",
            f"Duplicates Skipped: {self.sources_duplicates}",
            f"Sources Forced:     {self.sources_forced}",
            f"Sources Failed:     {self.sources_failed}",
            f"Classified:         {self.sources_classified}",
            f"Classify Processed: {self.classify_processed}",
            f"Classify Cached:    {self.classify_cached}",
            f"Classify Auto:      {self.classify_auto}",
            f"Classify Review:    {self.classify_review}",
            f"Classify Unknown:   {self.classify_unknown}",
            f"Classify Errors:    {self.classify_errors}",
            f"Detect Processed:   {self.detect_sources_processed}",
            f"Detect Cached:      {self.detect_sources_cached}",
            f"Detect Deferred:    {self.detect_sources_deferred}",
            f"Detect No Grid:     {self.detect_sources_no_grid}",
            f"Detect Errors:      {self.detect_sources_errors}",
            f"Candidates Found:   {self.candidates_found}",
            f"Assets Created:     {self.assets_created}",
            f"Locked Found:       {self.locked_found}",
            f"Empty Found:        {self.empty_found}",
            f"Partial Found:      {self.partial_found}",
            f"Duplicates Found:   {self.duplicates_found}",

            f"Assets Detected:    {self.assets_detected}",
            f"Locked Skipped:     {self.locked_skipped}",
            f"Partial Skipped:    {self.partial_skipped}",
            f"Review Required:    {self.review_required}",
            f"OCR Guns Processed: {self.ocr_guns_processed}",
            f"OCR Guns Success:   {self.ocr_guns_success}",
            f"OCR Counters Found: {self.ocr_counters_found}",
            f"OCR UIDs Found:     {self.ocr_uids_found}",
            f"OCR Cache Hits:     {self.ocr_cache_hits}",
            "-" * 50,
        ]
        for stage, dur in self.durations.items():
            lines.append(f"{stage.capitalize():<20} {dur:.2f} s")
        lines.append(f"{'Total':<20} {self.total_elapsed_seconds:.2f} s")
        lines.append("=" * 50)
        return "\n".join(lines)
