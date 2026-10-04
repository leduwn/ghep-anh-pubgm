"""Image ingest pipeline: file validation, unicode-safe decoding, hashing and thumbnails."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
from PIL import Image

from .constants import (
    SUPPORTED_IMAGE_EXTENSIONS,
    DEFAULT_THUMBNAIL_MAX_DIMENSION,
    SourceStatus,
)
from .exceptions import CorruptImageError, PathTraversalError
from .models import SourceImage


def compute_sha256(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
    """Stream-compute SHA-256 hash of a file without loading entire file into memory."""
    hasher = hashlib.sha256()
    path = Path(file_path).resolve()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_image_cv2(file_path: Union[str, Path]) -> Optional[np.ndarray]:
    """Unicode-safe image reading via numpy fromfile and cv2.imdecode with Pillow fallback."""
    path = Path(file_path).resolve()
    if not path.is_file():
        return None
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data is None or len(data) == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        try:
            with Image.open(path) as pil_img:
                rgb = pil_img.convert("RGB")
                return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        except Exception:
            return None


def write_image_cv2(file_path: Union[str, Path], image: np.ndarray, ext: str = ".png") -> bool:
    """Unicode-safe image writing via cv2.imencode and tofile."""
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    extension = path.suffix or ext
    try:
        success, encoded = cv2.imencode(extension, image)
        if success and encoded is not None:
            encoded.tofile(str(path))
            return True
        return False
    except Exception:
        return False


class ImageIngestor:
    """Validates, hashes, inspects dimensions and produces thumbnails for screenshots."""

    def __init__(
        self,
        allowed_root: Optional[Union[str, Path]] = None,
        thumb_max_dim: int = DEFAULT_THUMBNAIL_MAX_DIMENSION,
    ):
        self.allowed_root = Path(allowed_root).resolve() if allowed_root else None
        self.thumb_max_dim = thumb_max_dim

    def validate_path_safety(self, target_path: Union[str, Path]) -> Path:
        resolved = Path(target_path).resolve()
        if self.allowed_root:
            root_resolved = Path(self.allowed_root).resolve()
            if not resolved.is_relative_to(root_resolved):
                raise PathTraversalError(f"Path '{resolved}' escapes allowed directory '{root_resolved}'")
        return resolved

    def ingest_file(
        self,
        file_path: Union[str, Path],
        source_index: int = 0,
        thumb_dir: Optional[Union[str, Path]] = None,
    ) -> SourceImage:
        """Ingests a single file, calculates sha256, validates image, and creates thumbnail."""
        resolved = self.validate_path_safety(file_path)
        sha256_hash = ""
        source_id = ""
        mtime = 0.0

        if not resolved.is_file():
            return SourceImage(
                id=f"src_{source_index:04d}",
                path=str(resolved),
                sha256="",
                filename=resolved.name,
                width=0,
                height=0,
                mtime=0.0,
                source_index=source_index,
                status=SourceStatus.FAILED.value,
                error_message=f"File not found: {resolved}",
            )

        if resolved.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return SourceImage(
                id=f"src_{source_index:04d}",
                path=str(resolved),
                sha256="",
                filename=resolved.name,
                width=0,
                height=0,
                mtime=resolved.stat().st_mtime if resolved.exists() else 0.0,
                source_index=source_index,
                status=SourceStatus.FAILED.value,
                error_message=f"Unsupported image extension: {resolved.suffix}",
            )

        try:
            mtime = resolved.stat().st_mtime
            sha256_hash = compute_sha256(resolved)
            source_id = sha256_hash[:16]

            img = read_image_cv2(resolved)
            if img is None:
                raise CorruptImageError(f"Cannot decode image data from '{resolved.name}'")

            h, w = img.shape[:2]
            if w < 10 or h < 10 or w > 20000 or h > 20000:
                raise CorruptImageError(f"Invalid dimensions {w}x{h} for '{resolved.name}'")

            if thumb_dir:
                td = Path(thumb_dir).resolve()
                td.mkdir(parents=True, exist_ok=True)
                thumb_path = td / f"{source_id}.jpg"
                if not thumb_path.is_file():
                    scale = min(self.thumb_max_dim / float(max(w, h)), 1.0)
                    tw = max(1, round(w * scale))
                    th = max(1, round(h * scale))
                    thumb = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
                    write_image_cv2(thumb_path, thumb, ext=".jpg")

            return SourceImage(
                id=source_id,
                path=str(resolved),
                sha256=sha256_hash,
                filename=resolved.name,
                width=w,
                height=h,
                mtime=mtime,
                source_index=source_index,
                status=SourceStatus.SUCCESS.value,
            )

        except Exception as exc:
            return SourceImage(
                id=source_id or f"src_{source_index:04d}",
                path=str(resolved),
                sha256=sha256_hash,
                filename=resolved.name,
                width=0,
                height=0,
                mtime=mtime,
                source_index=source_index,
                status=SourceStatus.FAILED.value,
                error_message=str(exc),
            )

    def scan_directory(
        self,
        directory_path: Union[str, Path],
        recursive: bool = False,
        enforce_root: bool = True,
    ) -> list[Path]:
        """Collects all valid image files in a directory sorted by name, enforcing sandbox."""
        dir_path = self.validate_path_safety(directory_path)
        if not dir_path.is_dir():
            return []

        effective_root = self.allowed_root or (dir_path.resolve() if enforce_root else None)

        pattern = "**/*" if recursive else "*"
        candidates = []
        for p in dir_path.glob(pattern):
            if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                if effective_root:
                    resolved = p.resolve()
                    if not resolved.is_relative_to(effective_root):
                        # Symlink / junction points outside sandbox root -> reject
                        continue
                candidates.append(p)
        return sorted(candidates, key=lambda x: x.name.lower())

