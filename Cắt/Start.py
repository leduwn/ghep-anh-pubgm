#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HỆ THỐNG ĐỒNG BỘ PHÂN LOẠI & CẮT ẢNH TỰ ĐỘNG THEO MÃ TÀI KHOẢN (ALL-IN-ONE MASTER DASHBOARD)
===========================================================================================
Bản đồ phân loại màn hình PUBG Mobile:
1. XƯỞNG SÚNG (Gun Lab) ➔ SUNG
2. TAB CHÍNH DỌC BÊN PHẢI (X: 2530..2600):
   - Tab 1 (y: 0..300)      : TRANG PHỤC (Outfit / Set / Mũ / Balo / Mặt Nạ / Đồ)
   - Tab 2 (y: 300..475)    : SÚNG (Gun / Weapons, đang tắt tool cắt)
   - Tab 3 (y: 475..665)    : XE (Vehicles)
   - Tab 4 (y: 665..900)    : HÀNH ĐỘNG / LỰU ĐẠN
   - Tab 5 (y: 900..1150)   : ITEM / KHÁC (Item Box / Materials / Gems / Vouchers)
   - Tab 6 (y: 1150..1284)  : LINH THÚ / KHÁC
"""

import os
import sys
import glob
import time
import shutil
import argparse
import threading
from typing import List, Tuple, Optional, Dict

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = (
    os.path.join(PROJECT_ROOT, "tool")
    if os.path.isdir(os.path.join(PROJECT_ROOT, "tool"))
    else os.path.join(PROJECT_ROOT, "Cắt")
)
SOURCE_INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
GLOBAL_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
ENABLE_GUN_TOOL = True  # Bật module Cắt Súng (Xưởng Nâng Cấp - DienLV)
SOURCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
INVALID_ACCOUNT_CHARS = set('<>:"/\\|?*')
RESERVED_ACCOUNT_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Súng"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Trang Phục"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Đồ"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Xe"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Mũ"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Balo"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Mặt Nạ"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Lựu Đạn"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Dù"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Hành Động"))
sys.path.insert(0, os.path.join(TOOLS_DIR, "Cắt Item"))

catsung = None
if ENABLE_GUN_TOOL:
    try:
        import catsung
    except Exception:
        catsung = None

try:
    import cattrangphuc
except Exception:
    cattrangphuc = None

try:
    import catdo
except Exception:
    catdo = None

try:
    import catxe
except Exception:
    catxe = None

try:
    import catmu
except Exception:
    catmu = None

try:
    import catbalo
except Exception:
    catbalo = None

try:
    import catmatna
except Exception:
    catmatna = None

try:
    import catluudan
except Exception:
    catluudan = None

try:
    import catdu
except Exception:
    catdu = None

try:
    import cathanhdong
except Exception:
    cathanhdong = None

try:
    import catitem
except Exception:
    catitem = None


# ==============================================================================
# HÀM XỬ LÝ ẢNH UNICODE TRÊN WINDOWS
# ==============================================================================
def cv2_imread_utf8(path: str) -> Optional[np.ndarray]:
    try:
        if not os.path.exists(path):
            return None
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[Lỗi đọc ảnh] {path}: {e}")
        return None


def cv2_imwrite_utf8(path: str, img: np.ndarray, quality: int = 95) -> bool:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        elif ext == '.webp':
            params = [int(cv2.IMWRITE_WEBP_QUALITY), quality]
        else:
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]

        success, buf = cv2.imencode(ext if ext else '.png', img, params)
        if success:
            buf.tofile(path)
            return True
        return False
    except Exception as e:
        print(f"[Lỗi ghi ảnh] {path}: {e}")
        return False


# ==============================================================================
# BỘ NHẬN DIỆN PHÂN LOẠI ẢNH TỰ ĐỘNG CHUẨN XÁC THEO TỪNG TAB
# ==============================================================================
class ImageClassifier:
    """
    Phân tích vị trí thanh Tab dọc bên phải (X: 2520..2620):
    - Tab 1 (y: 0..300)      : TRANG PHỤC / KHO ĐỒ
    - Tab 2 (y: 300..475)    : SÚNG (Gun)
    - Tab 3 (y: 475..665)    : XE (Vô lăng)
    - Tab 4 (y: 665..900)    : HÀNH ĐỘNG / LỰU ĐẠN
    - Tab 5 (y: 900..1150)   : ITEM (Hộp đồ)
    - Tab 6 (y: 1150..1284)  : LINH THÚ / KHÁC
    """

    @staticmethod
    def is_gun_lab_screen(img: np.ndarray) -> bool:
        """Nhận diện màn hình Xưởng Nâng Cấp Súng (Gun Lab)."""
        if img is None:
            return False

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        top_right = img[int(30 * scale_y):int(110 * scale_y), int(2300 * scale_x):int(2550 * scale_x)]
        has_xuong_txt = False
        if top_right.size > 0:
            has_xuong_txt = np.sum(cv2.cvtColor(top_right, cv2.COLOR_BGR2GRAY) > 200) > int(600 * (scale_x * scale_y))

        roi_daco = img[int(90 * scale_y):int(180 * scale_y), int(2120 * scale_x):int(2300 * scale_x)]
        has_daco = False
        if roi_daco.size > 0:
            hsv_daco = cv2.cvtColor(roi_daco, cv2.COLOR_BGR2HSV)
            orange = cv2.inRange(hsv_daco, np.array([5, 120, 100]), np.array([30, 255, 255]))
            has_daco = np.sum(orange > 0) > int(120 * (scale_x * scale_y))

        center_roi = img[
            int(180 * scale_y):int(1100 * scale_y),
            int(50 * scale_x):int(1650 * scale_x),
        ]
        has_dark_workshop = (
            center_roi.size > 0
            and float(np.mean(cv2.cvtColor(center_roi, cv2.COLOR_BGR2GRAY))) < 140.0
        )

        # Nút vàng Nâng Cấp ở góc dưới trái (y: 1100..1260, x: 50..550)
        roi_btn = img[int(1100 * scale_y):int(1260 * scale_y), int(50 * scale_x):int(550 * scale_x)]
        has_yellow_btn = False
        if roi_btn.size > 0:
            hsv_btn = cv2.cvtColor(roi_btn, cv2.COLOR_BGR2HSV)
            yellow = cv2.inRange(hsv_btn, np.array([12, 100, 100]), np.array([38, 255, 255]))
            has_yellow_btn = np.sum(yellow > 0) > int(300 * (scale_x * scale_y))

        # Một số màn Xưởng không có nút vàng ở dưới (đã max cấp); hoặc hiệu ứng
        # súng phát sáng mạnh (như Thiên Mã - P90) đẩy độ sáng trung bình lên cao.
        return has_xuong_txt and has_daco and (has_dark_workshop or has_yellow_btn)

    @staticmethod
    def is_appearance_screen(img: np.ndarray) -> bool:
        """Nhận diện màn hình Ngoại hình (Kiểu tóc / Khuôn mặt)."""
        if img is None or img.size == 0 or img.shape[1] < img.shape[0] * 1.7:
            return False
        if catitem:
            try:
                return catitem.HairstyleFilter.is_hair_screen(img)
            except Exception:
                pass
        return False

    @staticmethod
    def _find_blue_indicator_y(
        blue_mask: np.ndarray,
        x1: int,
        x2: int,
        scale_x: float,
        scale_y: float,
    ) -> Optional[float]:
        """Tìm tâm thanh xanh dọc đang chọn, bỏ qua icon màu xanh nhỏ."""
        mask_h, mask_w = blue_mask.shape[:2]
        sx1 = max(0, min(mask_w, int(round(x1 * scale_x))))
        sx2 = max(sx1 + 1, min(mask_w, int(round(x2 * scale_x))))
        strip = (blue_mask[:mask_h, sx1:sx2] > 0).astype(np.uint8)
        if strip.size == 0:
            return None

        count, _, stats, centers = cv2.connectedComponentsWithStats(strip, connectivity=8)
        min_height = max(18, int(round(42 * scale_y)))
        min_area = max(24, int(round(65 * scale_x * scale_y)))
        candidates = []

        for index in range(1, count):
            _, _, comp_w, comp_h, area = stats[index]
            if comp_h < min_height or area < min_area:
                continue

            slender_bonus = comp_h / max(1.0, float(comp_w))
            score = float(area) * min(8.0, slender_bonus) * float(comp_h)
            candidates.append((score, float(centers[index][1]) / scale_y))

        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    @staticmethod
    def _blue_indicator_masks(hsv: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Tạo mask chính và mask dự phòng cho vạch chọn màu xanh.

        Ảnh JPG, màn hình HDR và một số phông nền làm vạch xanh nhạt đi khá
        nhiều. Mask dự phòng chỉ được dùng khi mask chính không tìm thấy vạch;
        cấu trúc màn hình sẽ được kiểm tra thêm trước khi phân loại.
        """
        strict = cv2.inRange(
            hsv,
            np.array([100, 120, 120], dtype=np.uint8),
            np.array([130, 255, 255], dtype=np.uint8),
        )
        relaxed = cv2.inRange(
            hsv,
            np.array([92, 65, 75], dtype=np.uint8),
            np.array([142, 255, 255], dtype=np.uint8),
        )
        return strict, relaxed

    @staticmethod
    def _find_indicator_with_fallback(
        strict_mask: np.ndarray,
        relaxed_mask: np.ndarray,
        x1: int,
        x2: int,
        scale_x: float,
        scale_y: float,
    ) -> Optional[float]:
        indicator_y = ImageClassifier._find_blue_indicator_y(
            strict_mask, x1, x2, scale_x, scale_y
        )
        if indicator_y is None:
            indicator_y = ImageClassifier._find_blue_indicator_y(
                relaxed_mask, x1, x2, scale_x, scale_y
            )
        return indicator_y

    @staticmethod
    def _fast_inventory_grid_score(img: np.ndarray) -> float:
        """Đo nhanh nhịp ba hàng thẻ trên bản thu nhỏ 1/4 kích thước."""
        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        x1 = max(0, int(round(1718 * scale_x)))
        x2 = min(width, int(round(2411 * scale_x)))
        grid = img[:, x1:x2]
        if grid.size == 0:
            return 0.0

        gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(
            gray,
            None,
            fx=0.25,
            fy=0.25,
            interpolation=cv2.INTER_AREA,
        ).astype(np.float32)
        if small.shape[0] < 2:
            return 0.0
        row_change = np.mean(np.abs(np.diff(small, axis=0)), axis=1)

        slot_h = max(12, int(round(250 * scale_y * 0.25)))
        step_y = max(slot_h + 1, int(round(267 * scale_y * 0.25)))
        min_y = int(round(190 * scale_y * 0.25))
        bottom_limit = small.shape[0] - 2
        best_score = 0.0

        for phase in range(step_y):
            rows = [
                y for y in range(phase, small.shape[0], step_y)
                if y >= min_y and y + slot_h <= bottom_limit
            ]
            if len(rows) < 2:
                continue

            boundary_scores = []
            for top_y in rows:
                top_band = row_change[
                    max(0, top_y - 1):min(len(row_change), top_y + 2)
                ]
                bottom_y = top_y + slot_h - 1
                bottom_band = row_change[
                    max(0, bottom_y - 1):min(len(row_change), bottom_y + 2)
                ]
                if top_band.size and bottom_band.size:
                    boundary_scores.append(
                        float(np.max(top_band) + np.max(bottom_band))
                    )

            if len(boundary_scores) >= 2:
                score = float(
                    np.median(boundary_scores) + 0.25 * np.mean(boundary_scores)
                )
                best_score = max(best_score, score)

        return best_score

    @staticmethod
    def has_wardrobe_inventory_layout(img: np.ndarray) -> bool:
        """Kiểm tra đúng cấu trúc lưới Kho Đồ, không chỉ dựa vào một vạch xanh.

        Sảnh, hồ sơ người chơi và màn bộ sưu tập đôi khi cũng có vạch xanh ở
        cùng tọa độ. Kho Đồ thật có lưới thẻ ba cột và một thanh mục con khá
        phẳng ở sát bên phải lưới; kết hợp hai dấu hiệu giúp chặn các màn giả.
        """
        if img is None or img.size == 0:
            return False

        height, width = img.shape[:2]
        if width < height * 1.7:
            return False

        scale_x = width / 2778.0
        scale_y = height / 1284.0
        rail_x1 = max(0, int(round(2390 * scale_x)))
        rail_x2 = min(width, int(round(2495 * scale_x)))
        rail = img[:, rail_x1:rail_x2]
        if rail.size == 0 or rail.shape[0] < 2:
            return False

        rail_gray = cv2.cvtColor(rail, cv2.COLOR_BGR2GRAY).astype(np.float32)
        row_change = np.mean(np.abs(np.diff(rail_gray, axis=0)), axis=1)
        # Thanh mục con của Kho Đồ ít nhiễu; sảnh trưng bày có nhiều vật thể,
        # khung súng và chữ chạy cắt ngang dải này nên percentile tăng rõ rệt.
        # Ảnh độ phân giải thấp có biên đậm hơn sau khi co, nên nới nhẹ theo tỉ lệ.
        rail_limit = 14.0 + max(0.0, min(6.0, (1.0 / max(scale_y, 0.25) - 1.0) * 4.0))
        if float(np.percentile(row_change, 95)) > rail_limit:
            return False

        return ImageClassifier._fast_inventory_grid_score(img) >= 45.0

    @staticmethod
    def has_backpack_level_selector(img: np.ndarray) -> bool:
        """Nhận cụm ba ô chọn Balo cấp 1/2/3 ở cạnh trái lưới vật phẩm."""
        if img is None or img.size == 0:
            return False

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        x1 = max(0, int(round(1110 * scale_x)))
        x2 = min(width, int(round(1260 * scale_x)))
        y1 = max(0, int(round(60 * scale_y)))
        y2 = min(height, int(round(560 * scale_y)))
        selector = img[y1:y2, x1:x2]
        if selector.size == 0 or selector.shape[0] < 2:
            return False

        selector_gray = cv2.cvtColor(selector, cv2.COLOR_BGR2GRAY).astype(np.float32)
        row_change = np.mean(np.abs(np.diff(selector_gray, axis=0)), axis=1)
        return (
            float(np.std(selector)) >= 32.0
            and float(np.max(row_change)) >= 42.0
            and float(np.percentile(row_change, 95)) >= 5.5
        )

    @staticmethod
    def is_backpack_inventory_screen(
        img: np.ndarray,
        selected_subtab_y: Optional[float] = None,
        has_wardrobe_layout: Optional[bool] = None,
    ) -> bool:
        """Nhận Balo theo nội dung, chịu được việc thanh danh mục bị cuộn.

        Vị trí Balo thực tế trong dữ liệu dao động từ y~802 đến y~1208, nên
        không thể dùng một khoảng y hẹp. Cụm chọn ba cấp là dấu hiệu ổn định để
        phân biệt Balo với Mặt Nạ, kính và các mục quần áo ở gần đó.
        """
        if selected_subtab_y is None or selected_subtab_y < 760.0:
            return False
        if has_wardrobe_layout is None:
            has_wardrobe_layout = ImageClassifier.has_wardrobe_inventory_layout(img)
        return (
            has_wardrobe_layout
            and ImageClassifier.has_backpack_level_selector(img)
        )

    @staticmethod
    def has_item_detail_popup(img: np.ndarray) -> bool:
        """Nhận diện bảng thông tin chi tiết vật phẩm ở bên trái lưới trang phục.

        Màu tiêu đề có thể đỏ, vàng hoặc tím. Phần thân của bảng luôn là một
        hình chữ nhật sáng, ít bão hòa màu ở vị trí cố định phía dưới màn hình.
        Hai cạnh dọc của cả bảng phải đồng thời tồn tại; điều kiện này chặn
        cảnh nền, xe và nhân vật có màu vô tình giống dải tiêu đề.
        """
        if img is None:
            return False

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0

        # Bảng popup có hai cạnh dọc kéo dài ổn định tại x≈1325 và x≈1685.
        # Trước đây chỉ dò màu nên nền sân/xe màu đỏ ở đúng khu vực này khiến
        # ảnh Trang Phục thường bị đưa nhầm vào Cắt Đồ.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        edge_y1 = max(0, int(round(930 * scale_y)))
        edge_y2 = min(height, int(round(1240 * scale_y)))
        edge_radius = max(2, int(round(5 * scale_x)))
        frame_edge_scores = []
        for base_x in (1325, 1685):
            x = int(round(base_x * scale_x))
            band_x1 = max(0, x - edge_radius)
            band_x2 = min(width, x + edge_radius + 1)
            edge_band = gray[edge_y1:edge_y2, band_x1:band_x2]
            if edge_band.shape[0] < 2 or edge_band.shape[1] < 2:
                return False
            frame_edge_scores.append(float(np.mean(np.abs(np.diff(edge_band, axis=1)))))

        # Ảnh thu nhỏ làm biên sắc hơn theo đơn vị pixel, vì vậy ngưỡng được
        # tăng theo tỉ lệ thay vì dùng một số cố định. Không dùng màu thân bảng
        # vì vàng/đỏ/tím và nền xuyên thấu thay đổi theo từng acc.
        resolution_factor = max(1.0, max(scale_y, 0.25) ** -0.80)
        edge_threshold = 2.82 * resolution_factor
        return min(frame_edge_scores) >= edge_threshold

    @staticmethod
    def has_3_slot_item_grid(img: np.ndarray) -> bool:
        """Tên tương thích cũ: chỉ có bảng chi tiết mới được đưa vào Cắt Đồ."""
        return ImageClassifier.has_item_detail_popup(img)

    @staticmethod
    def _inventory_card_grid_metrics(img: np.ndarray) -> Tuple[float, int, int]:
        """Đo lưới thẻ 3 cột của màn Hành Động/Item.

        Trả về ``(điểm_mép_lưới, số_thẻ, số_thẻ_giống_emoji)``. Việc kiểm tra
        cấu trúc lưới ngăn một vạch xanh hoặc icon xanh ngẫu nhiên khiến ảnh
        của tab khác bị chuyển nhầm vào tool cắt.
        """
        if img is None or img.size == 0:
            return 0.0, 0, 0

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        slot_h = max(80, int(round(250 * scale_y)))
        step_y = max(slot_h + 4, int(round(267 * scale_y)))
        min_full_y = int(round(190 * scale_y))
        bottom_limit = height - max(8, int(round(10 * scale_y)))
        search_radius = max(2, int(round(4 * scale_y)))

        inner_ranges = [
            (1730, 1927),
            (1967, 2164),
            (2203, 2399),
        ]
        strips = []
        for x1, x2 in inner_ranges:
            sx1 = max(0, int(round(x1 * scale_x)))
            sx2 = min(width, int(round(x2 * scale_x)))
            if sx2 > sx1:
                strips.append(img[:, sx1:sx2])
        if not strips:
            return 0.0, 0, 0

        gray = cv2.cvtColor(np.concatenate(strips, axis=1), cv2.COLOR_BGR2GRAY)
        row_diff = np.mean(
            np.abs(np.diff(gray.astype(np.float32), axis=0)), axis=1
        )

        best_score = -1.0
        best_rows: List[int] = []
        for phase in range(step_y):
            rows = [
                y for y in range(phase, height, step_y)
                if y >= min_full_y and y + slot_h <= bottom_limit
            ]
            if len(rows) < 2:
                continue

            boundary_scores = []
            for top_y in rows:
                top_band = row_diff[
                    max(0, top_y - search_radius):
                    min(len(row_diff), top_y + search_radius + 1)
                ]
                bottom_y = top_y + slot_h - 1
                bottom_band = row_diff[
                    max(0, bottom_y - search_radius):
                    min(len(row_diff), bottom_y + search_radius + 1)
                ]
                if top_band.size and bottom_band.size:
                    boundary_scores.append(float(np.max(top_band) + np.max(bottom_band)))

            if len(boundary_scores) < 2:
                continue
            score = float(np.median(boundary_scores) + 0.25 * np.mean(boundary_scores))
            if score > best_score:
                best_score = score
                best_rows = rows

        if best_score < 30.0 or not best_rows:
            return max(0.0, best_score), 0, 0

        cols_base = [(1718, 1939), (1955, 2176), (2191, 2411)]
        cols = [
            (int(round(x1 * scale_x)), int(round(x2 * scale_x)))
            for x1, x2 in cols_base
        ]
        card_count = 0
        emote_count = 0

        for nominal_y in best_rows:
            lo = max(0, nominal_y - search_radius)
            hi = min(len(row_diff), nominal_y + search_radius + 1)
            top_y = lo + int(np.argmax(row_diff[lo:hi]))
            if top_y + slot_h > bottom_limit:
                continue

            margin_x = max(1, int(round(5 * scale_x)))
            margin_y = max(1, int(round(5 * scale_y)))
            for left, right in cols:
                raw = img[top_y:top_y + slot_h, left:right]
                if raw.size == 0 or float(np.std(raw)) < 16.0:
                    continue
                hsv_card = cv2.cvtColor(raw, cv2.COLOR_BGR2HSV)
                sat = hsv_card[:, :, 1]
                val = hsv_card[:, :, 2]
                if float(np.mean((val < 185) | (sat > 45))) < 0.55:
                    continue

                card_count += 1
                inner = hsv_card[
                    margin_y:max(margin_y + 1, hsv_card.shape[0] - margin_y),
                    margin_x:max(margin_x + 1, hsv_card.shape[1] - margin_x),
                ]
                hue = inner[:, :, 0]
                inner_sat = inner[:, :, 1]
                inner_val = inner[:, :, 2]
                white_ratio = float(np.mean((inner_sat <= 75) & (inner_val >= 180)))
                red_ratio = float(np.mean(
                    ((hue <= 15) | (hue >= 160))
                    & (inner_sat >= 55)
                    & (inner_val >= 55)
                ))
                purple_ratio = float(np.mean(
                    (hue >= 145)
                    & (hue <= 175)
                    & (inner_sat >= 45)
                    & (inner_val >= 55)
                ))
                if white_ratio >= 0.07 and max(red_ratio, purple_ratio) >= 0.45:
                    emote_count += 1

        return best_score, card_count, emote_count

    @staticmethod
    def is_item_inventory_screen(img: np.ndarray) -> bool:
        """Chỉ nhận Item khi có ít nhất một hàng lưới vật phẩm hoàn chỉnh."""
        score, card_count, _ = ImageClassifier._inventory_card_grid_metrics(img)
        return score >= 30.0 and card_count >= 3

    @staticmethod
    def is_emote_inventory_screen(img: np.ndarray) -> bool:
        """Nhận màn Emoji qua cả nội dung thẻ và vị trí hàng đầu.

        Vệt bay/Dù cũng có thể chứa hình người màu trắng nên chỉ đếm silhouette
        sẽ gây nhận nhầm. Màn Emoji thật có phần Cài Đặt phía trên và hàng thẻ
        đầu bắt đầu quanh y=313 (trên ảnh chuẩn 2778x1284).
        """
        score, card_count, emote_count = ImageClassifier._inventory_card_grid_metrics(img)
        if score < 30.0 or card_count < 3 or emote_count < 3:
            return False

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        strips = []
        for x1, x2 in [(1730, 1927), (1967, 2164), (2203, 2399)]:
            sx1 = max(0, int(round(x1 * scale_x)))
            sx2 = min(width, int(round(x2 * scale_x)))
            if sx2 > sx1:
                strips.append(img[:, sx1:sx2])
        if not strips:
            return False

        gray = cv2.cvtColor(np.concatenate(strips, axis=1), cv2.COLOR_BGR2GRAY)
        row_diff = np.mean(
            np.abs(np.diff(gray.astype(np.float32), axis=0)), axis=1
        )
        y1 = max(0, int(round(307 * scale_y)))
        y2 = min(len(row_diff), int(round(321 * scale_y)))
        return y2 > y1 and float(np.max(row_diff[y1:y2])) >= 18.0

    @staticmethod
    def is_throwable_inventory_screen(img: np.ndarray) -> bool:
        """Nhận màn Lựu Đạn qua hàng thẻ và bốn ô loại lựu đạn phía trên.

        Màn lựu đạn có thêm một thanh loại vật phẩm ngang ở phía trên nên mép
        hàng đầu quanh y=299. Tuy nhiên màn Máy Bay cũng có hàng đầu cùng vị
        trí, nên phải kiểm tra thêm ba vạch chia đều của bốn ô loại lựu đạn.
        """
        score, card_count, _ = ImageClassifier._inventory_card_grid_metrics(img)
        if score < 30.0 or card_count < 3:
            return False

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        strips = []
        for x1, x2 in [(1730, 1927), (1967, 2164), (2203, 2399)]:
            sx1 = max(0, int(round(x1 * scale_x)))
            sx2 = min(width, int(round(x2 * scale_x)))
            if sx2 > sx1:
                strips.append(img[:, sx1:sx2])
        if not strips:
            return False

        gray = cv2.cvtColor(np.concatenate(strips, axis=1), cv2.COLOR_BGR2GRAY)
        row_diff = np.mean(
            np.abs(np.diff(gray.astype(np.float32), axis=0)), axis=1
        )
        y1 = max(0, int(round(291 * scale_y)))
        y2 = min(len(row_diff), int(round(307 * scale_y)))
        if y2 <= y1 or float(np.max(row_diff[y1:y2])) < 25.0:
            return False

        # Bốn ô loại lựu đạn tạo ba vạch dọc ổn định tại x≈1882, 2063, 2246.
        # Máy bay chỉ có hai tab rộng; chữ/hình trong tab không tạo đủ cả ba
        # vạch mạnh đúng các tọa độ hẹp này.
        header_y1 = max(0, int(round(75 * scale_y)))
        header_y2 = min(height, int(round(155 * scale_y)))
        header = img[header_y1:header_y2]
        if header.size == 0:
            return False
        header_gray = cv2.cvtColor(header, cv2.COLOR_BGR2GRAY).astype(np.float32)
        col_diff = np.mean(np.abs(np.diff(header_gray, axis=1)), axis=0)
        radius = max(2, int(round(5 * scale_x)))
        separator_scores = []
        for base_x in (1882, 2063, 2246):
            x = int(round(base_x * scale_x))
            lo = max(0, x - radius)
            hi = min(len(col_diff), x + radius + 1)
            if hi <= lo:
                return False
            separator_scores.append(float(np.max(col_diff[lo:hi])))

        return min(separator_scores) >= 17.5

    @staticmethod
    def is_parachute_inventory_screen(img: np.ndarray) -> bool:
        """Nhận cả màn Dù và màn đồ bay/vệt bay.

        Hai màn này có lưới thẻ bắt đầu quanh y=215. Máy Bay và Lựu Đạn có
        thanh loại phía trên nên hàng thẻ thật bắt đầu quanh y=299; Emoji có
        phần Cài Đặt nên bắt đầu quanh y=313. Kết hợp cấu trúc hàng và số thẻ
        giúp tránh phụ thuộc vào hình dáng từng món đồ.
        """
        score, card_count, _ = ImageClassifier._inventory_card_grid_metrics(img)
        if score < 30.0 or card_count < 3:
            return False

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        strips = []
        for x1, x2 in [(1730, 1927), (1967, 2164), (2203, 2399)]:
            sx1 = max(0, int(round(x1 * scale_x)))
            sx2 = min(width, int(round(x2 * scale_x)))
            if sx2 > sx1:
                strips.append(img[:, sx1:sx2])
        if not strips:
            return False

        gray = cv2.cvtColor(np.concatenate(strips, axis=1), cv2.COLOR_BGR2GRAY)
        row_diff = np.mean(
            np.abs(np.diff(gray.astype(np.float32), axis=0)), axis=1
        )

        def band_strength(y1: float, y2: float) -> float:
            start = max(0, int(round(y1 * scale_y)))
            end = min(len(row_diff), int(round(y2 * scale_y)))
            return float(np.max(row_diff[start:end])) if end > start else 0.0

        first_row = band_strength(205, 225)
        subtype_row = band_strength(291, 307)
        return first_row >= 25.0 and subtype_row < 20.0

    @staticmethod
    def classify(img: np.ndarray) -> str:
        """
        Nhận diện và phân loại ảnh chụp màn hình PUBG Mobile:
        1. Xưởng Súng -> SUNG
        2. Thanh Tab Chính dọc bên phải (X: 2520..2620):
           - y < 300       : Tab 1 Trang Phục (Phân tích tiếp Mũ, Balo, Mặt Nạ, Đồ, Set)
           - 300 <= y < 475: Tab 2 Súng
           - 475 <= y < 665: Tab 3 Xe (Vô Lăng)
           - 665 <= y < 900: Tab 4 Biểu cảm & Phụ kiện:
                             * Lưới hình người trắng: HÀNH ĐỘNG
                             * Hàng đầu y~299: LỰU ĐẠN
                             * Dù, tàu lượn, vệt bay: DÙ
                             * Mục còn lại: ITEM
           - 900 <= y < 1150: Tab 5 Item / Hộp Đồ
           - 1150 <= y      : Tab 6 Linh Thú / Khác -> ITEM
        """
        if img is None:
            return "OTHER"

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        # 1. XƯỞNG NÂNG CẤP SÚNG
        if ImageClassifier.is_gun_lab_screen(img):
            return "SUNG"

        # 1.5. MÀN HÌNH NGOẠI HÌNH (KIỂU TÓC / KHUÔN MẶT) -> ITEM
        if ImageClassifier.is_appearance_screen(img):
            return "ITEM"

        # 2. PHÂN TÍCH VẠCH XANH TRÊN THANH TAB DỌC NGOÀI CÙNG (X: 2530..2600)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        blue_mask, relaxed_blue_mask = ImageClassifier._blue_indicator_masks(hsv)

        mt_y = ImageClassifier._find_blue_indicator_y(
            blue_mask, 2520, 2620, scale_x, scale_y
        )
        main_tab = "OTHER"

        if mt_y is not None:
            if mt_y < 300:
                main_tab = "TRANG_PHUC"
            elif mt_y < 475:
                # Tab 2 kho súng thường: không đưa vào Cắt Súng (chỉ nhận màn Xưởng Súng giống Sung.py)
                main_tab = "OTHER"
            elif mt_y < 665:
                main_tab = "XE"
            elif mt_y < 900:
                main_tab = "TAB_4_ACCESSORY"  # Tab 4 (Hexagon) Biểu cảm & Phụ kiện
            elif mt_y < 1150:
                main_tab = "ITEM"             # Tab 5 Item / Hộp Đồ (vạch xanh tại y: ~750..850)
            else:
                main_tab = "OTHER"            # Tab 6 Linh thú / Khác

        if main_tab == "SUNG":
            return "SUNG"
        elif main_tab == "XE":
            return "XE"
        elif main_tab == "ITEM":
            return "ITEM"

        # Tab 4: ưu tiên cấu trúc nội dung thay vì vị trí icon, vì vị trí icon
        # Lựu Đạn thay đổi giữa các phiên bản giao diện game.
        if main_tab == "TAB_4_ACCESSORY":
            if ImageClassifier.is_emote_inventory_screen(img):
                return "HANH_DONG"
            if ImageClassifier.is_throwable_inventory_screen(img):
                return "LUU_DAN"
            if ImageClassifier.is_parachute_inventory_screen(img):
                return "DU"
            return "ITEM"

        # Khi vạch xanh bị nhạt do JPG/HDR, chỉ chấp nhận kết quả dự phòng nếu
        # ảnh đồng thời có đúng cấu trúc lưới Kho Đồ. Điều này cứu ảnh trang
        # phục bị bỏ sót mà không kéo ảnh sảnh/profile vào tool cắt.
        wardrobe_layout = ImageClassifier.has_wardrobe_inventory_layout(img)
        is_outfit_lobby = (
            cattrangphuc is not None
            and cattrangphuc.OutfitDetector.detect_lobby_type(img) is not None
        )

        if main_tab == "OTHER":
            relaxed_mt_y = ImageClassifier._find_blue_indicator_y(
                relaxed_blue_mask, 2520, 2620, scale_x, scale_y
            )
            if (wardrobe_layout and relaxed_mt_y is not None and relaxed_mt_y < 300) or is_outfit_lobby:
                main_tab = "TRANG_PHUC"
            else:
                return "ITEM"

        # 3. PHÂN TÍCH KHO ĐỒ TRANG PHỤC (INVENTORY SUB-TABS: Cột X: 2410..2470)
        if not wardrobe_layout and not is_outfit_lobby:
            return "OTHER"

        st_y = ImageClassifier._find_indicator_with_fallback(
            blue_mask, relaxed_blue_mask, 2390, 2495, scale_x, scale_y
        )
        sub_tab = "SET"

        # Balo phải được nhận trước popup chi tiết: ảnh Balo đang mở phần mô tả
        # trước đây bị đẩy nhầm sang ĐỒ.
        if ImageClassifier.is_backpack_inventory_screen(img, st_y, wardrobe_layout):
            return "BALO"

        if st_y is not None:
            if st_y < 300:
                sub_tab = "SET"
            elif st_y < 450:
                sub_tab = "MU"
            else:
                # Mặt Nạ/Kính cũng bị đẩy xuống y~877 khi danh mục dọc cuộn.
                # Balo đã được chặn phía trên bằng cụm chọn 3 cấp riêng.
                sub_tab = "MAT_NA"

        if sub_tab == "MU":
            return "MU"
        elif sub_tab == "MAT_NA":
            return "MAT_NA"
        else:
            # Quy tắc bắt buộc: chỉ ảnh đang mở bảng thông tin chi tiết mới là ĐỒ.
            # Lưới trang phục không có bảng chi tiết luôn đưa sang Trang Phục.
            if ImageClassifier.has_item_detail_popup(img):
                return "DO"
            return "TRANG_PHUC"

        return "ITEM"


