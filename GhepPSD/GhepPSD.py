#!/usr/bin/env python3
"""Ghép ảnh account thành preview và PSD nhiều layer qua Photoshop.

Mỗi file ảnh con đầu vào được giữ nguyên và đặt thành một Smart Object độc lập
để có thể chọn, thay hoặc kéo riêng trong Photoshop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageStat

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from PIL import ImageTk
except ImportError:  # pragma: no cover - chỉ xảy ra trên Python không có Tk.
    tk = None
    filedialog = messagebox = ttk = None
    ImageTk = None

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_PATHS = {
    "source_project_root": "../Cắt",
    "input_dir": "../Cắt/input",
    "output_dir": "../Cắt/output",
    "results_dir": "KetQua",
    "temp_dir": "Temp",
    "forms_dir": "forms",
    "photoshop_script": "photoshop/photoshop_compose.jsx",
    "photoshop_bridge": "photoshop/photoshop_bridge.ps1",
    "label_library": "assets/1 cat chu.psd",
    "dienlv_root": "../DienLV/standalone",
}
PATH_CONFIG_LABELS = {
    "source_project_root": "Thư mục project Cắt",
    "input_dir": "Thư mục ảnh input",
    "output_dir": "Thư mục ảnh output theo acc",
    "results_dir": "Thư mục kết quả PSD",
    "temp_dir": "Thư mục tạm",
    "forms_dir": "Thư mục form",
    "photoshop_script": "Script Photoshop JSX",
    "photoshop_bridge": "Cầu nối Photoshop",
    "label_library": "File kho chữ/nhãn",
    "dienlv_root": "Thư mục súng DienLV",
}
PATH_CONFIG_FILE_KEYS = {"photoshop_script", "photoshop_bridge", "label_library"}


def _load_path_config() -> dict[str, str]:
    if not CONFIG_PATH.is_file():
        return dict(DEFAULT_PATHS)
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        configured = loaded.get("paths", loaded)
        return {key: str(configured.get(key, value)) for key, value in DEFAULT_PATHS.items()}
    except Exception as exc:
        raise RuntimeError(f"File cấu hình lỗi {CONFIG_PATH}: {exc}") from exc


def _configured_path(value: str) -> Path:
    expanded = Path(os.path.expandvars(value)).expanduser()
    if not expanded.is_absolute():
        expanded = PROJECT_ROOT / expanded
    return expanded.resolve()


def reload_path_config() -> dict[str, str]:
    global _PATHS, SOURCE_PROJECT_ROOT, INPUT_DIR, OUTPUT_DIR
    global RESULTS_DIR, TEMP_DIR, FORMS_DIR, PHOTOSHOP_SCRIPT
    global PHOTOSHOP_BRIDGE, PHOTOSHOP_DIR, LABEL_LIBRARY, DIENLV_ROOT

    _PATHS = _load_path_config()
    SOURCE_PROJECT_ROOT = _configured_path(_PATHS["source_project_root"])
    INPUT_DIR = _configured_path(_PATHS["input_dir"])
    OUTPUT_DIR = _configured_path(_PATHS["output_dir"])
    RESULTS_DIR = _configured_path(_PATHS["results_dir"])
    TEMP_DIR = _configured_path(_PATHS["temp_dir"])
    FORMS_DIR = _configured_path(_PATHS["forms_dir"])
    PHOTOSHOP_SCRIPT = _configured_path(_PATHS["photoshop_script"])
    PHOTOSHOP_BRIDGE = _configured_path(_PATHS["photoshop_bridge"])
    PHOTOSHOP_DIR = PHOTOSHOP_SCRIPT.parent
    LABEL_LIBRARY = _configured_path(_PATHS["label_library"])
    DIENLV_ROOT = _configured_path(_PATHS["dienlv_root"])
    if str(SOURCE_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_PROJECT_ROOT))
    return dict(_PATHS)


def save_path_config(paths: dict[str, str]) -> None:
    """Lưu cấu hình dạng dễ mang sang máy khác rồi áp dụng ngay."""
    cleaned = {
        key: str(paths.get(key, DEFAULT_PATHS[key])).strip()
        for key in DEFAULT_PATHS
    }
    missing = [PATH_CONFIG_LABELS[key] for key, value in cleaned.items() if not value]
    if missing:
        raise ComposeError("Không được để trống: " + ", ".join(missing))
    payload = {
        "version": 1,
        "_huong_dan": (
            "Đường dẫn tương đối được tính từ thư mục GhepPSD. "
            "Có thể sửa trực tiếp tại đây hoặc bằng cửa sổ Cấu hình trong tool."
        ),
        "paths": cleaned,
    }
    CONFIG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reload_path_config()


_PATHS: dict[str, str] = {}
reload_path_config()

if str(SOURCE_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_PROJECT_ROOT))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
CATEGORY_ORDER = (
    "sung", "xe", "tp", "do", "mu", "balo", "matna",
    "luudan", "du", "item", "hd",
)
LEFT_SMALL_CATEGORIES = ("luudan", "du", "item", "hd")
INVENTORY_CATEGORIES = ("do", "mu", "balo", "matna")
INVENTORY_GROUPS = {
    "do": "40_INVENTORY_DO",
    "mu": "41_INVENTORY_MU",
    "balo": "42_INVENTORY_BALO",
    "matna": "43_INVENTORY_MATNA",
}
OUTFIT_GRID_BY_COUNT = {
    12: (3, 4),
    15: (3, 5),
    20: (4, 5),
    36: (6, 6),
}
OUTFIT_LABEL_SOURCE = PROJECT_ROOT / "assets" / "1 cat chu.psd"
OUTFIT_LABEL_DIR = PROJECT_ROOT / "assets" / "outfit_labels"
OUTFIT_LABEL_EXPORT_SCRIPT = PROJECT_ROOT / "photoshop" / "export_outfit_labels.jsx"
OUTFIT_CHOICES = {
    "normal": "Trang phục thường",
    "star_7": "Thánh giáp 7★",
    "star_6": "Thánh giáp 6★",
    "star_5": "Thánh giáp 5★",
    "star_4": "Thánh giáp 4★",
    "star_3": "Thánh giáp 3★",
    "star_2": "Thánh giáp 2★",
    "star_1": "Thánh giáp 1★",
    "vip": "Thần giáp VIP",
}
VEHICLE_LABEL_DIR = PROJECT_ROOT / "assets" / "vehicle_labels"
VEHICLE_LABEL_EXPORT_SCRIPT = PROJECT_ROOT / "photoshop" / "export_vehicle_labels.jsx"
VEHICLE_CHOICES = {
    "none": "Không nhãn",
    "ticket_3": "3VÉ",
    "ticket_3_2cmt": "3VÉ - 2CMT",
    "ticket_1_2cmt": "1VÉ - 2CMT",
    "ticket_1_2c": "1VÉ - 2C",
    "ticket_1_4c": "1VÉ - 4C",
    "ticket_3_2c": "3VÉ - 2C",
    "ticket_3_4c": "3VÉ - 4C",
    "ticket_1_mt": "1VÉ - MT",
    "ticket_3_mt": "3VÉ - MT",
    "vip": "VIP",
}


class ComposeError(RuntimeError):
    """Lỗi có thể hiển thị trực tiếp cho người dùng."""


@dataclass(frozen=True)
class SourceImage:
    path: Path
    category: str
    width: int
    height: int


@dataclass(frozen=True)
class DienLVGunSet:
    code: str
    items: tuple[SourceImage, ...]
    columns: int
    rows: int
    reference_path: Path


@dataclass(frozen=True)
class RunFiles:
    psd: Path
    png: Path
    preview: Path
    layout: Path


_DIENLV_GUN_CACHE: dict[str, DienLVGunSet] = {}


def natural_key(value: str | Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", str(value))]


def validate_account_id(value: str) -> str:
    account = str(value or "").strip()
    if not account:
        raise ComposeError("Vui lòng nhập mã acc.")
    if account in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', account):
        raise ComposeError("Mã acc chứa ký tự không hợp lệ.")
    if account.endswith((".", " ")):
        raise ComposeError("Mã acc không được kết thúc bằng dấu chấm hoặc khoảng trắng.")
    return account


def image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception as exc:
        raise ComposeError(f"Không đọc được ảnh {path.name}: {exc}") from exc


def _has_red_vehicle_background(path: Path) -> bool:
    """Nhận diện thẻ xe nền đỏ bằng màu nền mép ảnh, bỏ qua màu chiếc xe."""
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((120, 50), Image.Resampling.BILINEAR)
            width, height = image.size
            pixels = []
            for y in range(height):
                for x in range(width):
                    if y < height // 4 or y >= height * 4 // 5 or x < width // 8 or x >= width * 7 // 8:
                        pixels.append(image.getpixel((x, y)))
    except Exception:
        return False
    if not pixels:
        return False
    channels = list(zip(*pixels))
    red, green, blue = (sorted(channel)[len(channel) // 2] for channel in channels)
    return red >= 100 and red - green >= 40 and red - blue >= 35


def vehicle_ticket_priority(choice: str) -> int:
    choice = str(choice or "none").strip()
    if choice.startswith("ticket_3"):
        return 0  # 3 vé đứng đầu tiên
    if choice.startswith("ticket_1") or choice.startswith("ticket_"):
        return 1  # 1 vé đứng sau
    if choice == "vip":
        return 2  # vip đứng sau 1 vé
    return 3      # không có tag thì đứng cuối


def sorted_vehicles(items: Iterable[SourceImage], choices: dict[str, str] | None = None) -> list[SourceImage]:
    items_list = list(items)
    choices_dict = choices or {}
    def key(index_item: tuple[int, SourceImage]) -> tuple[int, int, Any]:
        index, item = index_item
        choice = choices_dict.get(item.path.name, "none")
        priority = vehicle_ticket_priority(choice)
        is_red = 0 if _has_red_vehicle_background(item.path) else 1
        return priority, is_red, natural_key(item.path.name)
    return [item for _, item in sorted(enumerate(items_list), key=key)]


def sort_vehicle_images(items: Iterable[SourceImage]) -> list[SourceImage]:
    return sorted_vehicles(items)


def _dienlv_source_paths(code: str, root: Path | None = None) -> tuple[Path, list[Path], Path]:
    code = validate_account_id(code)
    candidate_folders: list[Path] = []
    if root is not None:
        candidate_folders.append(root / code)
        if not (root / code / "anhle").is_dir() and root.parent.is_dir() and (root.parent / code / "anhle").is_dir():
            candidate_folders.append(root.parent / code)
        elif not (root / code / "anhle").is_dir() and (root / "standalone" / code / "anhle").is_dir():
            candidate_folders.append(root / "standalone" / code)
    else:
        if OUTPUT_DIR.is_dir():
            candidate_folders.append(OUTPUT_DIR / code)
        tool_sung_out = SOURCE_PROJECT_ROOT / "tool" / "Cắt Súng" / "output"
        if tool_sung_out.is_dir():
            candidate_folders.append(tool_sung_out / code)
        candidate_folders.append(DIENLV_ROOT / code)
        if DIENLV_ROOT.parent.is_dir() and DIENLV_ROOT.name == "standalone":
            candidate_folders.append(DIENLV_ROOT.parent / code)
        if (DIENLV_ROOT / "standalone").is_dir():
            candidate_folders.append(DIENLV_ROOT / "standalone" / code)

    folder: Path | None = None
    for cand in candidate_folders:
        if (cand / "anhle").is_dir():
            folder = cand
            break

    if folder is None:
        folder = (root or DIENLV_ROOT) / code

    source_dir = folder / "anhle"
    if not source_dir.is_dir():
        raise ComposeError(f"Mã súng {code} không có thư mục anhle: {source_dir}")
    images = sorted(
        (path for path in source_dir.iterdir()
         if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: natural_key(path.name),
    )
    if not images:
        raise ComposeError(f"Thư mục {source_dir} chưa có ảnh súng lẻ.")
    references = [
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
        and path.stem.casefold() == code.casefold()
    ]
    if not references:
        # Dự phòng: tìm file PNG bất kỳ trong folder (ngoại trừ xem_truoc)
        references = [
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".png"
            and not path.stem.lower().startswith("xem_truoc")
        ]
    if not references:
        raise ComposeError(f"Mã súng {code} thiếu ảnh ghép tham chiếu {code}.png.")
    return folder, images, references[0]


def _order_from_dienlv_psd(folder: Path, images: list[Path]) -> tuple[list[Path], int, int] | None:
    """Đọc tên và tọa độ layer do DienLV đã lưu, không đọc lại nội dung pixel."""
    psd_path = next(
        (path for path in folder.iterdir()
         if path.is_file() and path.suffix.lower() == ".psd"
         and path.stem.casefold() == folder.name.casefold()),
        None,
    )
    if psd_path is None:
        return None
    try:
        import pytoshop

        with psd_path.open("rb") as stream:
            psd = pytoshop.read(stream)
        records = []
        for layer in psd.layer_and_mask_info.layer_info.layer_records:
            name = str(layer.name).rstrip("\x00")
            match = re.match(r"^gun_\d+_(.+)$", name, flags=re.IGNORECASE)
            if match:
                records.append((int(layer.left), int(layer.top), match.group(1).casefold()))
    except Exception:
        return None
    if not records:
        return None

    by_stem = {path.stem.casefold(): path for path in images}
    ordered = [
        by_stem[stem]
        for _, _, stem in sorted(records, key=lambda item: (item[1], item[0]))
        if stem in by_stem
    ]
    # Có thể PSD cũ chứa một ảnh đặc biệt đã bị xóa khỏi anhle. Ta chỉ bỏ ảnh
    # thiếu, nhưng mọi ảnh còn tồn tại phải tìm thấy đúng layer của nó.
    if len(ordered) != len(images) or len(set(ordered)) != len(images):
        return None
    columns = len({left for left, _, _ in records})
    rows = len({top for _, top, _ in records})
    return ordered, max(1, columns), max(1, rows)


def list_dienlv_codes(root: Path | None = None) -> list[dict[str, Any]]:
    """Liệt kê nhanh các bộ súng để đưa lên giao diện, chưa chạy ghép ảnh."""
    result: list[dict[str, Any]] = []
    seen_codes = set()
    if root is not None:
        candidate_roots = [root] if root.is_dir() else []
    else:
        candidate_roots = []
        if OUTPUT_DIR.is_dir():
            candidate_roots.append(OUTPUT_DIR)
        tool_sung_out = SOURCE_PROJECT_ROOT / "tool" / "Cắt Súng" / "output"
        if tool_sung_out.is_dir():
            candidate_roots.append(tool_sung_out)
        if DIENLV_ROOT.is_dir():
            candidate_roots.append(DIENLV_ROOT)
        if DIENLV_ROOT.parent.is_dir() and DIENLV_ROOT.name == "standalone":
            candidate_roots.append(DIENLV_ROOT.parent)
        elif (DIENLV_ROOT / "standalone").is_dir():
            candidate_roots.append(DIENLV_ROOT / "standalone")

    for r in candidate_roots:
        for folder in sorted((path for path in r.iterdir() if path.is_dir()), key=lambda path: natural_key(path.name)):
            if folder.name.casefold() in seen_codes or folder.name in {"standalone", "assets", "input", "anhrac", "Temp"}:
                continue
            try:
                _, images, reference = _dienlv_source_paths(folder.name, r)
                psd_layout = _order_from_dienlv_psd(folder, images)
                if psd_layout:
                    _, columns, rows = psd_layout
                else:
                    reference_w, reference_h = image_size(reference)
                    widths = sorted(image_size(path)[0] for path in images)
                    heights = sorted(image_size(path)[1] for path in images)
                    median_width = widths[len(widths) // 2]
                    median_height = heights[len(heights) // 2]
                    columns = max(1, round(reference_w / max(1, median_width)))
                    rows = max(1, round(reference_h / max(1, median_height)))
            except ComposeError:
                continue
            seen_codes.add(folder.name.casefold())
            result.append({
                "code": folder.name,
                "count": len(images),
                "columns": columns,
                "rows": rows,
            })
    return result


def _cv_read(path: Path) -> Any:
    try:
        import cv2
        import numpy as np

        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as exc:
        raise ComposeError(
            "Không đọc được thứ tự súng DienLV. Máy cần OpenCV (cv2) để đối chiếu ảnh."
        ) from exc
    if image is None:
        raise ComposeError(f"OpenCV không đọc được ảnh: {path}")
    return image


def _match_dienlv_order(images: list[Path], reference: Path, columns: int, cell_width: int) -> list[Path]:
    """Khôi phục vị trí ảnh lẻ bằng cách đối chiếu với PNG DienLV đã ghép.

    Tên IMG trong anhle là tên ảnh chụp ban đầu, không còn phản ánh thứ tự
    level sau khi DienLV sắp xếp. PNG cạnh file PSD là nguồn đáng tin cậy nhất.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise ComposeError(
            "Thiếu bộ đọc PSD DienLV và OpenCV nên chưa xác định được thứ tự súng."
        ) from exc

    canvas = _cv_read(reference)
    if canvas.shape[1] != columns * cell_width:
        raise ComposeError(
            f"Ảnh tham chiếu {reference.name} có chiều rộng không khớp các ảnh trong anhle."
        )

    scale = 0.25
    column_images = [canvas[:, col * cell_width:(col + 1) * cell_width] for col in range(columns)]
    small_columns = [
        cv2.resize(
            image,
            (max(1, round(cell_width * scale)), max(1, round(image.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
        for image in column_images
    ]
    matched: list[tuple[int, int, float, Path]] = []
    for path in images:
        source = _cv_read(path)
        normalized_height = max(1, round(source.shape[0] * cell_width / source.shape[1]))
        best: tuple[float, int, int] | None = None
        for column_index, (column_image, small_column) in enumerate(zip(column_images, small_columns)):
            for target_height in range(max(1, normalized_height - 5), normalized_height + 6):
                small_template = cv2.resize(
                    source,
                    (small_column.shape[1], max(1, round(target_height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
                if small_template.shape[0] > small_column.shape[0]:
                    continue
                score_map = cv2.matchTemplate(small_column, small_template, cv2.TM_SQDIFF_NORMED)
                _, _, rough_location, _ = cv2.minMaxLoc(score_map)
                rough_y = round(rough_location[1] / scale)
                normalized = cv2.resize(source, (cell_width, target_height), interpolation=cv2.INTER_AREA)
                y_start = max(0, rough_y - 7)
                y_end = min(column_image.shape[0] - target_height, rough_y + 7)
                for y in range(y_start, y_end + 1):
                    crop = column_image[y:y + target_height]
                    difference = float(np.mean(np.abs(crop.astype(np.int16) - normalized.astype(np.int16))))
                    candidate = (difference, column_index, y)
                    if best is None or candidate < best:
                        best = candidate
        if best is None:
            raise ComposeError(f"Không tìm được vị trí của ảnh súng {path.name}.")
        matched.append((best[1], best[2], best[0], path))

    locations = [(column, y) for column, y, _, _ in matched]
    worst_score = max(score for _, _, score, _ in matched)
    if len(set(locations)) != len(locations) or worst_score > 12.0:
        raise ComposeError(
            f"Ảnh trong anhle của {reference.stem} không còn khớp ảnh ghép tham chiếu. "
            "Hãy chạy lại DienLV hoặc giữ đúng bộ ảnh lẻ đi kèm."
        )
    # place_grid dùng thứ tự theo từng hàng: trái -> phải, trên -> dưới.
    return [path for column, y, _, path in sorted(matched, key=lambda item: (item[1], item[0]))]


def load_dienlv_guns(code: str, root: Path | None = None) -> DienLVGunSet:
    root = DIENLV_ROOT if root is None else root
    normalized_code = validate_account_id(code)
    cache_key = str((root / normalized_code).resolve()).casefold()
    if cache_key in _DIENLV_GUN_CACHE:
        return _DIENLV_GUN_CACHE[cache_key]

    folder, paths, reference = _dienlv_source_paths(normalized_code, root)
    widths = sorted(image_size(path)[0] for path in paths)
    cell_width = widths[len(widths) // 2]
    psd_layout = _order_from_dienlv_psd(folder, paths)
    if psd_layout:
        ordered_paths, columns, rows = psd_layout
    else:
        reference_width, reference_height = image_size(reference)
        columns = max(1, round(reference_width / max(1, cell_width)))
        ordered_paths = _match_dienlv_order(paths, reference, columns, cell_width)
        heights = sorted(image_size(path)[1] for path in paths)
        rows = max(1, round(reference_height / max(1, heights[len(heights) // 2])))
    items = tuple(
        SourceImage(path.resolve(), "sung", *image_size(path))
        for path in ordered_paths
    )
    result = DienLVGunSet(
        code=normalized_code,
        items=items,
        columns=columns,
        rows=rows,
        reference_path=reference.resolve(),
    )
    _DIENLV_GUN_CACHE[cache_key] = result
    return result


def load_forms() -> dict[str, dict[str, Any]]:
    forms: dict[str, dict[str, Any]] = {}
    for path in sorted(FORMS_DIR.glob("*.json"), key=natural_key):
        try:
            form = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ComposeError(f"Form lỗi {path.name}: {exc}") from exc
        if int(form.get("version", 0)) != 1 or not form.get("id"):
            raise ComposeError(f"Form {path.name} thiếu version=1 hoặc id.")
        form["_path"] = str(path)
        forms[str(form["id"])] = form
    if not forms:
        raise ComposeError(f"Không có form trong {FORMS_DIR}")
    return forms


def scan_account_output(account: str, output_root: Path | None = None) -> dict[str, list[SourceImage]]:
    account = validate_account_id(account)
    output_root = OUTPUT_DIR if output_root is None else output_root
    folder = output_root / account
    if not folder.is_dir():
        raise ComposeError(f"Không tìm thấy thư mục kết quả: {folder}")

    result = {category: [] for category in CATEGORY_ORDER}
    for path in sorted(folder.iterdir(), key=lambda p: natural_key(p.name)):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        category = path.stem.split("_", 1)[0].lower()
        if category not in result:
            continue
        width, height = image_size(path)
        result[category].append(SourceImage(path.resolve(), category, width, height))

    if not any(result.values()):
        raise ComposeError(
            f"{folder} chưa có ảnh con. Hãy chạy phần cắt hoặc kiểm tra lại mã acc."
        )
    result["xe"] = sort_vehicle_images(result["xe"])
    return result


def outfit_metadata_path(account: str) -> Path:
    return RESULTS_DIR / validate_account_id(account) / "trang_phuc.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_outfit_choices(account: str, items: list[SourceImage]) -> dict[str, str]:
    path = outfit_metadata_path(account)
    try:
        saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        records = saved.get("items", {}) if saved.get("version") == 1 else {}
    except (OSError, ValueError, TypeError, AttributeError):
        records = {}
    result: dict[str, str] = {}
    for item in items:
        record = records.get(item.path.name, {})
        if (isinstance(record, dict) and record.get("sha256") == _file_sha256(item.path)
                and record.get("choice") in OUTFIT_CHOICES):
            result[item.path.name] = record["choice"]
        else:
            result[item.path.name] = "normal"
    return result


def save_outfit_choices(account: str, items: list[SourceImage], choices: dict[str, str]) -> Path:
    path = outfit_metadata_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "items": {
            item.path.name: {
                "sha256": _file_sha256(item.path),
                "choice": choices.get(item.path.name, "normal"),
            }
            for item in items
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path

def calculate_gun_columns_and_rows(total_guns: int) -> tuple[int, int]:
    """Tự động chia cột súng sao cho mỗi cột có từ 8 - 15 súng, chia đều để tránh dư / trống."""
    if total_guns <= 0:
        return 1, 0
    if total_guns <= 15:
        return 1, total_guns
    best_cols = 2
    best_rows = math.ceil(total_guns / 2)
    best_score = float("inf")
    max_cols = max(2, math.ceil(total_guns / 8))
    for cols in range(2, max_cols + 2):
        rows = math.ceil(total_guns / cols)
        remainder = (cols * rows) - total_guns
        in_range = (8 <= rows <= 15)
        range_penalty = 0 if in_range else (abs(rows - 11) * 100)
        empty_penalty = remainder * 20
        balance_penalty = abs(rows - 11)
        score = range_penalty + empty_penalty + balance_penalty
        if score < best_score:
            best_score = score
            best_cols = cols
            best_rows = rows
    return best_cols, best_rows


def gun_metadata_path(account: str) -> Path:
    return RESULTS_DIR / validate_account_id(account) / "sung.json"


def load_gun_choices(account: str, items: list[SourceImage]) -> tuple[set[str], int | None]:
    path = gun_metadata_path(account)
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                excluded = set(data.get("excluded", []))
                columns = data.get("columns")
                return excluded, columns
    except Exception:
        pass
    return set(), None


def save_gun_choices(account: str, excluded: set[str], columns: int) -> Path:
    path = gun_metadata_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "columns": columns,
        "excluded": sorted(list(excluded)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def sorted_outfits(items: list[SourceImage], choices: dict[str, str]) -> list[SourceImage]:
    def key(index_item: tuple[int, SourceImage]) -> tuple[int, int, int]:
        index, item = index_item
        choice = choices.get(item.path.name, "normal")
        if choice.startswith("star_"):
            return 0, -int(choice.split("_", 1)[1]), index
        if choice == "vip":
            return 1, 0, index
        return 2, 0, index
    return [item for _, item in sorted(enumerate(items), key=key)]


def ensure_outfit_label_assets() -> None:
    if not OUTFIT_LABEL_SOURCE.is_file() or not OUTFIT_LABEL_EXPORT_SCRIPT.is_file():
        raise ComposeError("Thiếu file nhãn hoặc script xuất nhãn trong GhepPSD\\assets.")
    expected = [OUTFIT_LABEL_DIR / f"star_{number}.png" for number in range(1, 8)]
    expected.append(OUTFIT_LABEL_DIR / "vip.png")
    latest_source = max(OUTFIT_LABEL_SOURCE.stat().st_mtime_ns,
                        OUTFIT_LABEL_EXPORT_SCRIPT.stat().st_mtime_ns)
    if all(path.is_file() and path.stat().st_mtime_ns >= latest_source for path in expected):
        return
    OUTFIT_LABEL_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = TEMP_DIR / "jobs" / f"export_outfit_labels_{uuid.uuid4().hex}.jsx"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "AUTO_GHEP_LABEL_SOURCE": OUTFIT_LABEL_SOURCE,
        "AUTO_GHEP_LABEL_DIR": OUTFIT_LABEL_DIR,
    }
    lines = ["#target photoshop"]
    for name, path in values.items():
        lines.append(f"var {name} = {json.dumps(str(path).replace(chr(92), '/'))};")
    lines.append(f"$.evalFile(File({json.dumps(str(OUTFIT_LABEL_EXPORT_SCRIPT).replace(chr(92), '/'))}));")
    wrapper.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(PHOTOSHOP_BRIDGE), "-ScriptPath", str(wrapper)],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ComposeError("Photoshop xuất nhãn sao/VIP quá 3 phút.") from exc
    finally:
        wrapper.unlink(missing_ok=True)
    if completed.returncode != 0 or not all(
        path.is_file() and path.stat().st_mtime_ns >= latest_source for path in expected
    ):
        detail = (completed.stderr or completed.stdout or "Thiếu ảnh nhãn đầu ra").strip()
        raise ComposeError(f"Không xuất được nhãn sao/VIP từ PSD: {detail}")


def vehicle_metadata_path(account: str) -> Path:
    return RESULTS_DIR / validate_account_id(account) / "ve_xe.json"


def load_vehicle_choices(account: str, items: list[SourceImage]) -> dict[str, str]:
    path = vehicle_metadata_path(account)
    try:
        saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        records = saved.get("items", {}) if saved.get("version") == 1 else {}
    except (OSError, ValueError, TypeError, AttributeError):
        records = {}
    result: dict[str, str] = {}
    for item in items:
        record = records.get(item.path.name, {})
        if (isinstance(record, dict) and record.get("sha256") == _file_sha256(item.path)
                and record.get("choice") in VEHICLE_CHOICES):
            result[item.path.name] = record["choice"]
        else:
            result[item.path.name] = "none"
    return result


def save_vehicle_choices(account: str, items: list[SourceImage], choices: dict[str, str]) -> Path:
    path = vehicle_metadata_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "items": {
            item.path.name: {
                "sha256": _file_sha256(item.path),
                "choice": choices.get(item.path.name, "none"),
            }
            for item in items
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def ensure_vehicle_label_assets() -> None:
    if not OUTFIT_LABEL_SOURCE.is_file() or not VEHICLE_LABEL_EXPORT_SCRIPT.is_file():
        raise ComposeError("Thiếu kho chữ hoặc script xuất nhãn vé xe.")
    expected = [VEHICLE_LABEL_DIR / f"{choice}.png"
                for choice in VEHICLE_CHOICES if choice.startswith("ticket_")]
    latest_source = max(OUTFIT_LABEL_SOURCE.stat().st_mtime_ns,
                        VEHICLE_LABEL_EXPORT_SCRIPT.stat().st_mtime_ns)
    if all(path.is_file() and path.stat().st_mtime_ns >= latest_source for path in expected):
        return
    VEHICLE_LABEL_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = TEMP_DIR / "jobs" / f"export_vehicle_labels_{uuid.uuid4().hex}.jsx"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "#target photoshop",
        f"var AUTO_GHEP_VEHICLE_SOURCE = {json.dumps(str(OUTFIT_LABEL_SOURCE).replace(chr(92), '/'))};",
        f"var AUTO_GHEP_VEHICLE_DIR = {json.dumps(str(VEHICLE_LABEL_DIR).replace(chr(92), '/'))};",
        f"$.evalFile(File({json.dumps(str(VEHICLE_LABEL_EXPORT_SCRIPT).replace(chr(92), '/'))}));",
    ]
    wrapper.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(PHOTOSHOP_BRIDGE), "-ScriptPath", str(wrapper)],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ComposeError("Photoshop xuất nhãn vé xe quá 3 phút.") from exc
    finally:
        wrapper.unlink(missing_ok=True)
    if completed.returncode != 0 or not all(
        path.is_file() and path.stat().st_mtime_ns >= latest_source for path in expected
    ):
        detail = (completed.stderr or completed.stdout or "Thiếu ảnh nhãn đầu ra").strip()
        raise ComposeError(f"Không xuất được nhãn vé xe từ PSD: {detail}")


def vehicle_label_asset(choice: str) -> Path:
    return (OUTFIT_LABEL_DIR / "vip.png" if choice == "vip"
            else VEHICLE_LABEL_DIR / f"{choice}.png")


def vehicle_label_geometry(placement: dict[str, Any], asset: Path) -> tuple[int, int, int, int]:
    asset_width, asset_height = image_size(asset)
    cell_width = int(placement["width"])
    cell_height = int(placement["height"])
    if asset.stem == "vip":
        width = max(1, round(cell_width * 0.36))
        height = max(1, round(cell_height * 0.32))
    else:
        height = max(1, round(cell_height * 0.40))
        width = max(1, min(round(cell_width * 0.72),
                           round(asset_width / asset_height * height * 1.5)))
    margin = max(2, round(min(cell_width, cell_height) * 0.035))
    x = int(placement["x"]) + margin
    y = int(placement["y"]) + cell_height - height - margin
    return x, y, width, height


def _mean_brightness(path: Path) -> float:
    with Image.open(path) as image:
        image = image.convert("L")
        image.thumbnail((320, 180), Image.Resampling.BILINEAR)
        return float(ImageStat.Stat(image).mean[0])


def find_lobby_sources(input_dir: Path | None = None) -> tuple[Path, Path, list[Path]]:
    """Trả về (ảnh hồ sơ bên trái, ảnh sảnh bên phải, danh sách ứng viên).

    Quy trình chụp hiện tại đặt hai ảnh tổng quan ở cuối lượt chụp. Bộ phân loại
    sẵn có thường xếp đúng hai ảnh này vào ITEM/OTHER; dùng thông tin đó trước,
    sau đó mới dự phòng bằng hai tên file cuối. Ảnh tối hơn thường là hồ sơ.
    """
    input_dir = INPUT_DIR if input_dir is None else input_dir
    files = sorted(
        (path for path in input_dir.iterdir()
         if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda p: natural_key(p.name),
    ) if input_dir.is_dir() else []
    if len(files) < 2:
        raise ComposeError(f"Cần ít nhất 2 ảnh gốc trong {input_dir}")

    large_files: list[Path] = []
    for path in files:
        try:
            width, height = image_size(path)
            if width >= 1200 and 1.7 <= width / max(1, height) <= 2.5:
                large_files.append(path)
        except ComposeError:
            continue
    if len(large_files) < 2:
        large_files = files

    classified_candidates: list[Path] = []
    try:
        import Start  # dùng lại đúng bộ nhận diện đang chạy trong project.

        for path in large_files:
            image = Start.cv2_imread_utf8(str(path))
            if image is None:
                continue
            if Start.ImageClassifier.classify(image) in {"ITEM", "OTHER"}:
                classified_candidates.append(path)
    except Exception:
        classified_candidates = []

    candidates = classified_candidates if len(classified_candidates) >= 2 else large_files
    selected = sorted(candidates, key=lambda p: natural_key(p.name))[-2:]
    selected = sorted(selected, key=_mean_brightness)
    profile, lobby = selected[0], selected[1]
    return profile.resolve(), lobby.resolve(), [path.resolve() for path in candidates]


def choose_auto_form(categories: dict[str, list[SourceImage]]) -> str:
    count = sum(len(items) for items in categories.values())
    inventory_count = sum(len(categories[name]) for name in INVENTORY_CATEGORIES)
    if 1 <= inventory_count <= 6 and count <= 55 and len(categories["tp"]) <= 12:
        return "classic_small_736"
    if count >= 55 or inventory_count >= 8 or len(categories["tp"]) >= 12:
        return "classic_wide"
    return "classic_compact"


def _placement(
    item: SourceImage,
    group: str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    direct_select: bool = True,
) -> dict[str, Any]:
    return {
        "path": str(item.path),
        "name": item.path.stem,
        "category": item.category,
        "group": group,
        "x": int(x),
        "y": int(y),
        "width": max(1, int(width)),
        "height": max(1, int(height)),
        "direct_select": bool(direct_select),
    }


def bounded_height(natural_height: int, target_height: int, max_stretch: float) -> int:
    """Cân chiều cao nhưng giới hạn cả kéo dài lẫn nén ảnh nguồn."""
    natural_height = max(1, int(natural_height))
    max_stretch = max(1.0, float(max_stretch))
    minimum = max(1, math.ceil(natural_height / max_stretch))
    maximum = max(minimum, math.floor(natural_height * max_stretch))
    return min(max(int(target_height), minimum), maximum)


def place_grid(
    items: Iterable[SourceImage],
    *,
    x: int,
    y: int,
    width: int,
    columns: int,
    group: str,
    gap: int = 0,
    stretch_rows: bool = False,
    fixed_row_height: int | None = None,
    direct_select: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    items = list(items)
    if not items:
        return [], 0
    columns = max(1, min(int(columns), len(items)))
    cell_width = max(1, (width - gap * (columns - 1)) // columns)
    placements: list[dict[str, Any]] = []
    cursor_y = y
    for start in range(0, len(items), columns):
        row = items[start:start + columns]
        row_heights = [max(1, round(cell_width * item.height / item.width)) for item in row]
        row_height = max(1, int(fixed_row_height)) if fixed_row_height else max(row_heights)
        for column, (item, item_height) in enumerate(zip(row, row_heights)):
            item_x = x + column * (cell_width + gap)
            target_height = row_height if (stretch_rows or fixed_row_height) else item_height
            placements.append(_placement(
                item, group, item_x, cursor_y, cell_width, target_height,
                direct_select=direct_select,
            ))
        cursor_y += row_height + gap
    return placements, cursor_y - y - gap


def uniform_row_height(
    items: Iterable[SourceImage],
    *,
    width: int,
    columns: int,
    gap: int = 0,
) -> int:
    """Lấy chiều cao giữa để một ảnh súng cao bất thường không làm lệch hàng."""
    items = list(items)
    if not items:
        return 1
    columns = max(1, min(int(columns), len(items)))
    cell_width = max(1, (width - gap * (columns - 1)) // columns)
    heights = sorted(max(1, round(cell_width * item.height / item.width)) for item in items)
    middle = len(heights) // 2
    if len(heights) % 2:
        return heights[middle]
    return max(1, round((heights[middle - 1] + heights[middle]) / 2))


def place_grid_column_major(
    items: Iterable[SourceImage],
    *,
    x: int,
    y: int,
    width: int,
    columns: int,
    gap: int = 0,
    direct_select: bool = True,
    target_row_height: int | None = None,
    max_vertical_stretch: float = 1.35,
) -> tuple[list[dict[str, Any]], int]:
    """Xếp panel từ trên xuống dưới rồi mới chuyển sang cột kế tiếp."""
    items = list(items)
    if not items:
        return [], 0
    columns = max(1, min(int(columns), len(items)))
    rows = math.ceil(len(items) / columns)
    cell_width = max(1, (width - gap * (columns - 1)) // columns)
    natural_heights = [max(1, round(cell_width * item.height / item.width)) for item in items]
    item_heights = [
        bounded_height(height, target_row_height, max_vertical_stretch)
        if target_row_height else height
        for height in natural_heights
    ]
    row_heights = []
    for row in range(rows):
        heights = [
            item_heights[column * rows + row]
            for column in range(columns)
            if column * rows + row < len(items)
        ]
        row_heights.append(max(max(heights), int(target_row_height or 0)))
    row_y = [y]
    for row_height in row_heights[:-1]:
        row_y.append(row_y[-1] + row_height + gap)

    placements: list[dict[str, Any]] = []
    for index, (item, item_height) in enumerate(zip(items, item_heights)):
        column = index // rows
        row = index % rows
        placements.append(_placement(
            item,
            INVENTORY_GROUPS[item.category],
            x + column * (cell_width + gap),
            row_y[row],
            cell_width,
            item_height,
            direct_select=direct_select,
        ))
    return placements, sum(row_heights) + gap * (rows - 1)


def _reference_gun_columns(
    guns: list[SourceImage], dienlv_guns: DienLVGunSet | None,
) -> tuple[list[SourceImage], list[SourceImage]]:
    """Tách thứ tự hàng của DienLV về hai cột level gốc như mẫu 736."""
    if not guns:
        return [], []
    if dienlv_guns and dienlv_guns.columns == 2:
        left_rows = min(len(guns), max(1, dienlv_guns.rows))
        right_rows = len(guns) - left_rows
        left: list[SourceImage] = []
        right: list[SourceImage] = []
        cursor = 0
        for row in range(left_rows):
            left.append(guns[cursor])
            cursor += 1
            if row < right_rows:
                right.append(guns[cursor])
                cursor += 1
        return left, right
    # Ảnh súng trong output không có PNG DienLV đối chiếu: giữ thứ tự tên file.
    left_rows = math.ceil(len(guns) / 2)
    return guns[:left_rows], guns[left_rows:]


def place_small_account_left(
    guns: list[SourceImage],
    cars: list[SourceImage],
    small: list[SourceImage],
    dienlv_guns: DienLVGunSet | None,
    *,
    x: int,
    y: int,
    width: int,
    outfit_height: int,
    form: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """Mẫu PSD 736: súng cột trái, xe/item cột phải, súng dư dồn xuống cuối."""
    settings = form["left"]
    special = form["small_account_layout"]
    max_stretch = float(special.get("max_vertical_stretch", 1.35))
    gun_width = max(1, round(width * float(settings["gun_width_ratio_with_rail"])))
    rail_width = max(1, width - gun_width)
    left_guns, right_guns = _reference_gun_columns(guns, dienlv_guns)
    small_columns = max(1, int(settings["small_columns_with_guns"]))
    small_rows = math.ceil(len(small) / small_columns)
    rail_rows = len(cars) + small_rows
    left_tail = left_guns[min(rail_rows, len(left_guns)):]
    bottom_rows = max(len(left_tail), len(right_guns))
    total_rows = max(1, rail_rows + bottom_rows)

    natural_gun_height = uniform_row_height(guns, width=gun_width, columns=1)
    target = round(outfit_height / total_rows) if outfit_height else natural_gun_height
    row_height = bounded_height(natural_gun_height, target, max_stretch)
    placements: list[dict[str, Any]] = []

    def add(item: SourceImage, group: str, item_x: int, row: int, item_width: int) -> None:
        natural = max(1, round(item_width * item.height / item.width))
        height = bounded_height(natural, row_height, max_stretch)
        placements.append(_placement(item, group, item_x, y + row * row_height, item_width, height))

    for row, item in enumerate(left_guns[:rail_rows]):
        add(item, "10_GUNS", x, row, gun_width)

    for row, item in enumerate(cars):
        add(item, "20_VEHICLES", x + gun_width, row, rail_width)

    rail_start = len(cars)
    for index, item in enumerate(small):
        column = index % small_columns
        cell_left = round(rail_width * column / small_columns)
        cell_right = round(rail_width * (column + 1) / small_columns)
        add(item, "50_EXTRAS", x + gun_width + cell_left,
            rail_start + index // small_columns, cell_right - cell_left)

    for row in range(bottom_rows):
        if row < len(left_tail):
            add(left_tail[row], "10_GUNS", x, rail_rows + row, gun_width)
        if row < len(right_guns):
            add(right_guns[row], "10_GUNS", x + gun_width, rail_rows + row, rail_width)

    return placements, total_rows * row_height, {
        "rail_rows": rail_rows,
        "bottom_gun_rows": bottom_rows,
        "row_height": row_height,
        "max_vertical_stretch_percent": round(max_stretch * 100),
    }


def _active_zone_ratios(categories: dict[str, list[SourceImage]], form: dict[str, Any]) -> dict[str, float]:
    active = {
        "left": bool(categories["sung"] or categories["xe"] or
                     any(categories[name] for name in LEFT_SMALL_CATEGORIES)),
        "outfits": bool(categories["tp"]),
        "inventory": any(categories[name] for name in INVENTORY_CATEGORIES),
    }
    ratios = {name: float(value) for name, value in form["zone_ratios"].items() if active[name]}
    if not ratios:
        raise ComposeError("Không có nhóm ảnh nào phù hợp để ghép.")
    total = sum(ratios.values())
    return {name: value / total for name, value in ratios.items()}


def build_layout_plan(
    account: str,
    profile_path: Path | None,
    lobby_path: Path | None,
    categories: dict[str, list[SourceImage]],
    form: dict[str, Any],
    include_label_library: bool = False,
    dienlv_guns: DienLVGunSet | None = None,
    middle_profile_path: Path | None = None,
    outfit_choices: dict[str, str] | None = None,
    vehicle_choices: dict[str, str] | None = None,
    gun_columns_override: int | None = None,
) -> dict[str, Any]:
    account = validate_account_id(account)
    canvas_width = int(form["canvas_width"])
    header_paths = [profile_path, middle_profile_path, lobby_path]
    header_categories = ["profile_left", "profile_middle", "lobby_right"]
    header_items: list[SourceImage | None] = []
    for path, category in zip(header_paths, header_categories):
        if path is None:
            header_items.append(None)
            continue
        resolved = Path(path).resolve()
        width, height = image_size(resolved)
        header_items.append(SourceImage(resolved, category, width, height))

    selected_header_items = [item for item in header_items if item is not None]
    selected_count = len(selected_header_items)
    slot_edges = (
        [round(canvas_width * index / selected_count) for index in range(selected_count + 1)]
        if selected_count else [0]
    )
    header_heights = [
        round((slot_edges[index + 1] - slot_edges[index]) * item.height / item.width)
        for index, item in enumerate(selected_header_items)
    ]
    header_height = max(header_heights, default=0)

    placements: list[dict[str, Any]] = []
    for index, item in enumerate(selected_header_items):
        placements.append(_placement(
            item,
            "00_HEADER",
            slot_edges[index],
            0,
            slot_edges[index + 1] - slot_edges[index],
            header_height,
        ))

    ratios = _active_zone_ratios(categories, form)
    zone_bounds: dict[str, tuple[int, int]] = {}
    cursor_x = 0
    active_names = [name for name in ("left", "outfits", "inventory") if name in ratios]
    cumulative = 0.0
    for index, name in enumerate(active_names):
        if index == len(active_names) - 1:
            right = canvas_width
        else:
            cumulative += ratios[name]
            right = round(canvas_width * cumulative)
        zone_bounds[name] = (cursor_x, right - cursor_x)
        cursor_x = right

    zone_heights: dict[str, int] = {}
    start_y = header_height
    outfit_count = len(categories["tp"])
    configured_outfit_rows, configured_outfit_columns = OUTFIT_GRID_BY_COUNT.get(
        outfit_count,
        (math.ceil(outfit_count / max(1, int(form["outfits"]["columns"]))) if outfit_count else 0,
         int(form["outfits"]["columns"])),
    )
    outfit_placements: list[dict[str, Any]] = []
    outfit_label_placements: list[dict[str, Any]] = []
    outfit_height = 0
    if "outfits" in zone_bounds:
        outfit_x, outfit_width = zone_bounds["outfits"]
        outfit_placements, outfit_height = place_grid(
            categories["tp"], x=outfit_x, y=start_y, width=outfit_width,
            columns=configured_outfit_columns, group="30_OUTFITS", direct_select=True,
        )
        for item, placement in zip(categories["tp"], outfit_placements):
            choice = (outfit_choices or {}).get(item.path.name, "normal")
            if choice == "normal":
                continue
            asset = OUTFIT_LABEL_DIR / f"{choice}.png"
            asset_width, asset_height = image_size(asset)
            label_height = max(1, round(placement["width"] * (0.20 if choice == "vip" else 0.25)))
            label_width = max(1, round(label_height * asset_width / asset_height))
            margin = max(3, round(placement["width"] * 0.025))
            outfit_label_placements.append({
                "path": str(asset.resolve()),
                "name": f"{item.path.stem}_{choice}",
                "category": "outfit_label",
                "group": None,
                "x": placement["x"] + placement["width"] - label_width - margin,
                "y": placement["y"] + margin,
                "width": label_width,
                "height": label_height,
                "direct_select": True,
            })
    small_account_info: dict[str, int] = {}

    if "left" in zone_bounds:
        zone_x, zone_width = zone_bounds["left"]
        settings = form["left"]
        guns = categories["sung"]
        gun_columns = gun_columns_override or (dienlv_guns.columns if dienlv_guns else (calculate_gun_columns_and_rows(len(guns))[0] if guns else int(settings["gun_columns"])))
        cars = sorted_vehicles(categories["xe"], vehicle_choices)
        small = [item for name in LEFT_SMALL_CATEGORIES for item in categories[name]]
        rail_exists = bool(cars or small)
        local_heights: list[int] = []

        if guns and rail_exists and form.get("small_account_layout", {}).get("share_rail_with_first_gun_column") and gun_columns == 2:
            compact_placements, compact_height, small_account_info = place_small_account_left(
                guns, cars, small, dienlv_guns,
                x=zone_x, y=start_y, width=zone_width,
                outfit_height=outfit_height, form=form,
            )
            placements.extend(compact_placements)
            local_heights.append(compact_height)
        elif guns and rail_exists:
            gun_width = max(1, round(zone_width * float(settings["gun_width_ratio_with_rail"])))
            rail_width = zone_width - gun_width
            gun_row_height = uniform_row_height(
                guns, width=gun_width, columns=gun_columns,
            )
            gun_placements, gun_height = place_grid(
                guns, x=zone_x, y=start_y, width=gun_width,
                columns=gun_columns, group="10_GUNS",
                fixed_row_height=gun_row_height,
            )
            placements.extend(gun_placements)
            rail_y = start_y
            car_placements, car_height = place_grid(
                cars, x=zone_x + gun_width, y=rail_y, width=rail_width,
                columns=int(settings["car_columns_with_guns"]), group="20_VEHICLES",
                fixed_row_height=gun_row_height,
            )
            placements.extend(car_placements)
            rail_y += car_height
            small_placements, small_height = place_grid(
                small, x=zone_x + gun_width, y=rail_y, width=rail_width,
                columns=int(settings["small_columns_with_guns"]), group="50_EXTRAS",
                fixed_row_height=gun_row_height,
            )
            placements.extend(small_placements)
            local_heights.extend([gun_height, car_height + small_height])
        else:
            local_y = start_y
            if guns:
                gun_row_height = uniform_row_height(
                    guns, width=zone_width, columns=gun_columns,
                )
                gun_placements, gun_height = place_grid(
                    guns, x=zone_x, y=local_y, width=zone_width,
                    columns=gun_columns, group="10_GUNS",
                    fixed_row_height=gun_row_height,
                )
                placements.extend(gun_placements)
                local_y += gun_height
            car_placements, car_height = place_grid(
                cars, x=zone_x, y=local_y, width=zone_width,
                columns=int(settings["car_columns_without_guns"]), group="20_VEHICLES",
            )
            placements.extend(car_placements)
            local_y += car_height
            small_placements, small_height = place_grid(
                small, x=zone_x, y=local_y, width=zone_width,
                columns=int(settings["small_columns_without_guns"]), group="50_EXTRAS",
            )
            placements.extend(small_placements)
            local_heights.append(local_y + small_height - start_y)
        zone_heights["left"] = max(local_heights or [0])

    if "outfits" in zone_bounds:
        placements.extend(outfit_placements)
        zone_heights["outfits"] = outfit_height

    if "inventory" in zone_bounds:
        zone_x, zone_width = zone_bounds["inventory"]
        inventory_items = [item for category in INVENTORY_CATEGORIES for item in categories[category]]
        inventory_placements, inventory_height = place_grid_column_major(
            inventory_items,
            x=zone_x,
            y=start_y,
            width=zone_width,
            columns=int(form["inventory"]["columns"]),
            direct_select=True,
            target_row_height=(round(outfit_height / configured_outfit_rows)
                               if form.get("small_account_layout") and configured_outfit_rows else None),
            max_vertical_stretch=float(form.get("small_account_layout", {}).get("max_vertical_stretch", 1.35)),
        )
        placements.extend(inventory_placements)
        zone_heights["inventory"] = inventory_height

    vehicle_label_placements: list[dict[str, Any]] = []
    for placement in placements:
        if placement["category"] != "xe":
            continue
        choice = (vehicle_choices or {}).get(Path(placement["path"]).name, "none")
        if choice == "none":
            continue
        asset = vehicle_label_asset(choice)
        x, y, width, height = vehicle_label_geometry(placement, asset)
        vehicle_label_placements.append({
            "path": str(asset.resolve()),
            "name": f"{placement['name']}_{choice}",
            "category": "vehicle_label",
            "group": None,
            "x": x, "y": y, "width": width, "height": height,
            "direct_select": True,
        })
    placements.extend(vehicle_label_placements)
    placements.extend(outfit_label_placements)

    bottom_height = max(int(form.get("minimum_bottom_height", 1)), max(zone_heights.values(), default=1))
    canvas_height = header_height + bottom_height
    watermark = dict(form.get("watermark", {}))

    return {
        "version": 1,
        "account_id": account,
        "form_id": form["id"],
        "canvas": {"width": canvas_width, "height": canvas_height, "background": form.get("background", [0, 0, 0])},
        "header_height": header_height,
        "header_slots": [
            {
                "position": position,
                "selected": item is not None,
                "path": str(item.path) if item else "",
                "x": (
                    slot_edges[sum(value is not None for value in header_items[:index])]
                    if item is not None else None
                ),
                "width": (
                    slot_edges[sum(value is not None for value in header_items[:index]) + 1]
                    - slot_edges[sum(value is not None for value in header_items[:index])]
                    if item is not None else 0
                ),
            }
            for index, (position, item) in enumerate(zip(
                ("left", "middle", "right"), header_items,
            ))
        ],
        "header_selected_count": selected_count,
        "zone_bounds": {name: {"x": x, "width": width, "height": zone_heights.get(name, 0)}
                        for name, (x, width) in zone_bounds.items()},
        # Mọi layer ảnh và nhãn đều đặt trực tiếp ở root; không gộp thành nhóm/group.
        "groups": ["90_LABEL_LIBRARY"] if include_label_library and LABEL_LIBRARY.is_file() else [],
        "placements": placements,
        "outfit_choices": outfit_choices or {},
        "vehicle_choices": vehicle_choices or {},
        "watermark": watermark,
        "outfit_grid": {
            "count": outfit_count,
            "rows": configured_outfit_rows,
            "columns": configured_outfit_columns,
            "preset_matched": outfit_count in OUTFIT_GRID_BY_COUNT,
        },
        "small_account_layout": small_account_info or None,
        "dienlv_guns": ({
            "code": dienlv_guns.code,
            "count": len(dienlv_guns.items),
            "columns": dienlv_guns.columns,
            "rows": dienlv_guns.rows,
            "reference_path": str(dienlv_guns.reference_path),
            "source_mode": "individual_smart_objects_from_anhle",
        } if dienlv_guns else None),
        "inventory_layout": {
            "source_mode": "original_input_images_as_individual_smart_objects",
            "count": sum(len(categories[name]) for name in INVENTORY_CATEGORIES),
            "columns": int(form["inventory"]["columns"]),
            "order": list(INVENTORY_CATEGORIES),
            "fill_direction": "top_to_bottom_then_next_column",
            "cropping": "none",
            "direct_select": True,
        },
        "label_library_path": str(LABEL_LIBRARY.resolve()) if include_label_library and LABEL_LIBRARY.is_file() else "",
    }


def _fit_font(size: int) -> ImageFont.ImageFont:
    for path in (Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_preview(plan: dict[str, Any], output_path: Path, max_width: int = 1900) -> Path:
    canvas = plan["canvas"]
    scale = min(1.0, max_width / int(canvas["width"]))
    width = max(1, round(int(canvas["width"]) * scale))
    height = max(1, round(int(canvas["height"]) * scale))
    background = tuple(int(v) for v in canvas.get("background", [0, 0, 0]))
    result = Image.new("RGB", (width, height), background)

    for placement in plan["placements"]:
        target = (
            max(1, round(placement["width"] * scale)),
            max(1, round(placement["height"] * scale)),
        )
        with Image.open(placement["path"]) as source:
            source = source.convert("RGBA").resize(target, Image.Resampling.LANCZOS)
            position = (round(placement["x"] * scale), round(placement["y"] * scale))
            result.paste(source.convert("RGB"), position, source.getchannel("A"))

    watermark = plan.get("watermark", {})
    if watermark.get("enabled"):
        draw = ImageDraw.Draw(result)
        font = _fit_font(max(20, round(int(watermark.get("font_size", 200)) * scale)))
        margin = round(int(watermark.get("margin", 32)) * scale)
        text = "Z" + plan["account_id"]
        box = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, round(4 * scale)))
        x = width - margin - (box[2] - box[0])
        y = height - margin - (box[3] - box[1])
        draw.text((x, y), text, font=font, fill="white", stroke_fill="#e00000",
                  stroke_width=max(1, round(4 * scale)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "JPEG", quality=90, optimize=True)
    return output_path


def create_run_folder(account: str, results_root: Path | None = None) -> Path:
    """Đặt kết quả trực tiếp vào thư mục mã acc, không có tầng ngày giờ."""
    account = validate_account_id(account)
    results_root = RESULTS_DIR if results_root is None else results_root
    account_root = results_root / account
    account_root.mkdir(parents=True, exist_ok=True)
    return account_root


def choose_run_files(account: str, output_folder: Path) -> RunFiles:
    """Giữ bản cũ khi ghép lại: 735.psd, rồi 735_02.psd,... cùng một thư mục."""
    account = validate_account_id(account)
    index = 1
    while True:
        suffix = "" if index == 1 else f"_{index:02}"
        files = RunFiles(
            psd=output_folder / f"{account}{suffix}.psd",
            png=output_folder / f"{account}{suffix}.png",
            preview=output_folder / f"xem_truoc{suffix}.jpg",
            layout=output_folder / f"layout{suffix}.json",
        )
        if not any(path.exists() for path in (files.psd, files.png, files.preview, files.layout)):
            return files
        index += 1


def save_plan(plan: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_photoshop(
    plan: dict[str, Any], output_folder: Path,
    log: Callable[[str], None] = print,
    run_files: RunFiles | None = None,
) -> tuple[Path, Path, Path]:
    if not PHOTOSHOP_SCRIPT.is_file() or not PHOTOSHOP_BRIDGE.is_file():
        raise ComposeError("Thiếu bộ điều khiển Photoshop trong thư mục GhepPSD\\photoshop.")

    output_folder.mkdir(parents=True, exist_ok=True)
    account = plan["account_id"]
    run_files = run_files or choose_run_files(account, output_folder)
    psd_path = run_files.psd
    png_path = run_files.png
    layout_path = run_files.layout
    if psd_path.exists() or png_path.exists():
        raise ComposeError(f"Tên file kết quả đã tồn tại: {psd_path.name}. Hãy ghép lại để chọn tên mới.")

    job_root = TEMP_DIR / "jobs"
    job_root.mkdir(parents=True, exist_ok=True)
    job_id = f"{account}_{uuid.uuid4().hex}"
    completion_path = job_root / f"{job_id}.done.json"
    job_path = job_root / f"{job_id}.json"
    wrapper_path = job_root / f"{job_id}.jsx"

    job = dict(plan)
    job.update({
        "output_psd": str(psd_path.resolve()),
        "output_png": str(png_path.resolve()),
        "completion_path": str(completion_path.resolve()),
    })
    save_plan(job, job_path)
    save_plan(plan, layout_path)

    job_js = str(job_path.resolve()).replace("\\", "/").replace('"', '\\"')
    script_js = str(PHOTOSHOP_SCRIPT.resolve()).replace("\\", "/").replace('"', '\\"')
    wrapper_path.write_text(
        '#target photoshop\nvar AUTO_GHEP_JOB_PATH = "' + job_js + '";\n' +
        '$.evalFile(File("' + script_js + '"));\n',
        encoding="utf-8-sig",
    )

    log("Đang mở Photoshop và tạo Smart Object...")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(PHOTOSHOP_BRIDGE), "-ScriptPath", str(wrapper_path),
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as exc:
        raise ComposeError("Photoshop xử lý quá 15 phút. PSD có thể vẫn đang mở trong Photoshop.") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Lỗi không xác định").strip()
        raise ComposeError(f"Photoshop không tạo được PSD: {detail}")
    if not completion_path.is_file():
        raise ComposeError("Photoshop đã dừng nhưng không trả kết quả hoàn tất.")
    status = json.loads(completion_path.read_text(encoding="utf-8-sig"))
    if not status.get("ok"):
        raise ComposeError(f"Photoshop báo lỗi: {status.get('error', 'không rõ nguyên nhân')}")
    if not psd_path.is_file() or not png_path.is_file():
        raise ComposeError("Photoshop báo xong nhưng thiếu file PSD hoặc PNG.")
    # Ba file dưới chỉ là cầu nối tạm giữa Python và Photoshop. Giữ layout
    # chính, nhưng dọn file kỹ thuật sau khi đã xác nhận kết quả thành công.
    for temporary_path in (completion_path, job_path, wrapper_path):
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    log(f"Đã tạo PSD: {psd_path.name}")
    return psd_path, png_path, layout_path


def prepare_plan(
    account: str,
    form_id: str = "auto",
    profile_path: Path | None = None,
    lobby_path: Path | None = None,
    include_label_library: bool = False,
    gun_code: str | None = None,
    middle_profile_path: Path | None = None,
    auto_detect_headers: bool = True,
    outfit_choices: dict[str, str] | None = None,
    vehicle_choices: dict[str, str] | None = None,
    gun_choices: tuple[list[SourceImage], int, int] | None = None,
) -> tuple[dict[str, Any], dict[str, list[SourceImage]], Path | None, Path | None]:
    categories = scan_account_output(account)
    chosen_outfits = (outfit_choices if outfit_choices is not None
                      else load_outfit_choices(account, categories["tp"]))
    chosen_vehicles = (vehicle_choices if vehicle_choices is not None
                       else load_vehicle_choices(account, categories["xe"]))
    if (any(choice != "normal" for choice in chosen_outfits.values())
            or "vip" in chosen_vehicles.values()):
        ensure_outfit_label_assets()
    if any(choice not in {"none", "vip"} for choice in chosen_vehicles.values()):
        ensure_vehicle_label_assets()
    categories["tp"] = sorted_outfits(categories["tp"], chosen_outfits)
    categories["xe"] = sorted_vehicles(categories["xe"], chosen_vehicles)
    dienlv_guns = load_dienlv_guns(gun_code) if gun_code else None
    if dienlv_guns:
        categories["sung"] = list(dienlv_guns.items)

    gun_columns_override: int | None = None
    if gun_choices is not None:
        chosen_guns, chosen_cols, chosen_rows = gun_choices
        categories["sung"] = chosen_guns
        if dienlv_guns:
            dienlv_guns = DienLVGunSet(
                code=dienlv_guns.code,
                items=tuple(chosen_guns),
                columns=chosen_cols,
                rows=chosen_rows,
                reference_path=dienlv_guns.reference_path,
            )
        gun_columns_override = chosen_cols
    else:
        active_source = categories["sung"] or (list(dienlv_guns.items) if dienlv_guns else [])
        if active_source:
            saved_excluded, saved_cols = load_gun_choices(account, active_source)
            active_guns = [g for g in active_source if g.path.name not in saved_excluded]
            if active_guns:
                categories["sung"] = active_guns
                auto_cols, auto_rows = calculate_gun_columns_and_rows(len(active_guns))
                final_cols = saved_cols if saved_cols else (dienlv_guns.columns if dienlv_guns and dienlv_guns.columns else auto_cols)
                final_rows = math.ceil(len(active_guns) / final_cols)
                if dienlv_guns:
                    dienlv_guns = DienLVGunSet(
                        code=dienlv_guns.code,
                        items=tuple(active_guns),
                        columns=final_cols,
                        rows=final_rows,
                        reference_path=dienlv_guns.reference_path,
                    )
                gun_columns_override = final_cols

    if auto_detect_headers and (profile_path is None or lobby_path is None):
        detected_profile, detected_lobby, _ = find_lobby_sources(INPUT_DIR)
        profile_path = profile_path or detected_profile
        lobby_path = lobby_path or detected_lobby
    forms = load_forms()
    selected_form_id = choose_auto_form(categories) if form_id == "auto" else form_id
    if selected_form_id not in forms:
        raise ComposeError(f"Không tìm thấy form: {selected_form_id}")
    plan = build_layout_plan(
        account,
        Path(profile_path) if profile_path else None,
        Path(lobby_path) if lobby_path else None,
        categories,
        forms[selected_form_id],
        include_label_library,
        dienlv_guns,
        Path(middle_profile_path) if middle_profile_path else None,
        chosen_outfits,
        chosen_vehicles,
        gun_columns_override=gun_columns_override,
    )
    return (
        plan,
        categories,
        Path(profile_path) if profile_path else None,
        Path(lobby_path) if lobby_path else None,
    )


class OutfitChoiceDialog:
    def __init__(self, parent: "tk.Tk", items: list[SourceImage], saved: dict[str, str],
                 action: str) -> None:
        self.items = items
        self.result: dict[str, str] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("CHỌN LOẠI TRANG PHỤC VÀ SỐ SAO")
        self.window.geometry("1080x800")
        self.window.minsize(850, 620)
        self.window.configure(bg="#11111b")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.variables: dict[str, tk.StringVar] = {}
        self.cards: dict[str, tk.Frame] = {}
        self.images: dict[str, tk.Label] = {}
        self.positions: dict[str, tk.Label] = {}
        self.photos: dict[str, "ImageTk.PhotoImage"] = {}
        self.base_thumbnails: dict[str, tuple[Image.Image, int, int, int]] = {}
        self.current_thumbnail_choice: dict[str, str] = {}
        self.reverse_choices = {label: key for key, label in OUTFIT_CHOICES.items()}

        header = tk.Frame(self.window, bg="#181825", padx=16, pady=12)
        header.pack(fill=tk.X)
        tk.Label(header, text="CHỌN LOẠI TRANG PHỤC", bg="#181825", fg="#89b4fa",
                 font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(header, text="Chọn Thánh giáp và số sao, hoặc Thần giáp VIP. Ảnh còn lại là trang phục thường."
                 " Thứ tự bên dưới cập nhật ngay khi chọn.", bg="#181825", fg="#cdd6f4",
                 font=("Segoe UI", 10), wraplength=980, justify=tk.LEFT).pack(anchor="w", pady=(4, 0))

        center = tk.Frame(self.window, bg="#11111b")
        center.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(center, bg="#11111b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(center, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        grid = tk.Frame(canvas, bg="#11111b", padx=10, pady=10)
        canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        for original_index, item in enumerate(items, start=1):
            name = item.path.name
            card = tk.Frame(grid, bg="#313244", padx=8, pady=8, width=190)
            self.cards[name] = card
            position = tk.Label(card, text="", bg="#313244", fg="#f9e2af",
                                font=("Segoe UI", 9, "bold"))
            position.pack(anchor="w")
            self.positions[name] = position
            image_label = tk.Label(card, bg="#242432", width=170, height=180)
            image_label.pack(pady=(4, 6))
            self.images[name] = image_label
            tk.Label(card, text=item.path.stem, bg="#313244", fg="#cdd6f4",
                     font=("Segoe UI", 9)).pack()
            choice = saved.get(name, "normal")
            variable = tk.StringVar(value=OUTFIT_CHOICES.get(choice, OUTFIT_CHOICES["normal"]))
            self.variables[name] = variable
            combo = ttk.Combobox(card, textvariable=variable, values=list(OUTFIT_CHOICES.values()),
                                 state="readonly", width=20)
            combo.pack(pady=(6, 0))
            combo.bind("<<ComboboxSelected>>", lambda event: self.reorder())

        footer = tk.Frame(self.window, bg="#181825", padx=16, pady=12)
        footer.pack(fill=tk.X)
        self.summary = tk.Label(footer, text="", bg="#181825", fg="#cdd6f4")
        self.summary.pack(side=tk.LEFT)
        tk.Button(footer, text="HỦY", command=self.cancel, bg="#45475a", fg="white",
                  relief=tk.FLAT, padx=15, pady=8).pack(side=tk.RIGHT, padx=(8, 0))
        button_text = "LƯU & XEM TRƯỚC" if action == "preview" else "XÁC NHẬN & GHÉP PSD"
        tk.Button(footer, text=button_text, command=self.confirm, bg="#a6e3a1", fg="#11111b",
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=15, pady=8).pack(side=tk.RIGHT)
        self.reorder()
        self.window.grab_set()
        self.window.focus_set()
        parent.wait_window(self.window)

    def choices(self) -> dict[str, str]:
        return {name: self.reverse_choices[variable.get()]
                for name, variable in self.variables.items()}

    def update_thumbnail(self, item: SourceImage, choice: str) -> None:
        name = item.path.name
        if self.current_thumbnail_choice.get(name) == choice:
            return
        if name not in self.base_thumbnails:
            with Image.open(item.path) as source:
                source = source.convert("RGBA")
                source.thumbnail((170, 180), Image.Resampling.LANCZOS)
                image = Image.new("RGBA", (170, 180), "#242432")
                left = (170 - source.width) // 2
                top = (180 - source.height) // 2
                image.alpha_composite(source, (left, top))
                self.base_thumbnails[name] = (image, left, top, source.width)
        base, left, top, source_width = self.base_thumbnails[name]
        image = base.copy()
        if choice != "normal":
            asset = OUTFIT_LABEL_DIR / f"{choice}.png"
            if asset.is_file():
                with Image.open(asset) as label_source:
                    label = label_source.convert("RGBA")
                    target_height = max(1, round(source_width * (0.20 if choice == "vip" else 0.25)))
                    target_width = max(1, round(target_height * label.width / label.height))
                    label = label.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    image.alpha_composite(label, (left + source_width - target_width - 3, top + 3))
        photo = ImageTk.PhotoImage(image.convert("RGB"), master=self.window)
        self.photos[name] = photo
        self.images[name].configure(image=photo, width=170, height=180)
        self.current_thumbnail_choice[name] = choice

    def reorder(self) -> None:
        choices = self.choices()
        ordered = sorted_outfits(self.items, choices)
        for index, item in enumerate(ordered):
            name = item.path.name
            self.cards[name].grid(row=index // 5, column=index % 5, padx=5, pady=5, sticky="n")
            self.positions[name].configure(text=f"VỊ TRÍ {index + 1:02d}")
            self.update_thumbnail(item, choices[name])
        stars = sum(choice.startswith("star_") for choice in choices.values())
        vip = sum(choice == "vip" for choice in choices.values())
        self.summary.configure(text=f"{stars} Thánh giáp  •  {vip} Thần giáp VIP  •  "
                                    f"{len(self.items) - stars - vip} trang phục thường")

    def confirm(self) -> None:
        self.result = self.choices()
        self.window.destroy()

    def cancel(self) -> None:
        self.window.destroy()


class VehicleChoiceDialog:
    def __init__(self, parent: "tk.Tk", items: list[SourceImage], saved: dict[str, str],
                 action: str) -> None:
        self.items = items
        self.result: dict[str, str] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("CHỌN VÉ XE / VIP")
        self.window.geometry("1080x760")
        self.window.minsize(850, 570)
        self.window.configure(bg="#11111b")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.variables: dict[str, tk.StringVar] = {}
        self.cards: dict[str, tk.Frame] = {}
        self.images: dict[str, tk.Label] = {}
        self.positions: dict[str, tk.Label] = {}
        self.photos: dict[str, "ImageTk.PhotoImage"] = {}
        self.base_thumbnails: dict[str, tuple[Image.Image, dict[str, int]]] = {}
        self.current_thumbnail_choice: dict[str, str] = {}
        self.reverse_choices = {label: key for key, label in VEHICLE_CHOICES.items()}

        header = tk.Frame(self.window, bg="#181825", padx=16, pady=12)
        header.pack(fill=tk.X)
        tk.Label(header, text="CHỌN VÉ XE / VIP", bg="#181825", fg="#89b4fa",
                 font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(header, text="Chọn dạng vé hoặc VIP cho từng xe. Xe tự động sắp xếp theo thứ tự: "
                 "3 Vé -> 1 Vé -> VIP -> Không nhãn. Thứ tự bên dưới cập nhật ngay khi chọn.", bg="#181825", fg="#cdd6f4",
                 font=("Segoe UI", 10), wraplength=980, justify=tk.LEFT).pack(anchor="w", pady=(4, 0))

        center = tk.Frame(self.window, bg="#11111b")
        center.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(center, bg="#11111b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(center, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        grid = tk.Frame(canvas, bg="#11111b", padx=10, pady=10)
        canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        for index, item in enumerate(items):
            name = item.path.name
            card = tk.Frame(grid, bg="#313244", padx=9, pady=9)
            self.cards[name] = card
            card_top = tk.Frame(card, bg="#313244")
            card_top.pack(fill=tk.X)
            pos_label = tk.Label(card_top, text="", bg="#313244", fg="#f9e2af",
                                 font=("Segoe UI", 9, "bold"))
            pos_label.pack(side=tk.LEFT)
            self.positions[name] = pos_label
            tk.Label(card_top, text=item.path.stem, bg="#313244", fg="#cdd6f4",
                     font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(6, 0))
            image_label = tk.Label(card, bg="#242432")
            image_label.pack(pady=(5, 7))
            self.images[name] = image_label
            choice = saved.get(name, "none")
            variable = tk.StringVar(value=VEHICLE_CHOICES.get(choice, VEHICLE_CHOICES["none"]))
            self.variables[name] = variable
            combo = ttk.Combobox(card, textvariable=variable, values=list(VEHICLE_CHOICES.values()),
                                 state="readonly", width=27)
            combo.pack(fill=tk.X)
            combo.bind("<<ComboboxSelected>>", lambda event, car=item: self.reorder())

        footer = tk.Frame(self.window, bg="#181825", padx=16, pady=12)
        footer.pack(fill=tk.X)
        self.summary = tk.Label(footer, text="", bg="#181825", fg="#cdd6f4")
        self.summary.pack(side=tk.LEFT)
        tk.Button(footer, text="HỦY", command=self.cancel, bg="#45475a", fg="white",
                  relief=tk.FLAT, padx=15, pady=8).pack(side=tk.RIGHT, padx=(8, 0))
        button_text = "LƯU & XEM TRƯỚC" if action == "preview" else "XÁC NHẬN & GHÉP PSD"
        tk.Button(footer, text=button_text, command=self.confirm, bg="#a6e3a1", fg="#11111b",
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=15, pady=8).pack(side=tk.RIGHT)
        self.reorder()
        self.window.grab_set()
        self.window.focus_set()
        parent.wait_window(self.window)

    def choices(self) -> dict[str, str]:
        return {name: self.reverse_choices[variable.get()]
                for name, variable in self.variables.items()}

    def update_thumbnail(self, item: SourceImage) -> None:
        name = item.path.name
        choice = self.reverse_choices[self.variables[name].get()]
        if self.current_thumbnail_choice.get(name) == choice:
            return
        if name not in self.base_thumbnails:
            with Image.open(item.path) as source:
                source = source.convert("RGBA")
                source.thumbnail((300, 155), Image.Resampling.LANCZOS)
                image = Image.new("RGBA", (300, 155), "#242432")
                left = (300 - source.width) // 2
                top = (155 - source.height) // 2
                image.alpha_composite(source, (left, top))
                self.base_thumbnails[name] = (
                    image, {"x": left, "y": top, "width": source.width, "height": source.height}
                )
        base, placement = self.base_thumbnails[name]
        image = base.copy()
        if choice != "none":
            asset = vehicle_label_asset(choice)
            x, y, width, height = vehicle_label_geometry(placement, asset)
            with Image.open(asset) as label_source:
                label = label_source.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
                image.alpha_composite(label, (x, y))
        photo = ImageTk.PhotoImage(image.convert("RGB"), master=self.window)
        self.photos[name] = photo
        self.images[name].configure(image=photo, width=300, height=155)
        self.current_thumbnail_choice[name] = choice
        if hasattr(self, "summary"):
            self.update_summary()

    def reorder(self) -> None:
        choices = self.choices()
        ordered = sorted_vehicles(self.items, choices)
        for index, item in enumerate(ordered):
            name = item.path.name
            card = self.cards[name]
            card.grid_forget()
            card.grid(row=index // 3, column=index % 3, padx=7, pady=7, sticky="n")
            self.positions[name].configure(text=f"#{index + 1:02d}")
            self.update_thumbnail(item)
        self.update_summary()

    def update_summary(self) -> None:
        choices = self.choices()
        labeled = sum(choice != "none" for choice in choices.values())
        self.summary.configure(text=f"{labeled}/{len(self.items)} xe có nhãn")

    def confirm(self) -> None:
        self.result = self.choices()
        self.window.destroy()

    def cancel(self) -> None:
        self.window.destroy()

class GunChoiceDialog:
    def __init__(
        self,
        parent: "tk.Tk",
        items: list[SourceImage],
        saved_excluded: set[str],
        saved_columns: int | None,
        action: str
    ) -> None:
        self.items = items
        self.result: tuple[list[SourceImage], int, int] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("XẾP & LỌC THẺ SÚNG (XƯỞNG NÂNG CẤP)")
        self.window.geometry("1080x780")
        self.window.minsize(820, 580)
        self.window.configure(bg="#11111b")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        self.selected_vars: dict[str, tk.BooleanVar] = {}
        self.cards: dict[str, tk.Frame] = {}
        self.card_buttons: dict[str, tk.Button] = {}
        self.photos: dict[str, "ImageTk.PhotoImage"] = {}

        init_cols, init_rows = calculate_gun_columns_and_rows(len(items))
        if saved_columns and 1 <= saved_columns <= 10:
            init_cols = saved_columns
            init_rows = math.ceil(len(items) / init_cols)

        self.columns_var = tk.IntVar(value=init_cols)
        self.rows_var = tk.IntVar(value=init_rows)

        header = tk.Frame(self.window, bg="#181825", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="XẾP & LỌC THẺ SÚNG", bg="#181825", fg="#89b4fa",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(header, text="Tự động chia cột đều từ 8 - 15 súng/cột để không bị trống layout. "
                 "Bấm 'Bỏ chọn' trên thẻ súng không cần thiết. Bạn có thể chỉnh số cột súng.",
                 bg="#181825", fg="#cdd6f4", font=("Segoe UI", 9), wraplength=980, justify=tk.LEFT).pack(anchor="w", pady=(2, 6))

        ctrl_bar = tk.Frame(header, bg="#1e1e2e", padx=10, pady=6)
        ctrl_bar.pack(fill=tk.X)

        tk.Label(ctrl_bar, text="Số cột súng:", bg="#1e1e2e", fg="#f9e2af", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.col_spin = tk.Spinbox(ctrl_bar, from_=1, to=10, textvariable=self.columns_var, font=("Segoe UI", 10, "bold"),
                                   width=4, bg="#313244", fg="white", relief=tk.FLAT, command=self.on_columns_changed)
        self.col_spin.pack(side=tk.LEFT, padx=(0, 12))
        self.col_spin.bind("<KeyRelease>", lambda event: self.on_columns_changed())

        tk.Label(ctrl_bar, text="Số hàng/cột:", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.row_display = tk.Label(ctrl_bar, text=str(init_rows), bg="#313244", fg="#a6e3a1", font=("Segoe UI", 10, "bold"), width=4)
        self.row_display.pack(side=tk.LEFT, padx=(0, 15))

        tk.Button(ctrl_bar, text="⚡ Tự động chia (8-15 súng/cột)", command=self.auto_split,
                  bg="#89b4fa", fg="#11111b", font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=8, pady=3).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(ctrl_bar, text="Chọn tất cả", command=self.select_all,
                  bg="#45475a", fg="white", font=("Segoe UI", 8), relief=tk.FLAT, padx=8, pady=3).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(ctrl_bar, text="Bỏ chọn tất cả", command=self.deselect_all,
                  bg="#45475a", fg="white", font=("Segoe UI", 8), relief=tk.FLAT, padx=8, pady=3).pack(side=tk.LEFT)

        center = tk.Frame(self.window, bg="#11111b")
        center.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(center, bg="#11111b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(center, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        grid = tk.Frame(canvas, bg="#11111b", padx=10, pady=10)
        canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        for index, item in enumerate(items):
            name = item.path.name
            is_active = name not in saved_excluded
            var = tk.BooleanVar(value=is_active)
            self.selected_vars[name] = var

            card = tk.Frame(grid, bg="#313244" if is_active else "#242432", padx=6, pady=6, relief=tk.FLAT)
            self.cards[name] = card

            top_bar = tk.Frame(card, bg=card.cget("bg"))
            top_bar.pack(fill=tk.X)
            tk.Label(top_bar, text=f"#{index + 1:02d} {item.path.stem}", bg=card.cget("bg"), fg="#cdd6f4",
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

            thumb_lbl = tk.Label(card, bg="#181825")
            thumb_lbl.pack(pady=(3, 5))
            try:
                with Image.open(item.path) as src:
                    src = src.convert("RGB")
                    src.thumbnail((210, 102), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(src, master=self.window)
                    self.photos[name] = photo
                    thumb_lbl.configure(image=photo)
            except Exception:
                pass

            act_btn = tk.Button(card, text="✓ Đang chọn" if is_active else "✕ Đã bỏ qua",
                                bg="#a6e3a1" if is_active else "#f38ba8", fg="#11111b",
                                font=("Segoe UI", 8, "bold"), relief=tk.FLAT, pady=2,
                                command=lambda n=name: self.toggle_item(n))
            act_btn.pack(fill=tk.X)
            self.card_buttons[name] = act_btn

            card.grid(row=index // 4, column=index % 4, padx=5, pady=5, sticky="nsew")

        footer = tk.Frame(self.window, bg="#181825", padx=16, pady=10)
        footer.pack(fill=tk.X)
        self.summary = tk.Label(footer, text="", bg="#181825", fg="#cdd6f4")
        self.summary.pack(side=tk.LEFT)
        tk.Button(footer, text="HỦY", command=self.cancel, bg="#45475a", fg="white",
                  relief=tk.FLAT, padx=14, pady=6).pack(side=tk.RIGHT, padx=(8, 0))
        button_text = "LƯU & XEM TRƯỚC" if action == "preview" else "XÁC NHẬN & GHÉP PSD"
        tk.Button(footer, text=button_text, command=self.confirm, bg="#a6e3a1", fg="#11111b",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=14, pady=6).pack(side=tk.RIGHT)
        self.update_summary()
        self.window.grab_set()
        self.window.focus_set()
        parent.wait_window(self.window)

    def toggle_item(self, name: str) -> None:
        new_state = not self.selected_vars[name].get()
        self.selected_vars[name].set(new_state)
        card = self.cards[name]
        btn = self.card_buttons[name]
        if new_state:
            card.configure(bg="#313244")
            btn.configure(text="✓ Đang chọn", bg="#a6e3a1", fg="#11111b")
        else:
            card.configure(bg="#242432")
            btn.configure(text="✕ Đã bỏ qua", bg="#f38ba8", fg="#11111b")
        self.on_columns_changed()

    def select_all(self) -> None:
        for name, var in self.selected_vars.items():
            var.set(True)
            self.cards[name].configure(bg="#313244")
            self.card_buttons[name].configure(text="✓ Đang chọn", bg="#a6e3a1", fg="#11111b")
        self.auto_split()

    def deselect_all(self) -> None:
        for name, var in self.selected_vars.items():
            var.set(False)
            self.cards[name].configure(bg="#242432")
            self.card_buttons[name].configure(text="✕ Đã bỏ qua", bg="#f38ba8", fg="#11111b")
        self.on_columns_changed()

    def auto_split(self) -> None:
        active = sum(1 for v in self.selected_vars.values() if v.get())
        cols, rows = calculate_gun_columns_and_rows(active)
        self.columns_var.set(cols)
        self.on_columns_changed()

    def on_columns_changed(self) -> None:
        try:
            cols = max(1, min(10, self.columns_var.get()))
        except Exception:
            cols = 2
        active = sum(1 for v in self.selected_vars.values() if v.get())
        rows = math.ceil(active / cols) if active > 0 else 0
        self.rows_var.set(rows)
        self.row_display.configure(text=str(rows))
        self.update_summary()

    def update_summary(self) -> None:
        total = len(self.items)
        active = sum(1 for v in self.selected_vars.values() if v.get())
        try:
            cols = max(1, self.columns_var.get())
        except Exception:
            cols = 2
        rows = math.ceil(active / cols) if active > 0 else 0
        remainder = (cols * rows) - active
        rem_text = f" ({remainder} ô trống)" if remainder > 0 else " (chia đều không trống)"
        self.summary.configure(
            text=f"Đã chọn: {active}/{total} súng  •  Bố cục: {cols} cột x {rows} hàng{rem_text}"
        )

    def confirm(self) -> None:
        chosen = [item for item in self.items if self.selected_vars[item.path.name].get()]
        try:
            cols = max(1, min(10, self.columns_var.get()))
        except Exception:
            cols = 2
        rows = math.ceil(len(chosen) / cols) if chosen else 0
        self.result = (chosen, cols, rows)
        self.window.destroy()

    def cancel(self) -> None:
        self.result = None
        self.window.destroy()


class ComposeGUI:
    def __init__(self, root: "tk.Tk | tk.Frame", account_variable: "tk.StringVar | None" = None) -> None:
        self.root = root
        if isinstance(root, (tk.Tk, tk.Toplevel)):
            self.root.title("GHÉP ẢNH ACC THÀNH PSD - SMART OBJECT")
            self.root.geometry("940x775")
            self.root.minsize(820, 690)
        self.forms = load_forms()
        self.form_labels = {"Tự động chọn form": "auto"}
        self.form_labels.update({form["label"]: form_id for form_id, form in self.forms.items()})
        self.gun_labels = {"Không dùng bộ súng DienLV": ""}
        for info in list_dienlv_codes():
            label = (
                f"{info['code']}  —  {info['count']} ảnh  —  "
                f"{info['columns']} cột x {info['rows']} hàng"
            )
            self.gun_labels[label] = str(info["code"])

        self.account_var = account_variable if account_variable is not None else tk.StringVar()
        self.form_var = tk.StringVar(value="Tự động chọn form")
        self.gun_var = tk.StringVar(value="Không dùng bộ súng DienLV")
        self.profile_var = tk.StringVar()
        self.middle_profile_var = tk.StringVar()
        self.lobby_var = tk.StringVar()
        self.include_labels_var = tk.BooleanVar(value=False)
        self.running = False
        self._build()
        try:
            self.account_var.trace_add("write", lambda *_: self.auto_select_gun_for_account(self.account_var.get()))
        except Exception:
            pass
        if self.account_var.get():
            self.auto_select_gun_for_account(self.account_var.get())

    def _build(self) -> None:
        root = self.root
        root.configure(bg="#11111b")
        frame = tk.Frame(root, bg="#181825", padx=18, pady=16)
        frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        tk.Label(frame, text="GHÉP ẢNH ACCOUNT THÀNH PSD", font=("Segoe UI", 17, "bold"),
                 bg="#181825", fg="#89b4fa").pack(anchor="w")
        tk.Label(frame, text="Mỗi ảnh con là một Smart Object riêng, có thể thay/kéo lại trong Photoshop.",
                 font=("Segoe UI", 10), bg="#181825", fg="#bac2de").pack(anchor="w", pady=(2, 14))

        form_frame = tk.Frame(frame, bg="#181825")
        form_frame.pack(fill=tk.X)
        tk.Label(form_frame, text="Mã acc", width=16, anchor="w", bg="#181825", fg="#cdd6f4").grid(row=0, column=0, sticky="w", pady=4)
        tk.Entry(form_frame, textvariable=self.account_var, font=("Segoe UI", 11, "bold"), bg="#313244", fg="white", insertbackground="white").grid(row=0, column=1, sticky="ew", pady=4)
        tk.Button(form_frame, text="Quét ảnh", command=self.scan, bg="#89b4fa", fg="#11111b", relief=tk.FLAT).grid(row=0, column=2, padx=(8, 0), pady=4)

        tk.Label(form_frame, text="Form", width=16, anchor="w", bg="#181825", fg="#cdd6f4").grid(row=1, column=0, sticky="w", pady=4)
        self.form_combo = ttk.Combobox(form_frame, textvariable=self.form_var, values=list(self.form_labels), state="readonly")
        self.form_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)
        self.form_combo.configure(postcommand=self.refresh_form_choices)

        tk.Label(form_frame, text="Mã súng DienLV", width=16, anchor="w", bg="#181825", fg="#cdd6f4").grid(row=2, column=0, sticky="w", pady=4)
        self.gun_combo = ttk.Combobox(form_frame, textvariable=self.gun_var, values=list(self.gun_labels), state="readonly")
        self.gun_combo.grid(row=2, column=1, sticky="ew", pady=4)
        self.gun_combo.configure(postcommand=self.refresh_gun_codes)
        tk.Button(
            form_frame, text="⚡ Xếp súng", command=self.open_gun_choice_dialog,
            bg="#89b4fa", fg="#11111b", font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
        ).grid(row=2, column=2, padx=(8, 0), pady=4)
        tk.Button(
            form_frame, text="Làm mới", command=self.refresh_gun_codes,
            bg="#45475a", fg="white", relief=tk.FLAT,
        ).grid(row=2, column=3, padx=(6, 0), pady=4)

        self._path_row(form_frame, 3, "Ảnh hồ sơ (trái)", self.profile_var, self.choose_profile)
        self._path_row(form_frame, 4, "Ảnh hồ sơ (giữa)", self.middle_profile_var, self.choose_middle_profile)
        self._path_row(form_frame, 5, "Ảnh sảnh (phải)", self.lobby_var, self.choose_lobby)
        form_frame.columnconfigure(1, weight=1)

        tk.Checkbutton(
            frame, text="Kèm kho chữ/nhãn vào PSD (tùy chọn, mặc định không cần)",
            variable=self.include_labels_var, bg="#181825", fg="#cdd6f4",
            selectcolor="#313244", activebackground="#181825", activeforeground="#cdd6f4",
        ).pack(anchor="w", pady=(10, 4))

        tk.Button(
            frame, text="CẤU HÌNH THƯ MỤC", command=self.open_path_config,
            bg="#45475a", fg="white", relief=tk.FLAT, pady=5,
        ).pack(anchor="e", pady=(0, 8))

        button_frame = tk.Frame(frame, bg="#181825")
        button_frame.pack(fill=tk.X, pady=(2, 10))
        self.preview_button = tk.Button(button_frame, text="XEM TRƯỚC BỐ CỤC", command=self.preview,
                                        bg="#cba6f7", fg="#11111b", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, pady=8)
        self.preview_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.psd_button = tk.Button(button_frame, text="CHỌN NHÃN & GHÉP PSD", command=self.compose,
                                    bg="#a6e3a1", fg="#11111b", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, pady=8)
        self.psd_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        tk.Label(frame, text="NHẬT KÝ", font=("Segoe UI", 9, "bold"), bg="#181825", fg="#fab387").pack(anchor="w")
        self.log_box = tk.Text(frame, height=18, bg="#11111b", fg="#a6adc8", insertbackground="white", relief=tk.FLAT, font=("Consolas", 9), wrap=tk.WORD)
        self.log_box.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.log("Có 3 ô ảnh đầu: hồ sơ trái, hồ sơ giữa, sảnh phải. Ô nào không cần thì bấm Bỏ.")

    def _path_row(self, parent: "tk.Widget", row: int, title: str, variable: "tk.StringVar", command: Callable[[], None]) -> None:
        tk.Label(parent, text=title, width=16, anchor="w", bg="#181825", fg="#cdd6f4").grid(row=row, column=0, sticky="w", pady=4)
        tk.Entry(parent, textvariable=variable, state="readonly", readonlybackground="#313244", fg="white").grid(row=row, column=1, sticky="ew", pady=4)
        tk.Button(parent, text="Chọn...", command=command, bg="#45475a", fg="white", relief=tk.FLAT).grid(row=row, column=2, padx=(8, 0), pady=4)
        tk.Button(parent, text="Bỏ", command=lambda: variable.set(""), bg="#313244", fg="#f38ba8", relief=tk.FLAT).grid(row=row, column=3, padx=(6, 0), pady=4)

    def log(self, value: str) -> None:
        self.log_box.insert(tk.END, value + "\n")
        self.log_box.see(tk.END)

    def open_path_config(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("CẤU HÌNH THƯ MỤC")
        window.geometry("900x590")
        window.minsize(760, 540)
        window.configure(bg="#11111b")
        window.transient(self.root)

        panel = tk.Frame(window, bg="#181825", padx=18, pady=16)
        panel.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        tk.Label(
            panel, text="CẤU HÌNH ĐƯỜNG DẪN", font=("Segoe UI", 15, "bold"),
            bg="#181825", fg="#89b4fa",
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(
            panel,
            text="Có thể dùng đường dẫn tương đối tính từ thư mục GhepPSD hoặc đường dẫn đầy đủ.",
            bg="#181825", fg="#bac2de", font=("Segoe UI", 9),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

        variables = {
            key: tk.StringVar(value=_PATHS.get(key, default))
            for key, default in DEFAULT_PATHS.items()
        }

        def choose_path(key: str) -> None:
            current = variables[key].get().strip()
            try:
                resolved = _configured_path(current) if current else PROJECT_ROOT
            except (OSError, ValueError):
                resolved = PROJECT_ROOT
            if key in PATH_CONFIG_FILE_KEYS:
                initial_dir = resolved.parent if resolved.suffix else resolved
                filters = {
                    "photoshop_script": [("Photoshop JSX", "*.jsx"), ("Tất cả file", "*.*")],
                    "photoshop_bridge": [("PowerShell", "*.ps1"), ("Tất cả file", "*.*")],
                    "label_library": [("Photoshop PSD", "*.psd"), ("Tất cả file", "*.*")],
                }
                selected = filedialog.askopenfilename(
                    parent=window,
                    title=f"Chọn {PATH_CONFIG_LABELS[key].lower()}",
                    initialdir=str(initial_dir),
                    filetypes=filters[key],
                )
            else:
                initial_dir = resolved if resolved.is_dir() else resolved.parent
                selected = filedialog.askdirectory(
                    parent=window,
                    title=f"Chọn {PATH_CONFIG_LABELS[key].lower()}",
                    initialdir=str(initial_dir),
                )
            if selected:
                variables[key].set(selected)

        for index, key in enumerate(DEFAULT_PATHS, start=2):
            tk.Label(
                panel, text=PATH_CONFIG_LABELS[key], width=25, anchor="w",
                bg="#181825", fg="#cdd6f4",
            ).grid(row=index, column=0, sticky="w", pady=4)
            tk.Entry(
                panel, textvariable=variables[key], bg="#313244", fg="white",
                insertbackground="white", relief=tk.FLAT,
            ).grid(row=index, column=1, sticky="ew", pady=4, ipady=4)
            tk.Button(
                panel, text="Chọn...", command=lambda name=key: choose_path(name),
                bg="#45475a", fg="white", relief=tk.FLAT,
            ).grid(row=index, column=2, padx=(8, 0), pady=4)

        panel.columnconfigure(1, weight=1)
        button_row = 2 + len(DEFAULT_PATHS)

        def reset_defaults() -> None:
            for key, value in DEFAULT_PATHS.items():
                variables[key].set(value)

        def save_and_apply() -> None:
            try:
                save_path_config({key: variable.get() for key, variable in variables.items()})
                self._refresh_config_choices()
            except Exception as exc:
                messagebox.showerror("Không lưu được cấu hình", str(exc), parent=window)
                return
            self.log(f"Đã lưu và áp dụng cấu hình: {CONFIG_PATH}")
            messagebox.showinfo(
                "Đã áp dụng",
                "Đã lưu config.json và nạp lại danh sách form, mã súng.",
                parent=window,
            )
            window.destroy()

        buttons = tk.Frame(panel, bg="#181825")
        buttons.grid(row=button_row, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        tk.Button(
            buttons, text="ĐẶT LẠI MẶC ĐỊNH", command=reset_defaults,
            bg="#45475a", fg="white", relief=tk.FLAT, pady=7,
        ).pack(side=tk.LEFT)
        tk.Button(
            buttons, text="LƯU & ÁP DỤNG", command=save_and_apply,
            bg="#a6e3a1", fg="#11111b", font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, pady=7, padx=20,
        ).pack(side=tk.RIGHT)

        window.grab_set()
        window.focus_set()

    def _refresh_config_choices(self) -> None:
        self.refresh_form_choices()
        self.refresh_gun_codes()

    def refresh_form_choices(self) -> None:
        current_form_id = self.form_labels.get(self.form_var.get(), "auto")

        self.forms = load_forms()
        self.form_labels = {"Tự động chọn form": "auto"}
        self.form_labels.update({form["label"]: form_id for form_id, form in self.forms.items()})
        self.form_combo.configure(values=list(self.form_labels))
        form_label = next(
            (label for label, form_id in self.form_labels.items() if form_id == current_form_id),
            "Tự động chọn form",
        )
        self.form_var.set(form_label)

    def refresh_gun_codes(self) -> None:
        current_gun_code = self.gun_labels.get(self.gun_var.get(), "")
        _DIENLV_GUN_CACHE.clear()
        self.gun_labels = {"Không dùng bộ súng DienLV": ""}
        for info in list_dienlv_codes():
            label = (
                f"{info['code']}  —  {info['count']} ảnh  —  "
                f"{info['columns']} cột x {info['rows']} hàng"
            )
            self.gun_labels[label] = str(info["code"])
        self.gun_combo.configure(values=list(self.gun_labels))
        gun_label = next(
            (label for label, code in self.gun_labels.items() if code == current_gun_code),
            "Không dùng bộ súng DienLV",
        )
        self.gun_var.set(gun_label)

    def _set_running(self, value: bool) -> None:
        self.running = value
        state = tk.DISABLED if value else tk.NORMAL
        self.preview_button.configure(state=state)
        self.psd_button.configure(state=state)

    def choose_profile(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(INPUT_DIR), title="Chọn ảnh hồ sơ bên trái", filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self.profile_var.set(path)

    def choose_middle_profile(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(INPUT_DIR), title="Chọn ảnh hồ sơ ở giữa", filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self.middle_profile_var.set(path)

    def choose_lobby(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(INPUT_DIR), title="Chọn ảnh sảnh bên phải", filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self.lobby_var.set(path)

    def auto_select_gun_for_account(self, account: str) -> None:
        clean_acc = str(account or "").strip()
        if not clean_acc:
            return
        self.refresh_gun_codes()
        matched_label = None
        for label, code in self.gun_labels.items():
            if code.casefold() == clean_acc.casefold():
                matched_label = label
                break
        if matched_label:
            self.gun_var.set(matched_label)

    def scan(self) -> None:
        try:
            account = validate_account_id(self.account_var.get())
            categories = scan_account_output(account)
            profile, lobby, candidates = find_lobby_sources(INPUT_DIR)
        except ComposeError as exc:
            messagebox.showerror("Không quét được", str(exc))
            return
        self.auto_select_gun_for_account(account)
        self.profile_var.set(str(profile))
        self.lobby_var.set(str(lobby))
        self.log_box.delete("1.0", tk.END)
        self.log(f"Acc {account}: " + ", ".join(f"{key}={len(value)}" for key, value in categories.items() if value))
        gun_code = self.gun_labels.get(self.gun_var.get(), "")
        if gun_code:
            gun_info = next((info for info in list_dienlv_codes() if info["code"] == gun_code), None)
            if gun_info:
                self.log(
                    f"Súng DienLV {gun_code}: {gun_info['count']} ảnh lẻ, "
                    f"giữ bố cục {gun_info['columns']} cột x {gun_info['rows']} hàng."
                )
        self.log(f"Ứng viên ảnh lớn: {len(candidates)}. Đã chọn trái={profile.name}, phải={lobby.name}; ô giữa để bạn chọn.")
        self.log("Nếu ảnh chưa đúng, dùng Chọn... để đổi hoặc Bỏ để không ghép ô đó.")

    def _choose_guns(self, account: str, action: str) -> tuple[list[SourceImage], int, int] | None:
        categories = scan_account_output(account)
        guns = list(categories["sung"])
        gun_code = self.gun_labels.get(self.gun_var.get(), "") or None
        if gun_code:
            try:
                dienlv_set = load_dienlv_guns(gun_code)
                guns = list(dienlv_set.items)
            except Exception:
                pass

        if not guns:
            return None

        saved_excluded, saved_cols = load_gun_choices(account, guns)
        dialog = GunChoiceDialog(self.root, guns, saved_excluded, saved_cols, action)
        if dialog.result is None:
            return None

        chosen_items, chosen_cols, chosen_rows = dialog.result
        all_names = {item.path.name for item in guns}
        chosen_names = {item.path.name for item in chosen_items}
        excluded = all_names - chosen_names
        save_gun_choices(account, excluded, chosen_cols)
        self.log(f"Bố cục súng {account}: chọn {len(chosen_items)}/{len(guns)} súng -> {chosen_cols} cột x {chosen_rows} hàng.")
        return dialog.result

    def open_gun_choice_dialog(self) -> None:
        try:
            account = validate_account_id(self.account_var.get())
        except Exception:
            messagebox.showwarning("Chưa nhập mã acc", "Vui lòng nhập Mã acc trước khi xếp súng.")
            return
        res = self._choose_guns(account, "preview")
        if res:
            messagebox.showinfo("Đã lưu bố cục súng", f"Đã lưu: {len(res[0])} súng, bố cục {res[1]} cột x {res[2]} hàng.")

    def _choose_outfits(self, account: str, action: str) -> dict[str, str] | None:
        categories = scan_account_output(account)
        items = categories["tp"]
        if not items:
            return {}
        ensure_outfit_label_assets()
        saved = load_outfit_choices(account, items)
        dialog = OutfitChoiceDialog(self.root, items, saved, action)
        if dialog.result is None:
            return None
        return dialog.result

    def _choose_vehicles(self, account: str, action: str) -> dict[str, str] | None:
        categories = scan_account_output(account)
        items = categories["xe"]
        if not items:
            return {}
        ensure_vehicle_label_assets()
        ensure_outfit_label_assets()
        saved = load_vehicle_choices(account, items)
        dialog = VehicleChoiceDialog(self.root, items, saved, action)
        return dialog.result

    def _choose_labels(self, account: str, action: str) -> tuple[dict[str, str], dict[str, str], tuple[list[SourceImage], int, int] | None] | None:
        categories = scan_account_output(account)
        gun_code = self.gun_labels.get(self.gun_var.get(), "") or None
        has_guns = bool(categories["sung"] or gun_code)
        gun_result = None
        if has_guns:
            gun_result = self._choose_guns(account, action)
            if gun_result is None:
                return None
        outfit_choices = self._choose_outfits(account, action)
        if outfit_choices is None:
            return None
        vehicle_choices = self._choose_vehicles(account, action)
        if vehicle_choices is None:
            return None
        if categories["tp"]:
            save_outfit_choices(account, categories["tp"], outfit_choices)
        if categories["xe"]:
            save_vehicle_choices(account, categories["xe"], vehicle_choices)
        self.log(f"Đã lưu nhãn cho {len(categories['tp'])} trang phục và {len(categories['xe'])} xe.")
        return outfit_choices, vehicle_choices, gun_result

    def _prepare(self, outfit_choices: dict[str, str] | None = None,
                 vehicle_choices: dict[str, str] | None = None,
                 gun_result: tuple[list[SourceImage], int, int] | None = None) -> dict[str, Any]:
        account = validate_account_id(self.account_var.get())
        profile = Path(self.profile_var.get()) if self.profile_var.get() else None
        middle_profile = Path(self.middle_profile_var.get()) if self.middle_profile_var.get() else None
        lobby = Path(self.lobby_var.get()) if self.lobby_var.get() else None
        form_id = self.form_labels[self.form_var.get()]
        gun_code = self.gun_labels.get(self.gun_var.get(), "") or None
        if gun_code:
            self.log(f"Đang đọc đúng thứ tự level của bộ súng {gun_code}...")
        plan, categories, profile, lobby = prepare_plan(
            account,
            form_id,
            profile,
            lobby,
            self.include_labels_var.get(),
            gun_code,
            middle_profile_path=middle_profile,
            auto_detect_headers=False,
            outfit_choices=outfit_choices,
            vehicle_choices=vehicle_choices,
            gun_choices=gun_result,
        )
        self.profile_var.set(str(profile) if profile else "")
        self.lobby_var.set(str(lobby) if lobby else "")
        selected_header_slots = sum(1 for slot in plan["header_slots"] if slot["selected"])
        self.log(f"Hàng đầu: {selected_header_slots} ảnh được chia đều toàn bộ chiều ngang.")
        self.log(f"Form: {plan['form_id']} | Canvas: {plan['canvas']['width']} x {plan['canvas']['height']} | {len(plan['placements'])} ảnh")
        if plan.get("dienlv_guns"):
            info = plan["dienlv_guns"]
            self.log(
                f"Đã xếp {info['count']} súng từ {info['code']} thành "
                f"{info['columns']} cột x {info['rows']} hàng; mỗi ô là Smart Object riêng."
            )
        inventory_info = plan.get("inventory_layout") or {}
        if inventory_info.get("count"):
            self.log(
                f"Kho: {inventory_info['count']} ảnh nguồn nguyên vẹn; không cắt nhỏ, "
                f"mỗi file là một Smart Object chọn riêng."
            )
        outfit_grid = plan.get("outfit_grid") or {}
        if outfit_grid.get("count"):
            status = "đúng mẫu" if outfit_grid.get("preset_matched") else "bố cục mặc định"
            self.log(
                f"Trang phục: {outfit_grid['count']} ảnh = {outfit_grid['rows']} hàng x "
                f"{outfit_grid['columns']} cột ({status}); mỗi ảnh chọn riêng."
            )
        vehicle_labels = sum(placement["category"] == "vehicle_label"
                             for placement in plan["placements"])
        if vehicle_labels:
            self.log(f"Xe: đã đặt {vehicle_labels} nhãn vé/VIP ở góc dưới bên trái.")
        small_layout = plan.get("small_account_layout") or {}
        if small_layout:
            self.log(
                f"Mẫu 736: {small_layout['rail_rows']} hàng súng cạnh xe/item, "
                f"{small_layout['bottom_gun_rows']} hàng súng dồn xuống dưới; "
                f"cao {small_layout['row_height']} px/hàng, giới hạn giãn/nén "
                f"{small_layout['max_vertical_stretch_percent']}%."
            )
        return plan

    def preview(self) -> None:
        if self.running:
            return
        try:
            account = validate_account_id(self.account_var.get())
            choices = self._choose_labels(account, "preview")
            if choices is None:
                return
            preview_folder = TEMP_DIR / "preview" / account
            plan = self._prepare(*choices)
            path = render_preview(plan, preview_folder / "xem_truoc.jpg")
            save_plan(plan, preview_folder / "layout.json")
            self.log(f"Đã tạo ảnh xem trước: {path}")
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Không tạo được preview", str(exc))

    def compose(self) -> None:
        if self.running:
            return
        try:
            account = validate_account_id(self.account_var.get())
            choices = self._choose_labels(account, "compose")
            if choices is None:
                return
            out_folder = create_run_folder(account)
            plan = self._prepare(*choices)
            run_files = choose_run_files(account, out_folder)
            render_preview(plan, run_files.preview)
        except Exception as exc:
            messagebox.showerror("Chưa thể ghép", str(exc))
            return
        self._set_running(True)

        def worker() -> None:
            try:
                result = run_photoshop(
                    plan, out_folder,
                    lambda value: self.root.after(0, self.log, value),
                    run_files,
                )
            except Exception as exc:
                self.root.after(0, self._finish_error, str(exc))
                return
            self.root.after(0, self._finish_ok, result)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_error(self, detail: str) -> None:
        self._set_running(False)
        self.log("LỖI: " + detail)
        messagebox.showerror("Ghép PSD thất bại", detail)

    def _finish_ok(self, result: tuple[Path, Path, Path]) -> None:
        self._set_running(False)
        psd, png, layout = result
        self.log(f"Hoàn tất: {psd}")
        messagebox.showinfo(
            "Đã ghép xong",
            f"File nằm trực tiếp trong thư mục mã acc.\n\n"
            f"Kết quả: {psd.parent}\n\nFile PSD đang mở trong Photoshop.",
        )
        os.startfile(psd.parent)


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ghép ảnh acc thành PSD nhiều Smart Object")
    parser.add_argument("--account", "-a", help="Mã acc; bỏ trống để mở giao diện")
    parser.add_argument("--form", default="auto", help="auto, classic_compact hoặc classic_wide")
    parser.add_argument("--profile", type=Path, help="Ảnh hồ sơ bên trái")
    parser.add_argument("--middle-profile", type=Path, help="Ảnh hồ sơ ở giữa (tùy chọn)")
    parser.add_argument("--lobby", type=Path, help="Ảnh sảnh bên phải")
    parser.add_argument("--gun-code", help="Mã thư mục súng trong DienLV\\standalone, ví dụ HUQ2MQQ7YU")
    parser.add_argument("--preview-only", action="store_true", help="Chỉ tạo preview, không mở Photoshop")
    parser.add_argument(
        "--include-label-library", action="store_true",
        help="Chép kho chữ vào một group ẩn; mặc định tự ghép nhãn bằng file mẫu riêng",
    )
    args = parser.parse_args(argv)

    if not args.account:
        if tk is None:
            parser.error("Python hiện tại không có Tkinter; hãy dùng --account.")
        root = tk.Tk()
        ComposeGUI(root)
        root.mainloop()
        return 0

    try:
        account = validate_account_id(args.account)
        gun_code = args.gun_code
        if not gun_code:
            try:
                _dienlv_source_paths(account)
                gun_code = account
            except ComposeError:
                gun_code = None
        plan, _, profile, lobby = prepare_plan(
            args.account,
            args.form,
            args.profile,
            args.lobby,
            args.include_label_library,
            gun_code,
            middle_profile_path=args.middle_profile,
        )
        print(f"Ảnh trái: {profile.name if profile else '(trống)'}")
        middle_slot = plan["header_slots"][1]
        print(f"Ảnh giữa: {Path(middle_slot['path']).name if middle_slot['selected'] else '(trống)'}")
        print(f"Ảnh phải: {lobby.name if lobby else '(trống)'}")
        print(f"Form: {plan['form_id']} - {plan['canvas']['width']}x{plan['canvas']['height']}")
        if plan.get("dienlv_guns"):
            info = plan["dienlv_guns"]
            print(f"Súng DienLV: {info['code']} - {info['count']} ảnh - {info['columns']} cột")
        outfit_grid = plan.get("outfit_grid") or {}
        if outfit_grid.get("count"):
            print(
                f"Trang phục: {outfit_grid['count']} ảnh - "
                f"{outfit_grid['rows']} hàng x {outfit_grid['columns']} cột"
            )
        if args.preview_only:
            folder = TEMP_DIR / "preview" / account
            path = render_preview(plan, folder / "xem_truoc.jpg")
            save_plan(plan, folder / "layout.json")
            print(f"Preview: {path}")
        else:
            folder = create_run_folder(account)
            run_files = choose_run_files(account, folder)
            render_preview(plan, run_files.preview)
            psd, png, layout = run_photoshop(plan, folder, run_files=run_files)
            print(f"Thư mục mã acc: {folder}\nPSD: {psd}\nPNG: {png}\nLayout: {layout}")
        return 0
    except ComposeError as exc:
        print(f"[LỖI] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli_main())
