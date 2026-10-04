"""Unit tests for metrics collection and stopwatch profiling."""

import time
from core.metrics import MetricsCollector


def test_metrics_collector():
    mc = MetricsCollector()
    mc.sources_seen = 15
    mc.sources_added = 10
    mc.sources_duplicates = 2
    mc.sources_forced = 1
    mc.sources_failed = 2

    mc.sources_classified = 9
    mc.sources_unknown = 1
    mc.assets_detected = 25
    mc.locked_skipped = 1
    mc.partial_skipped = 0
    mc.review_required = 3

    assert mc.sources_total == 10
    assert mc.duplicates_skipped == 2

    with mc.timer("ingest"):
        time.sleep(0.01)

    with mc.timer("classify"):
        time.sleep(0.01)

    assert "ingest" in mc.durations
    assert mc.durations["ingest"] > 0.005

    summary = mc.summary()
    assert "Sources Seen:       15" in summary
    assert "Sources Added:      10" in summary
    assert "Duplicates Skipped: 2" in summary
    assert "Sources Forced:     1" in summary
    assert "Sources Failed:     2" in summary
    assert "Classified:         9" in summary
    assert "Assets Detected:    25" in summary
    assert "Ingest" in summary
