"""Metrics collection and execution profiling for Auto-Cut-Next."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class MetricsCollector:
    """Collects counters, durations and produces end-of-run performance reports."""
    sources_total: int = 0
    sources_classified: int = 0
    sources_unknown: int = 0
    assets_detected: int = 0
    duplicates_skipped: int = 0
    locked_skipped: int = 0
    partial_skipped: int = 0
    review_required: int = 0

    durations: dict[str, float] = field(default_factory=dict)
    start_time: float = field(default_factory=time.perf_counter)

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
            f"Sources:            {self.sources_total}",
            f"Classified:         {self.sources_classified}",
            f"Unknown:            {self.sources_unknown}",
            f"Assets:             {self.assets_detected}",
            f"Duplicates:         {self.duplicates_skipped}",
            f"Locked skipped:     {self.locked_skipped}",
            f"Partial skipped:    {self.partial_skipped}",
            f"Review:             {self.review_required}",
            "-" * 50,
        ]
        for stage, dur in self.durations.items():
            lines.append(f"{stage.capitalize():<20} {dur:.2f} s")
        lines.append(f"{'Total':<20} {self.total_elapsed_seconds:.2f} s")
        lines.append("=" * 50)
        return "\n".join(lines)
