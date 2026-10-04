"""Unit tests for structured stage logging."""

from core.constants import Stage
from core.logging import StageLogger


def test_stage_logger_creates_file_and_logs(tmp_path):
    log_dir = tmp_path / "logs"
    logger = StageLogger(log_dir=log_dir, log_filename="test.log", console=False)

    logger.info("Starting ingest", stage=Stage.INGEST, account="ACC01", source="img.png", status="INIT")
    logger.warning("Low confidence card", stage=Stage.DETECT, account="ACC01", source="img.png", status="WARN", duration_ms=45.2)

    log_file = log_dir / "test.log"
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")

    assert "[INFO ]" in content
    assert "[INGEST   ]" in content
    assert "[ACC01]" in content
    assert "Starting ingest" in content

    assert "[WARN ]" in content or "[WARNI]" in content or "WARN" in content
    assert "[DETECT   ]" in content
    assert "(45.2ms)" in content



def test_stage_logger_isolation(tmp_path):
    dir_a = tmp_path / "ws_a" / "logs"
    dir_b = tmp_path / "ws_b" / "logs"

    logger_a = StageLogger(log_dir=dir_a, log_filename="run.log", console=False)
    logger_b = StageLogger(log_dir=dir_b, log_filename="run.log", console=False)

    logger_a.info("EVENT_ALPHA", account="ACC_A")
    logger_b.info("EVENT_BETA", account="ACC_B")

    logger_a.close()
    logger_b.close()

    content_a = (dir_a / "run.log").read_text(encoding="utf-8")
    content_b = (dir_b / "run.log").read_text(encoding="utf-8")

    assert "EVENT_ALPHA" in content_a
    assert "EVENT_BETA" not in content_a
    assert "EVENT_BETA" in content_b
    assert "EVENT_ALPHA" not in content_b


def test_stage_logger_context_manager(tmp_path):
    log_dir = tmp_path / "ctx_logs"
    with StageLogger(log_dir=log_dir, log_filename="ctx.log", console=False) as logger:
        logger.info("INSIDE_CTX")
    content = (log_dir / "ctx.log").read_text(encoding="utf-8")
    assert "INSIDE_CTX" in content