# ==============================================================================
# BỘ QUẢN LÝ PHÂN LOẠI VÀ CHUYỂN ẢNH VÀO TOOL (ORGANIZER)
# ==============================================================================
GENERATED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def validate_account_id(value: str) -> str:
    """Chuẩn hóa mã acc và chặn mã có thể thoát khỏi thư mục output."""
    acc_id = str(value or "").strip()
    if not acc_id:
        raise ValueError("Vui lòng nhập Mã Acc trước khi bắt đầu.")
    if acc_id in {".", ".."}:
        raise ValueError("Mã Acc không hợp lệ.")
    if any(char in INVALID_ACCOUNT_CHARS or ord(char) < 32 for char in acc_id):
        raise ValueError('Mã Acc không được chứa các ký tự: < > : " / \\ | ? *')
    if acc_id.endswith((".", " ")):
        raise ValueError("Mã Acc không được kết thúc bằng dấu chấm hoặc khoảng trắng.")
    if acc_id.split(".", 1)[0].upper() in RESERVED_ACCOUNT_NAMES:
        raise ValueError("Mã Acc trùng với tên hệ thống dành riêng của Windows.")
    return acc_id


def list_source_images(folder_path: str = SOURCE_INPUT_DIR) -> List[str]:
    """Liệt kê ảnh nằm trực tiếp trong input; không quét thư mục con."""
    if not os.path.isdir(folder_path):
        return []
    return sorted(
        os.path.join(folder_path, name)
        for name in os.listdir(folder_path)
        if os.path.isfile(os.path.join(folder_path, name))
        and os.path.splitext(name)[1].lower() in SOURCE_IMAGE_EXTENSIONS
    )


