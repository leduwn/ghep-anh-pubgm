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
            f"Unknown:            {self.sources_unknown}",
            f"Assets Detected:    {self.assets_detected}",
            f"Locked Skipped:     {self.locked_skipped}",
            f"Partial Skipped:    {self.partial_skipped}",
            f"Review Required:    {self.review_required}",
            "-" * 50,
        ]
        for stage, dur in self.durations.items():
            lines.append(f"{stage.capitalize():<20} {dur:.2f} s")
        lines.append(f"{'Total':<20} {self.total_elapsed_seconds:.2f} s")
        lines.append("=" * 50)
        return "\n".join(lines)
