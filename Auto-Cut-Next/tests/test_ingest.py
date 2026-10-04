"""Unit tests for image ingestion, validation, hashing, and security checks."""

import pytest
from core.constants import SourceStatus
from core.exceptions import PathTraversalError
from core.ingest import ImageIngestor, compute_sha256


def test_ingest_valid_1080p_image(sample_image_1080p, tmp_path):
    thumbs_dir = tmp_path / "thumbs"
    ingestor = ImageIngestor(thumb_max_dim=300)

    src = ingestor.ingest_file(sample_image_1080p, source_index=1, thumb_dir=thumbs_dir)
    assert src.status == SourceStatus.SUCCESS.value
    assert src.width == 1920
    assert src.height == 1080
    assert len(src.sha256) == 64
    assert src.error_message is None

    # Check thumbnail was generated
    thumb_file = thumbs_dir / f"{src.id}.jpg"
    assert thumb_file.is_file()


def test_ingest_pubg_image(sample_image_pubg):
    ingestor = ImageIngestor()
    src = ingestor.ingest_file(sample_image_pubg, source_index=2)
    assert src.status == SourceStatus.SUCCESS.value
    assert src.width == 2778
    assert src.height == 1284


def test_ingest_corrupt_image_gracefully_fails(sample_corrupt_file):
    ingestor = ImageIngestor()
    # Must not crash or raise uncaught error, but return FAILED SourceImage
    src = ingestor.ingest_file(sample_corrupt_file, source_index=3)
    assert src.status == SourceStatus.FAILED.value
    assert src.error_message is not None
    assert "Cannot decode" in src.error_message or "decode" in src.error_message.lower()


def test_ingest_nonexistent_file(tmp_path):
    ingestor = ImageIngestor()
    missing_file = tmp_path / "does_not_exist.png"
    src = ingestor.ingest_file(missing_file)
    assert src.status == SourceStatus.FAILED.value
    assert "not found" in src.error_message.lower()


def test_ingest_unsupported_extension(sample_text_file):
    ingestor = ImageIngestor()
    src = ingestor.ingest_file(sample_text_file)
    assert src.status == SourceStatus.FAILED.value
    assert "Unsupported image extension" in src.error_message


def test_path_traversal_detection(tmp_path, sample_image_1080p):
    restricted_root = tmp_path / "sandbox"
    restricted_root.mkdir()
    ingestor = ImageIngestor(allowed_root=restricted_root)

    # sample_image_1080p is in tmp_path, outside restricted_root
    with pytest.raises(PathTraversalError):
        ingestor.ingest_file(sample_image_1080p)


def test_scan_directory(tmp_path, sample_image_1080p, sample_image_pubg, sample_text_file):
    ingestor = ImageIngestor()
    found = ingestor.scan_directory(tmp_path)
    found_names = [f.name for f in found]
    assert sample_image_1080p.name in found_names
    assert sample_image_pubg.name in found_names
    # text file must not be scanned
    assert sample_text_file.name not in found_names


def test_sha256_reproducibility(sample_image_1080p):
    h1 = compute_sha256(sample_image_1080p)
    h2 = compute_sha256(sample_image_1080p)
    assert h1 == h2
    assert len(h1) == 64