def _clear_generated_images(folder_path: str, prefixes: Optional[Tuple[str, ...]] = None) -> int:
    """Xóa file ảnh sinh ra cũ trong đúng một thư mục, không xóa thư mục con."""
    if not os.path.isdir(folder_path):
        return 0

    deleted = 0
    for name in os.listdir(folder_path):
        path = os.path.join(folder_path, name)
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        if os.path.splitext(name)[1].lower() not in GENERATED_IMAGE_EXTENSIONS:
            continue
        if prefixes is not None and not name.lower().startswith(prefixes):
            continue
        os.remove(path)
        deleted += 1
    return deleted


def _generated_file_index(file_name: str, file_prefix: str) -> Optional[int]:
    """Lấy số thứ tự từ tên dạng <prefix>001.png; tên khác trả về None."""
    stem, extension = os.path.splitext(file_name)
    if extension.lower() not in GENERATED_IMAGE_EXTENSIONS:
        return None
    if not stem.lower().startswith(file_prefix.lower()):
        return None
    number_text = stem[len(file_prefix):]
    return int(number_text) if number_text.isdigit() else None


def append_tool_outputs(
    local_output_dir: str,
    global_output_dir: str,
    file_prefix: str,
    log_fn=print,
) -> List[str]:
    """Chép kết quả của lượt mới vào output acc và đánh số tiếp nối."""
    if not os.path.isdir(local_output_dir):
        return []

    os.makedirs(global_output_dir, exist_ok=True)
    existing_indexes = [
        index
        for name in os.listdir(global_output_dir)
        for index in [_generated_file_index(name, file_prefix)]
        if index is not None
    ]
    next_index = max(existing_indexes, default=0) + 1

    local_files = []
    for name in os.listdir(local_output_dir):
        source_path = os.path.join(local_output_dir, name)
        source_index = _generated_file_index(name, file_prefix)
        if os.path.isfile(source_path) and source_index is not None:
            local_files.append((source_index, name, source_path))
    local_files.sort(key=lambda item: (item[0], item[1].lower()))

    appended_paths = []
    for _, source_name, source_path in local_files:
        extension = os.path.splitext(source_name)[1].lower() or ".png"
        while True:
            destination_name = f"{file_prefix}{next_index:03d}{extension}"
            destination_path = os.path.join(global_output_dir, destination_name)
            next_index += 1
            if not os.path.exists(destination_path):
                break
        shutil.copy2(source_path, destination_path)
        appended_paths.append(destination_path)

    if appended_paths:
        log_fn(
            f"[THÊM VÀO OUTPUT] Đã thêm {len(appended_paths)} ảnh mới "
            f"({os.path.basename(appended_paths[0])} -> {os.path.basename(appended_paths[-1])}); "
            "giữ nguyên toàn bộ ảnh cũ."
        )
    return appended_paths


