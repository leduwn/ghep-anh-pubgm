"""Unit tests for metrics collection and stopwatch profiling."""

import time
from core.metrics import MetricsCollector


def test_metrics_collector():
    mc = MetricsCollector()
    mc.sources_total = 10
    mc.sources_classified = 9
    mc.sources_unknown = 1
    mc.assets_detected = 25
    mc.duplicates_skipped = 2
    mc.locked_skipped = 1
    mc.partial_skipped = 0
    mc.review_required = 3

    with mc.timer("ingest"):
        time.sleep(0.01)

    with mc.timer("classify"):
        time.sleep(0.01)

    assert "ingest" in mc.durations
    assert mc.durations["ingest"] > 0.005

    summary = mc.summary()
    assert "Sources:            10" in summary
    assert "Classified:         9" in summary
    assert "Assets:             25" in summary
    assert "Ingest" in summary