def organize_account_screenshots(
    acc_id: str,
    src_base_dir: Optional[str] = None,
    tools_base_dir: Optional[str] = None,
    log_fn=print
) -> Dict[str, List[str]]:
    """
    Quét ảnh trực tiếp trong input, phân loại rồi copy vào thư mục tool theo acc:
    - Cắt Súng       (sung_001.png, ...)
    - Cắt Xe         (xe_001.png, ...)
    - Cắt Trang Phục (tp_001.png, ...)
    - Cắt Đồ         (do_001.png, ...)
    - Cắt Mũ         (mu_001.png, ...)
    - Cắt Balo       (balo_001.png, ...)
    - Cắt Mặt Nạ     (matna_001.png, ...)
    - Cắt Lựu Đạn    (luudan_001.png, ...)
    - Cắt Dù          (du_001.png, ...)
    - Cắt Item       (item_001.png, ...)
    - Cắt Hành Động  (hd_001.png, ...)
    """
    acc_id = validate_account_id(acc_id)
    if src_base_dir is None:
        src_base_dir = SOURCE_INPUT_DIR
    if tools_base_dir is None:
        tools_base_dir = TOOLS_DIR

    acc_src_dir = src_base_dir
    if not os.path.isdir(acc_src_dir):
        log_fn(f"[X] Không tìm thấy thư mục ảnh gốc: {acc_src_dir}")
        return {"SUNG": [], "XE": [], "TRANG_PHUC": [], "DO": [], "MU": [], "BALO": [], "MAT_NA": [], "LUU_DAN": [], "DU": [], "ITEM": [], "HANH_DONG": [], "OTHER": []}

    src_files = list_source_images(acc_src_dir)

    total_files = len(src_files)
    if total_files == 0:
        log_fn(f"[!] Thư mục {acc_src_dir} không có ảnh nào!")
        return {"SUNG": [], "XE": [], "TRANG_PHUC": [], "DO": [], "MU": [], "BALO": [], "MAT_NA": [], "LUU_DAN": [], "DU": [], "ITEM": [], "HANH_DONG": [], "OTHER": []}

    log_fn(f"[*] Bắt đầu quét & phân loại {total_files} ảnh trực tiếp trong '{acc_src_dir}'...")

    sung_in_dir = os.path.join(tools_base_dir, "Cắt Súng", "input", acc_id)
    xe_in_dir = os.path.join(tools_base_dir, "Cắt Xe", "input", acc_id)
    tp_in_dir = os.path.join(tools_base_dir, "Cắt Trang Phục", "input", acc_id)
    do_in_dir = os.path.join(tools_base_dir, "Cắt Đồ", "input", acc_id)
    mu_in_dir = os.path.join(tools_base_dir, "Cắt Mũ", "input", acc_id)
    balo_in_dir = os.path.join(tools_base_dir, "Cắt Balo", "input", acc_id)
    matna_in_dir = os.path.join(tools_base_dir, "Cắt Mặt Nạ", "input", acc_id)
    luudan_in_dir = os.path.join(tools_base_dir, "Cắt Lựu Đạn", "input", acc_id)
    du_in_dir = os.path.join(tools_base_dir, "Cắt Dù", "input", acc_id)
    item_in_dir = os.path.join(tools_base_dir, "Cắt Item", "input", acc_id)
    hd_in_dir = os.path.join(tools_base_dir, "Cắt Hành Động", "input", acc_id)

    os.makedirs(sung_in_dir, exist_ok=True)
    os.makedirs(xe_in_dir, exist_ok=True)
    os.makedirs(tp_in_dir, exist_ok=True)
    os.makedirs(do_in_dir, exist_ok=True)
    os.makedirs(mu_in_dir, exist_ok=True)
    os.makedirs(balo_in_dir, exist_ok=True)
    os.makedirs(matna_in_dir, exist_ok=True)
    os.makedirs(luudan_in_dir, exist_ok=True)
    os.makedirs(du_in_dir, exist_ok=True)
    os.makedirs(item_in_dir, exist_ok=True)
    os.makedirs(hd_in_dir, exist_ok=True)

    # Xóa các bản copy phân loại của chính acc này trước khi phân loại lại.
    # Nếu không, ảnh sai từ lần chạy cũ vẫn còn và tiếp tục bị tool cắt xử lý.
    account_input_dirs = (
        sung_in_dir, xe_in_dir, tp_in_dir, do_in_dir, mu_in_dir,
        balo_in_dir, matna_in_dir, luudan_in_dir, du_in_dir, item_in_dir, hd_in_dir,
    )
    removed_stale_inputs = sum(_clear_generated_images(path) for path in account_input_dirs)
    if removed_stale_inputs:
        log_fn(f"[*] Đã bỏ {removed_stale_inputs} ảnh phân loại cũ của acc {acc_id} trước khi làm lại.")

    classified_files = {"SUNG": [], "XE": [], "TRANG_PHUC": [], "DO": [], "MU": [], "BALO": [], "MAT_NA": [], "LUU_DAN": [], "DU": [], "ITEM": [], "HANH_DONG": [], "OTHER": []}
    counts = {"SUNG": 0, "XE": 0, "TRANG_PHUC": 0, "DO": 0, "MU": 0, "BALO": 0, "MAT_NA": 0, "LUU_DAN": 0, "DU": 0, "ITEM": 0, "HANH_DONG": 0, "OTHER": 0}

    for idx, fpath in enumerate(src_files):
        fname = os.path.basename(fpath)
        img = cv2_imread_utf8(fpath)
        if img is None:
            log_fn(f"  [-] Bỏ qua file lỗi: {fname}")
            continue

        img_type = ImageClassifier.classify(img)
        counts[img_type] += 1
        classified_files[img_type].append(fpath)

        if img_type == "SUNG":
            if not ENABLE_GUN_TOOL:
                log_fn(f"  [🔫 SÚNG - TẠM TẮT] {fname} (không đưa vào tool Cắt Súng)")
                continue
            dest_name = f"sung_{counts['SUNG']:03d}.png"
            dest_path = os.path.join(sung_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🔫 SÚNG]       {fname} ➔ Cắt Súng\\input\\{acc_id}\\{dest_name}")

        elif img_type == "XE":
            dest_name = f"xe_{counts['XE']:03d}.png"
            dest_path = os.path.join(xe_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🚗 XE]         {fname} ➔ Cắt Xe\\input\\{acc_id}\\{dest_name}")

        elif img_type == "TRANG_PHUC":
            dest_name = f"tp_{counts['TRANG_PHUC']:03d}.png"
            dest_path = os.path.join(tp_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            lobby_label = ""
            if cattrangphuc:
                detector = cattrangphuc.OutfitDetector
                lobby = detector.detect_lobby_type(img)
                if lobby:
                    lobby_label = f" / {detector.LOBBY_LABELS[lobby]}"
            log_fn(f"  [✨ TRANG PHỤC{lobby_label}] {fname} ➔ Cắt Trang Phục\\input\\{acc_id}\\{dest_name}")

        elif img_type == "DO":
            dest_name = f"do_{counts['DO']:03d}.png"
            dest_path = os.path.join(do_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [👕 ĐỒ (Set)]   {fname} ➔ Cắt Đồ\\input\\{acc_id}\\{dest_name}")

        elif img_type == "MU":
            dest_name = f"mu_{counts['MU']:03d}.png"
            dest_path = os.path.join(mu_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🪖 MŨ]         {fname} ➔ Cắt Mũ\\input\\{acc_id}\\{dest_name}")

        elif img_type == "BALO":
            dest_name = f"balo_{counts['BALO']:03d}.png"
            dest_path = os.path.join(balo_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🎒 BALO]       {fname} ➔ Cắt Balo\\input\\{acc_id}\\{dest_name}")

        elif img_type == "MAT_NA":
            dest_name = f"matna_{counts['MAT_NA']:03d}.png"
            dest_path = os.path.join(matna_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🎭 MẶT NẠ]     {fname} ➔ Cắt Mặt Nạ\\input\\{acc_id}\\{dest_name}")

        elif img_type == "LUU_DAN":
            dest_name = f"luudan_{counts['LUU_DAN']:03d}.png"
            dest_path = os.path.join(luudan_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [💣 LỰU ĐẠN]    {fname} ➔ Cắt Lựu Đạn\\input\\{acc_id}\\{dest_name}")

        elif img_type == "DU":
            dest_name = f"du_{counts['DU']:03d}.png"
            dest_path = os.path.join(du_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🪂 DÙ/ĐỒ BAY]  {fname} ➔ Cắt Dù\\input\\{acc_id}\\{dest_name}")

        elif img_type == "ITEM":
            dest_name = f"item_{counts['ITEM']:03d}.png"
            dest_path = os.path.join(item_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [🎁 ITEM/KHÁC]  {fname} ➔ Cắt Item\\input\\{acc_id}\\{dest_name}")

        elif img_type == "HANH_DONG":
            dest_name = f"hd_{counts['HANH_DONG']:03d}.png"
            dest_path = os.path.join(hd_in_dir, dest_name)
            shutil.copy2(fpath, dest_path)
            log_fn(f"  [💃 HÀNH ĐỘNG]  {fname} ➔ Cắt Hành Động\\input\\{acc_id}\\{dest_name}")

        else:
            log_fn(f"  [❓ BỎ QUA]     {fname}")

    log_fn("-" * 65)
    log_fn(f"[TỔNG KẾT PHÂN LOẠI ACC '{acc_id}']:")
    log_fn(f" - Tổng ảnh gốc: {total_files}")
    log_fn(f" - 🔫 SÚNG:       {counts['SUNG']} ảnh ➔ Cắt Súng\\input\\{acc_id}\\")
    log_fn(f" - 🚗 XE:         {counts['XE']} ảnh ➔ Cắt Xe\\input\\{acc_id}\\")
    log_fn(f" - ✨ TRANG PHỤC: {counts['TRANG_PHUC']} ảnh ➔ Cắt Trang Phục\\input\\{acc_id}\\")
    log_fn(f" - 👕 ĐỒ (Set):   {counts['DO']} ảnh ➔ Cắt Đồ\\input\\{acc_id}\\")
    log_fn(f" - 🪖 MŨ:         {counts['MU']} ảnh ➔ Cắt Mũ\\input\\{acc_id}\\")
    log_fn(f" - 🎒 BALO:       {counts['BALO']} ảnh ➔ Cắt Balo\\input\\{acc_id}\\")
    log_fn(f" - 🎭 MẶT NẠ:     {counts['MAT_NA']} ảnh ➔ Cắt Mặt Nạ\\input\\{acc_id}\\")
    log_fn(f" - 💣 LỰU ĐẠN:    {counts['LUU_DAN']} ảnh ➔ Cắt Lựu Đạn\\input\\{acc_id}\\")
    log_fn(f" - 🪂 DÙ/ĐỒ BAY:  {counts['DU']} ảnh ➔ Cắt Dù\\input\\{acc_id}\\")
    log_fn(f" - 🎁 ITEM/KHÁC:  {counts['ITEM']} ảnh ➔ Cắt Item\\input\\{acc_id}\\")
    log_fn(f" - 💃 HÀNH ĐỘNG:  {counts['HANH_DONG']} ảnh ➔ Cắt Hành Động\\input\\{acc_id}\\")
    if counts['OTHER'] > 0:
        log_fn(f" - ❓ BỎ QUA:     {counts['OTHER']} ảnh")
    log_fn("-" * 65)

    return classified_files


# ==============================================================================
# HÀM CHẠY TỰ ĐỘNG TẤT CẢ CÁC TOOL CẮT
# ==============================================================================
def process_all_for_account(
    acc_id: str,
    project_root: str = PROJECT_ROOT,
    log_fn=print,
    progress_fn=None,
    on_preview_fn=None
) -> Dict:
    acc_id = validate_account_id(acc_id)
    src_base = os.path.join(project_root, "input")
    tools_base = (
        os.path.join(project_root, "tool")
        if os.path.isdir(os.path.join(project_root, "tool"))
        else os.path.join(project_root, "Cắt")
    )
    global_out = os.path.join(project_root, "output", acc_id)
    if not list_source_images(src_base):
        raise FileNotFoundError(f"Không có ảnh nào trong thư mục input: {src_base}")
    os.makedirs(global_out, exist_ok=True)

    log_fn("=" * 65)
    log_fn(f"🚀 BẮT ĐẦU QUY TRÌNH TỰ ĐỘNG TOÀN DIỆN CHO ACC: [{acc_id}]")
    log_fn(f"[*] Thư mục lưu kết quả cuối cùng: {global_out}")
    log_fn("=" * 65)

    # 1. Phân loại
    if progress_fn: progress_fn(5)
    log_fn("\n>>> [BƯỚC 1/12] PHÂN LOẠI & SẮP XẾP ẢNH TỪ INPUT...")
    organize_account_screenshots(acc_id, src_base, tools_base, log_fn=log_fn)

    # Chỉ làm sạch output tạm của từng tool. Kết quả cuối trong output/<acc>
    # được giữ nguyên để lượt cắt mới có thể nối tiếp vào tài khoản đã làm trước.
    output_specs = (
        ("Cắt Súng", "sung_"),
        ("Cắt Xe", "xe_"),
        ("Cắt Trang Phục", "tp_"),
        ("Cắt Đồ", "do_"),
        ("Cắt Mũ", "mu_"),
        ("Cắt Balo", "balo_"),
        ("Cắt Mặt Nạ", "matna_"),
        ("Cắt Lựu Đạn", "luudan_"),
        ("Cắt Dù", "du_"),
        ("Cắt Item", "item_"),
        ("Cắt Hành Động", "hd_"),
    )
    removed_local_outputs = 0
    for tool_name, _ in output_specs:
        tool_output = os.path.join(tools_base, tool_name, "output", acc_id)
        removed_local_outputs += _clear_generated_images(tool_output)

    if removed_local_outputs:
        log_fn(f"[*] Đã dọn {removed_local_outputs} file output tạm của lượt chạy trước.")
    log_fn(f"[*] Chế độ cắt bổ sung: giữ nguyên ảnh cũ trong output/{acc_id}.")

    # 2. Cắt Súng (Xưởng Nâng Cấp - DienLV)
    if progress_fn: progress_fn(15)
    log_fn("\n>>> [BƯỚC 2/12] BẮT ĐẦU CẮT ẢNH THẺ SÚNG XƯỞNG NÂNG CẤP (GUN LAB)...")
    sung_in = os.path.join(tools_base, "Cắt Súng", "input", acc_id)
    sung_out = os.path.join(tools_base, "Cắt Súng", "output", acc_id)
    sung_res = {"total_saved": 0}
    if catsung and os.path.exists(sung_in) and len(os.listdir(sung_in)) > 0:
        sung_res = catsung.process_batch(
            input_dir=sung_in,
            output_dir=sung_out,
            acc_id=acc_id,
            file_prefix="sung_",
            images_per_column=0,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(sung_out, global_out, "sung_", log_fn)
    else:
        log_fn("  [-] Không có ảnh súng nào cần xử lý.")

    # 3. Cắt Xe
    if progress_fn: progress_fn(25)
    log_fn("\n>>> [BƯỚC 3/12] BẮT ĐẦU CẮT ẢNH THẺ XE (VEHICLE CARDS)...")
    xe_in = os.path.join(tools_base, "Cắt Xe", "input", acc_id)
    xe_out = os.path.join(tools_base, "Cắt Xe", "output", acc_id)
    xe_res = {"total_saved": 0}
    if catxe and os.path.exists(xe_in) and len(os.listdir(xe_in)) > 0:
        xe_res = catxe.process_batch(
            input_dir=xe_in,
            output_dir=xe_out,
            enable_dedup=True,
            border_margin=3,
            extra_left=1,
            extra_top=1,
            extra_bottom=5,
            extra_right=1,
            target_size=(498, 190),
            file_prefix="xe_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(xe_out, global_out, "xe_", log_fn)
    else:
        log_fn("  [-] Không có ảnh xe nào cần xử lý.")

    # 4. Cắt Trang Phục
    if progress_fn: progress_fn(35)
    log_fn("\n>>> [BƯỚC 4/12] BẮT ĐẦU CẮT ẢNH TRANG PHỤC (NHÂN VẬT TOÀN THÂN)...")
    tp_in = os.path.join(tools_base, "Cắt Trang Phục", "input", acc_id)
    tp_out = os.path.join(tools_base, "Cắt Trang Phục", "output", acc_id)
    tp_res = {"total_saved": 0}
    if cattrangphuc and os.path.exists(tp_in) and len(os.listdir(tp_in)) > 0:
        tp_res = cattrangphuc.process_batch(
            input_dir=tp_in,
            output_dir=tp_out,
            target_size=(774, 1220),
            file_prefix="tp_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(tp_out, global_out, "tp_", log_fn)
    else:
        log_fn("  [-] Không có ảnh trang phục nào cần xử lý.")

    # 5. Cắt Đồ
    if progress_fn: progress_fn(45)
    log_fn("\n>>> [BƯỚC 5/12] BẮT ĐẦU CẮT 3 Ô ĐỒ (SET POPUP)...")
    do_in = os.path.join(tools_base, "Cắt Đồ", "input", acc_id)
    do_out = os.path.join(tools_base, "Cắt Đồ", "output", acc_id)
    do_res = {"total_saved": 0}
    if catdo and os.path.exists(do_in) and len(os.listdir(do_in)) > 0:
        do_res = catdo.process_batch(
            input_dir=do_in,
            output_dir=do_out,
            target_size=(683, 773),
            file_prefix="do_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(do_out, global_out, "do_", log_fn)
    else:
        log_fn("  [-] Không có ảnh đồ nào cần xử lý.")

    # 6. Cắt Mũ
    if progress_fn: progress_fn(55)
    log_fn("\n>>> [BƯỚC 6/12] BẮT ĐẦU CẮT 3 Ô MŨ...")
    mu_in = os.path.join(tools_base, "Cắt Mũ", "input", acc_id)
    mu_out = os.path.join(tools_base, "Cắt Mũ", "output", acc_id)
    mu_res = {"total_saved": 0}
    if catmu and os.path.exists(mu_in) and len(os.listdir(mu_in)) > 0:
        mu_res = catmu.process_batch(
            input_dir=mu_in,
            output_dir=mu_out,
            target_size=(683, 773),
            file_prefix="mu_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(mu_out, global_out, "mu_", log_fn)
    else:
        log_fn("  [-] Không có ảnh mũ nào cần xử lý.")

    # 7. Cắt Balo
    if progress_fn: progress_fn(65)
    log_fn("\n>>> [BƯỚC 7/12] BẮT ĐẦU CẮT 3 Ô BALO...")
    balo_in = os.path.join(tools_base, "Cắt Balo", "input", acc_id)
    balo_out = os.path.join(tools_base, "Cắt Balo", "output", acc_id)
    balo_res = {"total_saved": 0}
    if catbalo and os.path.exists(balo_in) and len(os.listdir(balo_in)) > 0:
        balo_res = catbalo.process_batch(
            input_dir=balo_in,
            output_dir=balo_out,
            target_size=(683, 773),
            file_prefix="balo_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(balo_out, global_out, "balo_", log_fn)
    else:
        log_fn("  [-] Không có ảnh balo nào cần xử lý.")

    # 8. Cắt Mặt Nạ
    if progress_fn: progress_fn(75)
    log_fn("\n>>> [BƯỚC 8/12] BẮT ĐẦU CẮT 3 Ô MẶT NẠ...")
    matna_in = os.path.join(tools_base, "Cắt Mặt Nạ", "input", acc_id)
    matna_out = os.path.join(tools_base, "Cắt Mặt Nạ", "output", acc_id)
    matna_res = {"total_saved": 0}
    if catmatna and os.path.exists(matna_in) and len(os.listdir(matna_in)) > 0:
        matna_res = catmatna.process_batch(
            input_dir=matna_in,
            output_dir=matna_out,
            target_size=(683, 773),
            file_prefix="matna_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(matna_out, global_out, "matna_", log_fn)
    else:
        log_fn("  [-] Không có ảnh mặt nạ nào cần xử lý.")

    # 9. Cắt Lựu Đạn (Chỉ Đỏ & Tím)
    if progress_fn: progress_fn(85)
    log_fn("\n>>> [BƯỚC 9/12] BẮT ĐẦU CẮT Ô LỰU ĐẠN (CHỈ NỀN ĐỎ & TÍM)...")
    luudan_in = os.path.join(tools_base, "Cắt Lựu Đạn", "input", acc_id)
    luudan_out = os.path.join(tools_base, "Cắt Lựu Đạn", "output", acc_id)
    luudan_res = {"total_saved": 0}
    if catluudan and os.path.exists(luudan_in) and len(os.listdir(luudan_in)) > 0:
        luudan_res = catluudan.process_batch(
            input_dir=luudan_in,
            output_dir=luudan_out,
            enable_dedup=True,
            border_margin=5,
            target_size=(216, 216),
            file_prefix="luudan_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(luudan_out, global_out, "luudan_", log_fn)
    else:
        log_fn("  [-] Không có ảnh lựu đạn nào cần xử lý.")

    # 10. Cắt Dù / Đồ Bay (Chỉ nền Vàng, Đỏ, Tím)
    if progress_fn: progress_fn(90)
    log_fn("\n>>> [BƯỚC 10/12] BẮT ĐẦU CẮT Ô DÙ / ĐỒ BAY (BỎ NỀN XÁM)...")
    du_in = os.path.join(tools_base, "Cắt Dù", "input", acc_id)
    du_out = os.path.join(tools_base, "Cắt Dù", "output", acc_id)
    du_res = {"total_saved": 0}
    if catdu and os.path.exists(du_in) and len(os.listdir(du_in)) > 0:
        du_res = catdu.process_batch(
            input_dir=du_in,
            output_dir=du_out,
            enable_dedup=True,
            border_margin=5,
            target_size=(216, 216),
            file_prefix="du_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(du_out, global_out, "du_", log_fn)
    else:
        log_fn("  [-] Không có ảnh Dù/đồ bay nào cần xử lý.")

    # 11. Cắt Item (Vật Phẩm / Khác)
    if progress_fn: progress_fn(92)
    log_fn("\n>>> [BƯỚC 11/12] BẮT ĐẦU CẮT Ô ITEM / VẬT PHẨM...")
    item_in = os.path.join(tools_base, "Cắt Item", "input", acc_id)
    item_out = os.path.join(tools_base, "Cắt Item", "output", acc_id)
    item_res = {"total_saved": 0}
    if catitem and os.path.exists(item_in) and len(os.listdir(item_in)) > 0:
        item_res = catitem.process_batch(
            input_dir=item_in,
            output_dir=item_out,
            enable_dedup=True,
            border_margin=5,
            target_size=(216, 216),
            file_prefix="item_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(item_out, global_out, "item_", log_fn)
    else:
        log_fn("  [-] Không có ảnh item nào cần xử lý.")

    # 12. Cắt Hành Động (Chỉ Nền Đỏ)
    if progress_fn: progress_fn(98)
    log_fn("\n>>> [BƯỚC 12/12] BẮT ĐẦU CẮT Ô HÀNH ĐỘNG (CHỈ NỀN ĐỎ)...")
    hd_in = os.path.join(tools_base, "Cắt Hành Động", "input", acc_id)
    hd_out = os.path.join(tools_base, "Cắt Hành Động", "output", acc_id)
    hd_res = {"total_saved": 0}
    if cathanhdong and os.path.exists(hd_in) and len(os.listdir(hd_in)) > 0:
        hd_res = cathanhdong.process_batch(
            input_dir=hd_in,
            output_dir=hd_out,
            enable_dedup=True,
            border_margin=5,
            target_size=(216, 216),
            file_prefix="hd_",
            acc_id=acc_id,
            sync_global_output=False,
            log_fn=log_fn,
            on_card_saved_fn=on_preview_fn
        )
        append_tool_outputs(hd_out, global_out, "hd_", log_fn)
    else:
        log_fn("  [-] Không có ảnh hành động nào cần xử lý.")

    if progress_fn: progress_fn(100)

    log_fn("\n" + "=" * 65)
    log_fn(f"🎉 HOÀN TẤT TOÀN BỘ CHO MÃ ACC: [{acc_id}]")
    log_fn(f" - 🔫 Súng:       {sung_res.get('total_saved', 0)} ảnh mới (sung_xxx.png)")
    log_fn(f" - 🚗 Xe:         {xe_res.get('total_saved', 0)} ảnh mới (xe_xxx.png)")
    log_fn(f" - ✨ Trang Phục: {tp_res.get('total_saved', 0)} ảnh mới (tp_xxx.png)")
    log_fn(f" - 👕 Đồ (3 Ô):   {do_res.get('total_saved', 0)} ảnh mới (do_xxx.png)")
    log_fn(f" - 🪖 Mũ (3 Ô):   {mu_res.get('total_saved', 0)} ảnh mới (mu_xxx.png)")
    log_fn(f" - 🎒 Balo (3 Ô): {balo_res.get('total_saved', 0)} ảnh mới (balo_xxx.png)")
    log_fn(f" - 🎭 Mặt Nạ:     {matna_res.get('total_saved', 0)} ảnh mới (matna_xxx.png)")
    log_fn(f" - 💣 Lựu Đạn:    {luudan_res.get('total_saved', 0)} ảnh mới (luudan_xxx.png)")
    log_fn(f" - 🪂 Dù/Đồ Bay:  {du_res.get('total_saved', 0)} ảnh mới (du_xxx.png)")
    log_fn(f" - 🎁 Item/Khác:  {item_res.get('total_saved', 0)} ảnh mới (item_xxx.png)")
    log_fn(f" - 💃 Hành Động:  {hd_res.get('total_saved', 0)} ảnh mới (hd_xxx.png)")
    log_fn(f" - Thư mục kết quả tổng: {global_out}")
    log_fn("=" * 65)

    return {
        "sung_saved": sung_res.get('total_saved', 0),
        "xe_saved": xe_res.get('total_saved', 0),
        "tp_saved": tp_res.get('total_saved', 0),
        "do_saved": do_res.get('total_saved', 0),
        "mu_saved": mu_res.get('total_saved', 0),
        "balo_saved": balo_res.get('total_saved', 0),
        "matna_saved": matna_res.get('total_saved', 0),
        "luudan_saved": luudan_res.get('total_saved', 0),
        "du_saved": du_res.get('total_saved', 0),
        "item_saved": item_res.get('total_saved', 0),
        "hd_saved": hd_res.get('total_saved', 0),
        "output_dir": global_out
    }


# ==============================================================================
# GIAO DIỆN TRUNG TÂM ĐIỀU KHIỂN (MODERN MASTER GUI)
# ==============================================================================
class MasterAppGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HỆ THỐNG PHÂN LOẠI & CẮT ẢNH GHÉP ACC TỰ ĐỘNG - START DASHBOARD")
        self.root.geometry("1120x920")
        self.root.minsize(960, 740)

        self.bg_color = "#11111b"
        self.card_bg = "#181825"
        self.input_bg = "#313244"
        self.fg_color = "#cdd6f4"
        self.accent_blue = "#89b4fa"
        self.accent_purple = "#cba6f7"
        self.accent_orange = "#fab387"
        self.btn_green = "#a6e3a1"
        self.btn_green_dark = "#11111b"

        self.root.configure(bg=self.bg_color)
        self.acc_id_var = tk.StringVar(value="")
        self.is_processing = False
        self.preview_images: List[ImageTk.PhotoImage] = []

        self._build_ui()

    def _require_account(self) -> Optional[str]:
        try:
            acc = validate_account_id(self.acc_id_var.get())
        except ValueError as exc:
            messagebox.showwarning("Mã Acc chưa hợp lệ", str(exc))
            return None
        self.acc_id_var.set(acc)
        os.makedirs(os.path.join(GLOBAL_OUTPUT_DIR, acc), exist_ok=True)
        return acc

    def _require_source_images(self) -> bool:
        os.makedirs(SOURCE_INPUT_DIR, exist_ok=True)
        if list_source_images(SOURCE_INPUT_DIR):
            return True
        messagebox.showwarning(
            "Thư mục input đang trống",
            f"Không có ảnh nào trong:\n{SOURCE_INPUT_DIR}\n\n"
            "Hãy đưa ảnh trực tiếp vào thư mục input rồi chạy lại."
        )
        return False

    def _build_ui(self):
        header = tk.Frame(self.root, bg=self.bg_color, pady=10)
        header.pack(fill=tk.X, padx=20)

        tk.Label(
            header,
            text="⚡ HỆ THỐNG ĐỒNG BỘ PHÂN LOẠI & CẮT ẢNH GHÉP ACC",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.accent_blue
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Tự động nhận diện 9 phân loại (Súng, Xe, Trang Phục, Đồ, Mũ, Balo, Mặt Nạ, Lựu Đạn, Item, Hành Động) ➔ Cắt chuẩn & Xuất theo Mã Acc",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg="#a6adc8"
        ).pack(anchor="w", pady=(2, 0))

        body = tk.Frame(self.root, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        left_col = tk.Frame(body, bg=self.card_bg, padx=14, pady=14)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        tk.Label(left_col, text="1. NHẬP MÃ ACC", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_blue).pack(anchor="w", pady=(0, 4))

        self.acc_entry = ttk.Entry(
            left_col,
            textvariable=self.acc_id_var,
            font=("Segoe UI", 10, "bold")
        )
        self.acc_entry.pack(fill=tk.X, pady=(0, 8))

        tk.Label(left_col, text="2. THỰC HIỆN TỰ ĐỘNG TOÀN DIỆN", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_blue).pack(anchor="w", pady=(0, 4))

        self.btn_auto_all = tk.Button(
            left_col,
            text="🚀  1-CLICK TỰ ĐỘNG TẤT CẢ",
            font=("Segoe UI", 11, "bold"),
            bg=self.btn_green,
            fg=self.btn_green_dark,
            activebackground="#94e2d5",
            relief=tk.FLAT,
            pady=8,
            command=self._start_auto_all
        )
        self.btn_auto_all.pack(fill=tk.X, pady=(0, 10))

        tk.Label(left_col, text="3. CHẠY TỪNG CÔNG ĐOẠN LẺ", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.accent_purple).pack(anchor="w", pady=(0, 3))

        buttons = [
            ("📁 [1] Phân loại ảnh vào các Tool", self._start_organize_only),
            ("🔫 [2] Cắt Súng (Xưởng Nâng Cấp)", self._start_guns_only),
            ("🚗 [3] Cắt Xe (Tab Vô Lăng)", self._start_cars_only),
            ("✨ [4] Cắt Trang Phục (Toàn Thân)", self._start_outfit_only),
            ("👕 [5] Cắt Đồ (3 Ô Đồ Set)", self._start_items_only),
            ("🪖 [6] Cắt Mũ (3 Ô Mũ Cấp 1,2,3)", self._start_helmets_only),
            ("🎒 [7] Cắt Balo (3 Ô Balo Cấp 1,2,3)", self._start_backpacks_only),
            ("🎭 [8] Cắt Mặt Nạ (3 Ô Mặt Nạ)", self._start_masks_only),
            ("💣 [9] Cắt Lựu Đạn (Chỉ Đỏ & Tím)", self._start_grenades_only),
            ("🪂 [10] Cắt Dù / Đồ Bay (Bỏ nền xám)", self._start_parachutes_only),
            ("🎁 [11] Cắt Item / Khác (216x216)", self._start_item_boxes_only),
            ("💃 [12] Cắt Hành Động (Chỉ Nền Đỏ)", self._start_emotes_only),
        ]

        for text, cmd in buttons:
            btn = tk.Button(left_col, text=text, font=("Segoe UI", 8), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, pady=2, command=cmd)
            btn.pack(fill=tk.X, pady=(0, 2))

        tk.Label(left_col, text="4. TRUY CẬP NHANH THƯ MỤC", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.accent_orange).pack(anchor="w", pady=(6, 2))

        tk.Button(left_col, text="📥 Mở Thư Mục Ảnh Gốc (input)", font=("Segoe UI", 8), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, pady=3, command=self._open_screenshot_folder).pack(fill=tk.X, pady=(0, 2))
        tk.Button(left_col, text="📂 Mở Thư Mục Kết Quả (output)", font=("Segoe UI", 8), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, pady=3, command=self._open_output_folder).pack(fill=tk.X, pady=(0, 6))

        self.progress_bar = ttk.Progressbar(left_col, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(2, 2))

        self.lbl_status = tk.Label(left_col, text="Sẵn sàng thực hiện", font=("Segoe UI", 8), bg=self.card_bg, fg="#a6adc8")
        self.lbl_status.pack(anchor="w")

        self.btn_clear_input = tk.Button(
            left_col,
            text="🗑 XÓA TOÀN BỘ ẢNH TRONG INPUT",
            font=("Segoe UI", 8, "bold"),
            bg="#d20f39",
            fg="#ffffff",
            activebackground="#f38ba8",
            activeforeground="#11111b",
            relief=tk.FLAT,
            padx=8,
            pady=6,
            command=self._delete_input_images
        )
        self.btn_clear_input.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        right_col = tk.Frame(body, bg=self.bg_color)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        preview_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        preview_panel.pack(fill=tk.X, pady=(0, 8))

        tk.Label(preview_panel, text="XEM TRƯỚC CÁC ẢNH VỪA CẮT MỚI NHẤT", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_blue).pack(anchor="w", pady=(0, 4))

        self.preview_canvas_frame = tk.Frame(preview_panel, bg=self.card_bg)
        self.preview_canvas_frame.pack(fill=tk.X)

        self.preview_labels = []
        for i in range(5):
            lbl = tk.Label(self.preview_canvas_frame, bg="#11111b", width=14, height=5, relief=tk.RIDGE, bd=1)
            lbl.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.BOTH)
            self.preview_labels.append(lbl)

        log_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        log_panel.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_panel, text="NHẬT KÝ TIẾN TRÌNH (LOGS)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_blue).pack(anchor="w", pady=(0, 4))

        self.log_text = tk.Text(log_panel, font=("Consolas", 9), bg="#11111b", fg="#a6adc8", relief=tk.FLAT, wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_panel, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, text: str):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _open_screenshot_folder(self):
        os.makedirs(SOURCE_INPUT_DIR, exist_ok=True)
        os.startfile(SOURCE_INPUT_DIR)

    def _open_output_folder(self):
        acc = self.acc_id_var.get().strip()
        if acc:
            try:
                acc = validate_account_id(acc)
            except ValueError as exc:
                messagebox.showwarning("Mã Acc chưa hợp lệ", str(exc))
                return
        target = os.path.join(GLOBAL_OUTPUT_DIR, acc) if acc else GLOBAL_OUTPUT_DIR
        os.makedirs(target, exist_ok=True)
        os.startfile(target)

    def _delete_input_images(self):
        if self.is_processing:
            messagebox.showwarning(
                "Tool đang xử lý",
                "Không thể xóa ảnh input trong khi tool đang chạy."
            )
            return

        os.makedirs(SOURCE_INPUT_DIR, exist_ok=True)
        image_files = list_source_images(SOURCE_INPUT_DIR)
        if not image_files:
            messagebox.showinfo("Không có ảnh", "Thư mục input hiện không có ảnh để xóa.")
            return

        confirmed = messagebox.askyesno(
            "Xác nhận xóa ảnh",
            f"Bạn có chắc muốn XÓA VĨNH VIỄN {len(image_files)} ảnh trong:\n"
            f"{SOURCE_INPUT_DIR}\n\n"
            "Thao tác này không xóa output và không thể hoàn tác.",
            icon="warning"
        )
        if not confirmed:
            return

        deleted = 0
        errors = []
        for path in image_files:
            try:
                os.remove(path)
                deleted += 1
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")

        self.log(f"[DỌN INPUT] Đã xóa {deleted}/{len(image_files)} ảnh trong input.")
        for error in errors:
            self.log(f"  [LỖI] {error}")

        if errors:
            messagebox.showwarning(
                "Đã xóa một phần",
                f"Đã xóa {deleted}/{len(image_files)} ảnh.\n"
                f"Có {len(errors)} ảnh không thể xóa; xem nhật ký để biết chi tiết."
            )
        else:
            messagebox.showinfo("Đã xóa ảnh", f"Đã xóa toàn bộ {deleted} ảnh trong input.")

    def _add_preview_image(self, path: str, img_bgr: np.ndarray):
        try:
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            thumb_h = 90
            thumb_w = int(w * (thumb_h / max(1, h)))
            if thumb_w > 160:
                thumb_w = 160
                thumb_h = int(h * (thumb_w / max(1, w)))

            img_resized = cv2.resize(img_rgb, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            pil_img = Image.fromarray(img_resized)
            tk_img = ImageTk.PhotoImage(pil_img)
            self.preview_images.append(tk_img)
            if len(self.preview_images) > 5:
                self.preview_images.pop(0)

            for idx, img_obj in enumerate(self.preview_images):
                if idx < len(self.preview_labels):
                    self.preview_labels[idx].configure(image=img_obj, width=thumb_w, height=thumb_h)
        except Exception:
            pass

    def _set_running_state(self, running: bool, title: str = "Đang xử lý..."):
        self.is_processing = running
        if running:
            self.btn_auto_all.configure(state=tk.DISABLED, bg="#6c7086", text="⏳ ĐANG XỬ LÝ...")
            self.btn_clear_input.configure(state=tk.DISABLED, bg="#6c7086")
            self.lbl_status.configure(text=title, fg=self.accent_blue)
            self.progress_bar["value"] = 0
            self.log_text.delete(1.0, tk.END)
        else:
            self.btn_auto_all.configure(state=tk.NORMAL, bg=self.btn_green, text="🚀  1-CLICK TỰ ĐỘNG TẤT CẢ")
            self.btn_clear_input.configure(state=tk.NORMAL, bg="#d20f39")
            self.progress_bar["value"] = 100
            self.lbl_status.configure(text="Hoàn tất!", fg=self.btn_green)

    def _finish_with_error(self, error_message: str):
        self._set_running_state(False)
        self.progress_bar["value"] = 0
        self.lbl_status.configure(text="Xử lý thất bại", fg="#f38ba8")
        self.log(f"[X] {error_message}")
        messagebox.showerror("Không thể xử lý", error_message)

    def _start_auto_all(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc or not self._require_source_images(): return

        self._set_running_state(True, f"Đang chạy tự động cho Acc: {acc}...")

        def thread_fn():
            try:
                res = process_all_for_account(
                    acc_id=acc,
                    project_root=PROJECT_ROOT,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    progress_fn=lambda v: self.root.after(0, lambda: self.progress_bar.configure(value=v)),
                    on_preview_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
            except Exception as exc:
                error_message = str(exc)
                self.root.after(0, lambda: self._finish_with_error(error_message))
                return

            def finish():
                self._set_running_state(False)
                messagebox.showinfo(
                    "Thành công",
                    f"🎉 ĐÃ THÊM ẢNH MỚI CHO ACC: {acc}\n"
                    f" - Súng:      {res['sung_saved']} ảnh mới\n"
                    f" - Xe:        {res['xe_saved']} ảnh mới\n"
                    f" - Trang Phục:{res['tp_saved']} ảnh mới\n"
                    f" - Đồ (3 Ô):  {res['do_saved']} ảnh mới\n"
                    f" - Mũ (3 Ô):  {res['mu_saved']} ảnh mới\n"
                    f" - Balo (3 Ô):{res['balo_saved']} ảnh mới\n"
                    f" - Mặt Nạ:    {res['matna_saved']} ảnh mới\n"
                    f" - Lựu Đạn:   {res['luudan_saved']} ảnh mới\n"
                    f" - Item/Khác: {res['item_saved']} ảnh mới\n"
                    f" - Hành Động: {res['hd_saved']} ảnh mới\n\n"
                    "Toàn bộ ảnh cũ của acc vẫn được giữ nguyên.\n"
                    f"Vị trí lưu: {res['output_dir']}"
                )

            self.root.after(0, finish)

        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_organize_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc or not self._require_source_images(): return
        self._set_running_state(True, f"Đang phân loại ảnh cho Acc: {acc}...")

        def thread_fn():
            organize_account_screenshots(
                acc_id=acc,
                src_base_dir=SOURCE_INPUT_DIR,
                tools_base_dir=TOOLS_DIR,
                log_fn=lambda m: self.root.after(0, lambda: self.log(m))
            )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_guns_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Súng cho Acc: {acc}...")

        def thread_fn():
            sung_in = os.path.join(TOOLS_DIR, "Cắt Súng", "input", acc)
            sung_out = os.path.join(TOOLS_DIR, "Cắt Súng", "output", acc)
            _clear_generated_images(sung_out)
            if catsung:
                catsung.process_batch(
                    input_dir=sung_in,
                    output_dir=sung_out,
                    acc_id=acc,
                    file_prefix="sung_",
                    images_per_column=0,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                global_out = os.path.join(GLOBAL_OUTPUT_DIR, acc)
                append_tool_outputs(sung_out, global_out, "sung_", log_fn=lambda m: self.root.after(0, lambda: self.log(m)))
            else:
                self.root.after(0, lambda: self.log("[LỖI] Không thể nạp module catsung."))
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_cars_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Xe cho Acc: {acc}...")

        def thread_fn():
            xe_in = os.path.join(TOOLS_DIR, "Cắt Xe", "input", acc)
            xe_out = os.path.join(TOOLS_DIR, "Cắt Xe", "output", acc)
            _clear_generated_images(xe_out)
            if catxe:
                catxe.process_batch(
                    input_dir=xe_in,
                    output_dir=xe_out,
                    border_margin=3,
                    extra_left=1,
                    extra_top=1,
                    extra_bottom=5,
                    extra_right=1,
                    target_size=(498, 190),
                    file_prefix="xe_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    xe_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "xe_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_outfit_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Trang Phục cho Acc: {acc}...")

        def thread_fn():
            tp_in = os.path.join(TOOLS_DIR, "Cắt Trang Phục", "input", acc)
            tp_out = os.path.join(TOOLS_DIR, "Cắt Trang Phục", "output", acc)
            _clear_generated_images(tp_out)
            if cattrangphuc:
                cattrangphuc.process_batch(
                    input_dir=tp_in,
                    output_dir=tp_out,
                    target_size=(774, 1220),
                    file_prefix="tp_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    tp_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "tp_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_items_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Đồ cho Acc: {acc}...")

        def thread_fn():
            do_in = os.path.join(TOOLS_DIR, "Cắt Đồ", "input", acc)
            do_out = os.path.join(TOOLS_DIR, "Cắt Đồ", "output", acc)
            _clear_generated_images(do_out)
            if catdo:
                catdo.process_batch(
                    input_dir=do_in,
                    output_dir=do_out,
                    target_size=(683, 773),
                    file_prefix="do_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    do_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "do_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_helmets_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Mũ cho Acc: {acc}...")

        def thread_fn():
            mu_in = os.path.join(TOOLS_DIR, "Cắt Mũ", "input", acc)
            mu_out = os.path.join(TOOLS_DIR, "Cắt Mũ", "output", acc)
            _clear_generated_images(mu_out)
            if catmu:
                catmu.process_batch(
                    input_dir=mu_in,
                    output_dir=mu_out,
                    target_size=(683, 773),
                    file_prefix="mu_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    mu_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "mu_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_backpacks_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Balo cho Acc: {acc}...")

        def thread_fn():
            balo_in = os.path.join(TOOLS_DIR, "Cắt Balo", "input", acc)
            balo_out = os.path.join(TOOLS_DIR, "Cắt Balo", "output", acc)
            _clear_generated_images(balo_out)
            if catbalo:
                catbalo.process_batch(
                    input_dir=balo_in,
                    output_dir=balo_out,
                    target_size=(683, 773),
                    file_prefix="balo_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    balo_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "balo_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_masks_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Mặt Nạ cho Acc: {acc}...")

        def thread_fn():
            matna_in = os.path.join(TOOLS_DIR, "Cắt Mặt Nạ", "input", acc)
            matna_out = os.path.join(TOOLS_DIR, "Cắt Mặt Nạ", "output", acc)
            _clear_generated_images(matna_out)
            if catmatna:
                catmatna.process_batch(
                    input_dir=matna_in,
                    output_dir=matna_out,
                    target_size=(683, 773),
                    file_prefix="matna_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    matna_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "matna_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_grenades_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Lựu Đạn cho Acc: {acc}...")

        def thread_fn():
            luudan_in = os.path.join(TOOLS_DIR, "Cắt Lựu Đạn", "input", acc)
            luudan_out = os.path.join(TOOLS_DIR, "Cắt Lựu Đạn", "output", acc)
            _clear_generated_images(luudan_out)
            if catluudan:
                catluudan.process_batch(
                    input_dir=luudan_in,
                    output_dir=luudan_out,
                    enable_dedup=True,
                    border_margin=5,
                    target_size=(216, 216),
                    file_prefix="luudan_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    luudan_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "luudan_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_parachutes_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Dù / Đồ Bay cho Acc: {acc}...")

        def thread_fn():
            du_in = os.path.join(TOOLS_DIR, "Cắt Dù", "input", acc)
            du_out = os.path.join(TOOLS_DIR, "Cắt Dù", "output", acc)
            _clear_generated_images(du_out)
            if catdu:
                catdu.process_batch(
                    input_dir=du_in,
                    output_dir=du_out,
                    enable_dedup=True,
                    border_margin=5,
                    target_size=(216, 216),
                    file_prefix="du_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    du_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "du_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_item_boxes_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Item / Khác cho Acc: {acc}...")

        def thread_fn():
            item_in = os.path.join(TOOLS_DIR, "Cắt Item", "input", acc)
            item_out = os.path.join(TOOLS_DIR, "Cắt Item", "output", acc)
            _clear_generated_images(item_out)
            if catitem:
                catitem.process_batch(
                    input_dir=item_in,
                    output_dir=item_out,
                    enable_dedup=True,
                    border_margin=5,
                    target_size=(216, 216),
                    file_prefix="item_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    item_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "item_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()

    def _start_emotes_only(self):
        if self.is_processing: return
        acc = self._require_account()
        if not acc: return
        self._set_running_state(True, f"Đang cắt Hành Động cho Acc: {acc}...")

        def thread_fn():
            hd_in = os.path.join(TOOLS_DIR, "Cắt Hành Động", "input", acc)
            hd_out = os.path.join(TOOLS_DIR, "Cắt Hành Động", "output", acc)
            _clear_generated_images(hd_out)
            if cathanhdong:
                cathanhdong.process_batch(
                    input_dir=hd_in,
                    output_dir=hd_out,
                    enable_dedup=True,
                    border_margin=5,
                    target_size=(216, 216),
                    file_prefix="hd_",
                    acc_id=acc,
                    sync_global_output=False,
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                    on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(p, im))
                )
                append_tool_outputs(
                    hd_out, os.path.join(GLOBAL_OUTPUT_DIR, acc), "hd_",
                    log_fn=lambda m: self.root.after(0, lambda: self.log(m))
                )
            self.root.after(0, lambda: self._set_running_state(False))
        threading.Thread(target=thread_fn, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Master Dashboard: Phân loại & Cắt ảnh tự động theo Mã Acc")
    parser.add_argument("--cli", action="store_true", help="Chạy CLI không mở GUI")
    parser.add_argument("-a", "--acc", default=None, help="Mã tài khoản")

    args = parser.parse_args()

    if args.cli:
        try:
            acc_id = validate_account_id(args.acc)
            print(f"[*] Khởi động Master Tool ở chế độ CLI cho Acc: {acc_id}")
            process_all_for_account(acc_id=acc_id, log_fn=print)
        except (ValueError, FileNotFoundError) as exc:
            parser.error(str(exc))
    else:
        root = tk.Tk()
        app = MasterAppGUI(root)
        if args.acc:
            app.acc_id_var.set(args.acc)
        root.mainloop()


if __name__ == "__main__":
    main()
