#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOOL CẮT ẢNH ITEM / VẬT PHẨM TỰ ĐỘNG - KHO ĐỒ PUBG MOBILE
=========================================================
Đặc điểm:
1. Tự động nhận diện đúng lưới vật phẩm 3 cột của Kho Đồ.
2. Tự động tìm pha cuộn, căn chỉnh và cắt sát ruột từng vật phẩm.
3. Không lấy nhầm icon con hoặc khung thông tin chi tiết bên trái.
4. Chuẩn hóa kích thước đầu ra đồng nhất 100% (chuẩn 216x216 px).
5. Lọc bỏ ô trùng lặp khi cuộn (Deduplication) và loại bỏ ô rỗng/ô đen.
6. Hỗ trợ giao diện đồ họa (GUI) xem trước trực quan và dòng lệnh (CLI).
7. Đồng bộ tự động ra output/<mã_acc>/ và D:\\Ghep-Anh\\output\\<mã_acc>/.
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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ==============================================================================
# HÀM ĐỌC / GHI ẢNH AN TOÀN VỚI ĐƯỜNG DẪN UNICODE TRÊN WINDOWS
# ==============================================================================
def cv2_imread_utf8(path: str) -> Optional[np.ndarray]:
    """Đọc ảnh an toàn với đường dẫn tiếng Việt trên Windows."""
    try:
        if not os.path.exists(path):
            return None
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[Lỗi đọc ảnh] {path}: {e}")
        return None


def cv2_imwrite_utf8(path: str, img: np.ndarray, quality: int = 95) -> bool:
    """Ghi ảnh an toàn với đường dẫn tiếng Việt trên Windows."""
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
# BỘ LỌC TRÙNG LẶP (DEDUPLICATOR)
# ==============================================================================
class Deduplicator:
    """Loại bỏ các ô vật phẩm trùng lặp khi người dùng vuốt cuộn màn hình."""
    def __init__(self, diff_threshold: float = 12.0):
        self.diff_threshold = diff_threshold
        self.saved_hashes: List[np.ndarray] = []

    def is_duplicate(self, img: np.ndarray) -> bool:
        if img is None or img.size == 0:
            return True
        h, w = img.shape[:2]
        crop_core = img[int(h * 0.15):int(h * 0.85), int(w * 0.15):int(w * 0.85)]
        thumb = cv2.resize(crop_core, (48, 48), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)

        for prev_hash in self.saved_hashes:
            diff = np.mean(np.abs(gray.astype(np.float32) - prev_hash.astype(np.float32)))
            if diff < self.diff_threshold:
                return True

        self.saved_hashes.append(gray)
        return False


# ==============================================================================
# BỘ TỰ ĐỘNG NHẬN DIỆN VÀ CẮT VẬT PHẨM BẤT KỲ (ITEM CARD DETECTOR)
# ==============================================================================
class HairstyleFilter:
    """Lấy hai tóc đặc biệt và mọi ô khuôn mặt tương tự mẫu.

    Dò hình tóc và kiểm tra riêng huy hiệu nguyên vẹn; ổ khóa chồng lên huy
    hiệu sẽ không đạt điều kiện xuất. Tất cả ảnh tóc khác đều bị bỏ qua.
    Mẫu đi kèm được lấy từ IMG_9799, không phụ thuộc input/output của acc.
    """

    _templates: Optional[Dict[str, np.ndarray]] = None
    # Làm việc ở nửa độ phân giải chuẩn, sau đó cắt trực tiếp ảnh nguồn.
    WORK_SIZE = (1389, 642)
    CARD_SIZE = 108
    CORE = (slice(15, 101), slice(5, 81))
    BADGE = (slice(3, 38), slice(82, 105))
    FACE_TEMPLATES = ("face_side", "face_front")
    TARGETS = (("hair_4", "tóc huy hiệu 4"), ("hair_5", "tóc huy hiệu 5"))

    @classmethod
    def _load_templates(cls) -> Dict[str, np.ndarray]:
        if cls._templates is None:
            templates = {}
            names = (
                "hair_title",
                "face_title",
                *cls.FACE_TEMPLATES,
                *(target[0] for target in cls.TARGETS),
                "hair_bui",
            )
            assets_dir = os.path.join(os.path.dirname(__file__), "assets")
            for name in names:
                path = os.path.join(assets_dir, name + ".png")
                if not os.path.exists(path):
                    continue
                image = cv2_imread_utf8(path)
                if image is None:
                    continue
                templates[name] = cv2.resize(image, None, fx=0.5, fy=0.5,
                                              interpolation=cv2.INTER_AREA)
            cls._templates = templates
        return cls._templates

    @classmethod
    def _working_image(cls, img: np.ndarray) -> np.ndarray:
        return cv2.resize(img, cls.WORK_SIZE, interpolation=cv2.INTER_AREA)

    @classmethod
    def _match_title(cls, work: np.ndarray, template_name: str) -> float:
        templates = cls._load_templates()
        if template_name not in templates:
            return 0.0
        region = cv2.cvtColor(work[50:100, 845:1030], cv2.COLOR_BGR2GRAY)
        title = cv2.cvtColor(templates[template_name], cv2.COLOR_BGR2GRAY)
        return float(cv2.minMaxLoc(cv2.matchTemplate(region, title, cv2.TM_CCOEFF_NORMED))[1])

    @classmethod
    def is_hair_screen(cls, img: np.ndarray) -> bool:
        """Nhận diện màn hình Ngoại hình: Kiểu tóc hoặc Khuôn mặt."""
        if img is None or img.size == 0 or img.shape[1] < img.shape[0] * 1.7:
            return False
        work = cls._working_image(img)
        hair_score = cls._match_title(work, "hair_title")
        face_score = cls._match_title(work, "face_title")
        return max(hair_score, face_score) >= 0.80

    @classmethod
    def crop_unlocked(cls, img: np.ndarray, target_size: Tuple[int, int],
                      border_margin: int, log_fn=print) -> List[np.ndarray]:
        work = cls._working_image(img)
        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        templates = cls._load_templates()
        # Bao gồm toàn bộ chiều dọc lưới: hàng có thể đổi vị trí khi cuộn.
        grid = gray[95:637, 850:1215]
        found = []

        def unlocked_without_badge(card: np.ndarray) -> bool:
            corner = card[4:35, 82:104]
            hsv = cv2.cvtColor(corner, cv2.COLOR_BGR2HSV)
            white = ((hsv[:, :, 2] > 190) & (hsv[:, :, 1] < 65)).astype(np.uint8)
            count, _, stats, _ = cv2.connectedComponentsWithStats(white, 8)
            largest = int(np.max(stats[1:, cv2.CC_STAT_AREA])) if count > 1 else 0
            return largest < 90

        def add_crop(x: int, y: int, label: str, trim: float,
                     trim_end_extra: float = 0.0) -> bool:
            sx, sy = img.shape[1] / 1389.0, img.shape[0] / 642.0
            x1, y1 = round((x + trim) * sx), round((y + trim) * sy)
            x2 = round((x + cls.CARD_SIZE - trim - trim_end_extra) * sx)
            y2 = round((y + cls.CARD_SIZE - trim - trim_end_extra) * sy)
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                return False
            found.append((y, x, cv2.resize(crop, target_size,
                                           interpolation=cv2.INTER_LANCZOS4)))
            log_fn(f"  [+] Cắt {label} đã mở khóa.")
            return True

        # Phân biệt màn hình Khuôn mặt và Kiểu tóc để chỉ xử lý đúng đối tượng
        hair_score = cls._match_title(work, "hair_title")
        face_score = cls._match_title(work, "face_title")
        is_face_screen = face_score >= 0.80 and face_score > hair_score

        # Dò các ô khuôn mặt mở khóa (trên màn Khuôn mặt hoặc màn Kiểu tóc có ô mặt)
        face_candidates = []
        face_core = (slice(10, 102), slice(10, 102))
        for name in cls.FACE_TEMPLATES:
            if name not in templates:
                continue
            reference = templates[name]
            core = cv2.cvtColor(reference[face_core], cv2.COLOR_BGR2GRAY)
            scores = cv2.matchTemplate(grid, core, cv2.TM_CCOEFF_NORMED)
            for _ in range(24):
                _, score, _, point = cv2.minMaxLoc(scores)
                if score < 0.45:
                    break
                px, py = point
                scores[max(0, py - 35):py + 36, max(0, px - 35):px + 36] = -1
                x, y = px + 840, py + 85
                if min(abs(x - col) for col in (859.5, 976.5, 1093.5)) > 10:
                    continue
                if y < 95 or y + cls.CARD_SIZE > 637:
                    continue
                face_candidates.append((float(score), x, y))

        kept_faces = []
        for _, x, y in sorted(face_candidates, reverse=True):
            if any(abs(x - px) < 45 and abs(y - py) < 45 for px, py in kept_faces):
                continue
            card = work[y:y + cls.CARD_SIZE, x:x + cls.CARD_SIZE]
            if not unlocked_without_badge(card):
                log_fn("  [-] Bỏ một ô khuôn mặt tương tự: đang bị khóa.")
                continue
            kept_faces.append((x, y))
            # Cắt sâu hơn để không còn khung xám quanh khuôn mặt.
            add_crop(x, y, "ô khuôn mặt tương tự mẫu",
                     max(4.0, border_margin / 2.0), trim_end_extra=4.0)

        # Màn hình Kiểu tóc: dò thêm búi tóc và tóc huy hiệu 4/5
        if not is_face_screen:
            # 1. Búi tóc (mẫu hair_bui: không huy hiệu, kiểm tra mở khóa)
            if "hair_bui" in templates:
                ref_bui = templates["hair_bui"]
                core_bui = cv2.cvtColor(ref_bui[cls.CORE], cv2.COLOR_BGR2GRAY)
                scores_bui = cv2.matchTemplate(grid, core_bui, cv2.TM_CCOEFF_NORMED)
                for _ in range(6):
                    _, score, _, point = cv2.minMaxLoc(scores_bui)
                    if score < 0.65:
                        break
                    px, py = point
                    scores_bui[max(0, py - 40):py + 41, max(0, px - 40):px + 41] = -1
                    x, y = px + 845, py + 80
                    if min(abs(x - col) for col in (859.5, 976.5, 1093.5)) > 10:
                        continue
                    if y < 95 or y + cls.CARD_SIZE > 637:
                        continue
                    card = work[y:y + cls.CARD_SIZE, x:x + cls.CARD_SIZE]
                    if not unlocked_without_badge(card):
                        log_fn("  [-] Bỏ búi tóc: đang bị khóa.")
                        continue
                    add_crop(x, y, "búi tóc", max(0, border_margin) / 2.0)
                    break

            # 2. Hai tóc huy hiệu 4/5
            for name, label in cls.TARGETS:
                if name not in templates:
                    continue
                reference = templates[name]
                core = cv2.cvtColor(reference[cls.CORE], cv2.COLOR_BGR2GRAY)
                scores = cv2.matchTemplate(grid, core, cv2.TM_CCOEFF_NORMED)
                for _ in range(6):
                    _, score, _, point = cv2.minMaxLoc(scores)
                    if score < 0.70:
                        break
                    px, py = point
                    scores[max(0, py - 40):py + 41, max(0, px - 40):px + 41] = -1
                    x, y = px + 845, py + 80
                    if min(abs(x - col) for col in (859.5, 976.5, 1093.5)) > 10:
                        continue
                    if y < 95 or y + cls.CARD_SIZE > 637:
                        continue
                    card = work[y:y + cls.CARD_SIZE, x:x + cls.CARD_SIZE]
                    badge = card[1:40, 80:107]
                    expected = reference[cls.BADGE]
                    badge_score = cv2.minMaxLoc(cv2.matchTemplate(
                        badge, expected, cv2.TM_CCOEFF_NORMED))[1]
                    if badge_score < 0.85:
                        log_fn(f"  [-] Bỏ {label}: bị khóa hoặc huy hiệu không rõ.")
                        continue
                    add_crop(x, y, label, max(0, border_margin) / 2.0)
                    break

        found.sort(key=lambda item: (item[0], item[1]))
        log_fn(f"  [+] Kiểu tóc/khuôn mặt: đã lấy {len(found)} ô hợp lệ đã mở khóa.")
        return [item[2] for item in found]


class ItemCardDetector:
    """
    Tự động nhận diện từng ô vật phẩm trong lưới 3 cột:
    1. Dò pha cuộn qua các mép ngang lặp lại của lưới.
    2. Chỉ cắt các khung đầy đủ nằm trong vùng Item bên phải.
    3. Cắt sát viền trong và loại ô trống.
    4. Chuẩn hóa kích thước đầu ra theo target_size (216 x 216 px).
    """

    def __init__(self, target_size: Tuple[int, int] = (216, 216), border_margin: int = 5):
        self.target_width, self.target_height = target_size
        self.border_margin = border_margin

    @staticmethod
    def _box_iou(b1: Tuple[int, int, int, int], b2: Tuple[int, int, int, int]) -> float:
        """Tính IoU giữa 2 bounding box (x, y, w, h)."""
        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[0] + b1[2], b2[0] + b2[2])
        y2 = min(b1[1] + b1[3], b2[1] + b2[3])

        inter_w = max(0, x2 - x1)
        inter_h = max(0, y2 - y1)
        inter_area = inter_w * inter_h
        if inter_area <= 0:
            return 0.0

        area1 = b1[2] * b1[3]
        area2 = b2[2] * b2[3]
        union_area = area1 + area2 - inter_area
        return inter_area / float(union_area) if union_area > 0 else 0.0

    @staticmethod
    def _detect_boxes_by_contours(img: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Phát hiện các ô item bằng Contour & Edge Analysis."""
        H, W = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Ngưỡng kích thước ô item tương thích đa độ phân giải
        min_w = int(0.045 * W)
        max_w = int(0.18 * W)
        min_h = int(0.09 * H)
        max_h = int(0.28 * H)

        detected_boxes = []

        # Chạy đa ngưỡng (Multi-threshold Canny & Adaptive) để bắt trọn viền
        edge_methods = [
            cv2.Canny(gray, 30, 90),
            cv2.Canny(gray, 50, 150),
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 3)
        ]

        for edges in edge_methods:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                aspect = w / float(max(1, h))

                # Ô item có dạng gần vuông: tỉ lệ rộng/cao ~ 0.82 đến 1.25
                if 0.82 <= aspect <= 1.25 and min_w <= w <= max_w and min_h <= h <= max_h:
                    # Bỏ qua các ô quá sát mép trên/dưới bị cắt lửng do cuộn
                    if y < 15 or (y + h) > (H - 15):
                        continue

                    # Bỏ qua khu vực điều hướng bên trái / trên cùng
                    if x < int(0.35 * W):
                        continue

                    detected_boxes.append((x, y, w, h))

        if not detected_boxes:
            return []

        # Khử trùng lặp box (Non-Maximum Suppression theo IoU)
        detected_boxes = sorted(detected_boxes, key=lambda b: (b[1], b[0]))
        unique_boxes = []
        for b in detected_boxes:
            overlap = False
            for u in unique_boxes:
                if ItemCardDetector._box_iou(b, u) > 0.40:
                    overlap = True
                    break
            if not overlap:
                unique_boxes.append(b)

        return unique_boxes

    @staticmethod
    def _detect_boxes_by_grid_search(img: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Dò từng hàng đủ ba ô, không phụ thuộc vị trí cuộn.

        Mỗi hàng chỉ được nhận khi cả mép trên và mép dưới của ba ô cùng xuất
        hiện. Nhờ vậy cạnh dưới của thanh tìm kiếm không còn bị nhầm là đầu
        hàng, ảnh chỉ có một hàng đầy đủ vẫn được cắt, còn hàng cuối thiếu một
        hoặc hai ô sẽ bị bỏ qua.
        """
        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        col_coords_base = [
            (1718, 1939),
            (1955, 2176),
            (2191, 2411),
        ]
        cols = [
            (int(round(c[0] * scale_x)), int(round(c[1] * scale_x)))
            for c in col_coords_base
        ]
        slot_h = max(80, int(round(250 * scale_y)))
        step_y = max(slot_h + 4, int(round(267 * scale_y)))
        min_full_y = int(round(175 * scale_y))
        bottom_limit = H - max(8, int(round(10 * scale_y)))

        inner_ranges = [
            (1730, 1927),
            (1967, 2164),
            (2203, 2399),
        ]
        row_diffs = []
        for x1, x2 in inner_ranges:
            sx1 = max(0, int(round(x1 * scale_x)))
            sx2 = min(W, int(round(x2 * scale_x)))
            if sx2 > sx1:
                gray = cv2.cvtColor(img[:, sx1:sx2], cv2.COLOR_BGR2GRAY)
                row_diffs.append(np.mean(
                    np.abs(np.diff(gray.astype(np.float32), axis=0)), axis=1
                ))
        if len(row_diffs) != 3:
            return []
        search_radius = max(2, int(round(4 * scale_y)))

        def peak(diff: np.ndarray, position: int) -> Tuple[int, float]:
            lo = max(0, position - search_radius)
            hi = min(len(diff), position + search_radius + 1)
            if hi <= lo:
                return position, 0.0
            local_index = int(np.argmax(diff[lo:hi]))
            index = lo + local_index
            return index, float(diff[index])

        # Quét mọi vị trí Y thay vì ép các hàng vào một pha duy nhất. Điểm
        # trung vị chịu được ô đang chọn có viền cam khác màu; điểm nhỏ nhất
        # vẫn buộc cả ba ô phải có đủ hai mép.
        candidates = []
        last_nominal_y = bottom_limit - slot_h
        for nominal_y in range(min_full_y, max(min_full_y, last_nominal_y) + 1):
            top_positions = []
            bottom_positions = []
            per_column_scores = []
            for diff in row_diffs:
                top_pos, top_strength = peak(diff, nominal_y)
                bottom_pos, bottom_strength = peak(diff, nominal_y + slot_h - 1)
                top_positions.append(top_pos)
                bottom_positions.append(bottom_pos)
                per_column_scores.append(min(top_strength, bottom_strength))

            median_score = float(np.median(per_column_scores))
            weakest_score = float(np.min(per_column_scores))
            if median_score < 16.0 or weakest_score < 7.0:
                continue

            top_y = int(round(float(np.median(top_positions))))
            bottom_y = int(round(float(np.median(bottom_positions))))
            detected_h = bottom_y - top_y + 1
            if not int(round(0.94 * slot_h)) <= detected_h <= int(round(1.06 * slot_h)):
                continue
            score = (
                median_score
                + 0.20 * float(np.mean(per_column_scores))
                + 0.10 * weakest_score
            )
            candidates.append((score, top_y, bottom_y))

        if not candidates:
            return []

        # NMS theo trục Y: một hàng tạo ra nhiều ứng viên lân cận do cửa sổ
        # tìm mép; chỉ giữ ứng viên mạnh nhất của mỗi hàng thật.
        selected_rows = []
        min_row_distance = 0.55 * step_y
        for score, top_y, bottom_y in sorted(candidates, reverse=True):
            if any(abs(top_y - saved_top) <= min_row_distance for _, saved_top, _ in selected_rows):
                continue
            selected_rows.append((score, top_y, bottom_y))

        boxes = []
        for _, top_y, bottom_y in sorted(selected_rows, key=lambda row: row[1]):
            detected_h = bottom_y - top_y + 1
            if top_y < 0 or top_y + detected_h > bottom_limit:
                continue
            for c_left, c_right in cols:
                boxes.append((c_left, top_y, c_right - c_left, detected_h))

        return boxes

    @staticmethod
    def _looks_like_item_card(raw_crop: np.ndarray) -> bool:
        """Loại ô trống nhưng vẫn giữ thẻ xám/không có viền màu."""
        if raw_crop is None or raw_crop.size == 0 or float(np.std(raw_crop)) < 16.0:
            return False
        hsv = cv2.cvtColor(raw_crop, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        card_background = (value < 185) | (saturation > 45)
        return float(np.mean(card_background)) >= 0.55

    def detect_and_crop(self, img: np.ndarray, log_fn=print) -> List[np.ndarray]:
        """
        Nhận diện tất cả các ô vật phẩm trong ảnh và cắt sát viền trong.
        Tự động nhận diện vị trí bất kỳ và sắp xếp theo thứ tự hiển thị tự nhiên.
        """
        if img is None or img.size == 0:
            return []

        if HairstyleFilter.is_hair_screen(img):
            # Kể cả không có tóc mở khóa, không rơi xuống bộ cắt item chung.
            return HairstyleFilter.crop_unlocked(
                img, (self.target_width, self.target_height), self.border_margin, log_fn)

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        # Chỉ quét vùng lưới 3 cột. Dò contour toàn màn hình từng lấy nhầm
        # icon nằm trong thẻ và cả ô thông tin chi tiết ở bên trái.
        boxes = self._detect_boxes_by_grid_search(img)

        if not boxes:
            log_fn("  [!] Không tìm thấy ô vật phẩm nào trong ảnh!")
            return []

        # 3. Sắp xếp các ô từ trên xuống dưới, từ trái sang phải
        # Nhóm theo hàng (sai lệch Y < 35% chiều cao)
        boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
        rows: List[List[Tuple[int, int, int, int]]] = []
        for b in boxes:
            placed = False
            for r in rows:
                if abs(b[1] - r[0][1]) < int(0.35 * b[3]):
                    r.append(b)
                    placed = True
                    break
            if not placed:
                rows.append([b])

        sorted_boxes = []
        for r in rows:
            r_sorted = sorted(r, key=lambda b: b[0])
            sorted_boxes.extend(r_sorted)

        # 4. Cắt và chuẩn hóa từng ô
        cropped_items = []
        m = self.border_margin

        for idx, (x, y, w, h) in enumerate(sorted_boxes):
            # Cắt ảnh thô
            raw_crop = img[y:y + h, x:x + w]
            if raw_crop.size == 0:
                continue

            # Bỏ qua ô trống nhưng vẫn giữ vật phẩm có thẻ nền xám.
            if not self._looks_like_item_card(raw_crop):
                continue

            # Cắt sát viền trong (loại bỏ viền khung ngoài)
            crop_h, crop_w = raw_crop.shape[:2]
            margin_x = max(1, int(round(m * scale_x)))
            margin_y = max(1, int(round(m * scale_y)))
            inner_x1 = margin_x
            inner_y1 = margin_y
            inner_x2 = crop_w - margin_x
            inner_y2 = crop_h - margin_y

            inner = raw_crop[inner_y1:inner_y2, inner_x1:inner_x2]
            if inner.size == 0 or inner.shape[0] < 10 or inner.shape[1] < 10:
                continue

            # Chuẩn hóa kích thước chuẩn 216x216
            res = cv2.resize(inner, (self.target_width, self.target_height), interpolation=cv2.INTER_LANCZOS4)
            cropped_items.append(res)

        log_fn(f"  [+] Nhận diện và cắt thành công {len(cropped_items)} ô vật phẩm.")
        return cropped_items


# ==============================================================================
# HÀM XỬ LÝ HÀNG LOẠT (PROCESS BATCH)
# ==============================================================================
def process_batch(
    input_dir: str,
    output_dir: str,
    enable_dedup: bool = True,
    border_margin: int = 5,
    target_size: Tuple[int, int] = (216, 216),
    file_prefix: str = "item_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    on_card_saved_fn=None
) -> Dict:
    """Hàm xử lý hàng loạt cắt ảnh Item tự động."""
    os.makedirs(output_dir, exist_ok=True)
    global_out_dir = None
    if sync_global_output and acc_id:
        global_out_dir = os.path.join(PROJECT_ROOT, "output", acc_id)
        os.makedirs(global_out_dir, exist_ok=True)

    supported_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
    files = []
    if os.path.exists(input_dir):
        for root, _, fnames in os.walk(input_dir):
            for fname in fnames:
                if os.path.splitext(fname)[1].lower() in supported_exts:
                    files.append(os.path.join(root, fname))
    files = sorted(list(set(files)))

    total_files = len(files)
    log_fn(f"[*] Tìm thấy {total_files} ảnh chụp màn hình trong '{input_dir}'.")
    if total_files == 0:
        return {"total_saved": 0, "total_files": 0}

    detector = ItemCardDetector(target_size=target_size, border_margin=border_margin)
    deduplicator = Deduplicator() if enable_dedup else None
    saved_count = 0

    for idx, fpath in enumerate(files):
        fname = os.path.basename(fpath)
        log_fn(f"\n[{idx + 1}/{total_files}] Đang xử lý: {fname}")

        img = cv2_imread_utf8(fpath)
        if img is None:
            log_fn(f"  [-] Bỏ qua ảnh lỗi: {fname}")
            continue

        items = detector.detect_and_crop(img, log_fn=log_fn)
        img_saved_count = 0

        for item_img in items:
            if deduplicator and deduplicator.is_duplicate(item_img):
                continue

            saved_count += 1
            img_saved_count += 1
            out_name = f"{file_prefix}{saved_count:03d}.png"
            out_path = os.path.join(output_dir, out_name)
            cv2_imwrite_utf8(out_path, item_img)

            if global_out_dir:
                global_path = os.path.join(global_out_dir, out_name)
                cv2_imwrite_utf8(global_path, item_img)

            if on_card_saved_fn:
                on_card_saved_fn(out_path, item_img)

        log_fn(f"  [✓] {fname} ➔ Đã lưu {img_saved_count} ô item.")

    log_fn(f"\n[✓] HOÀN TẤT: Đã cắt & lưu tổng cộng {saved_count} ảnh item vào '{output_dir}'.")
    return {"total_saved": saved_count, "total_files": total_files}


# ==============================================================================
# GIAO DIỆN GUI CHO TOOL CẮT ITEM
# ==============================================================================
class ItemCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TOOL CẮT ẢNH ITEM / VẬT PHẨM TỰ ĐỘNG - KHO ĐỒ")
        self.root.geometry("1000x720")
        self.root.minsize(860, 600)

        self.bg_color = "#1e1e2e"
        self.card_bg = "#252538"
        self.fg_color = "#cdd6f4"
        self.accent = "#89b4fa"
        self.btn_green = "#a6e3a1"
        self.root.configure(bg=self.bg_color)

        self.input_dir_var = tk.StringVar(value=os.path.join(os.path.dirname(os.path.abspath(__file__)), "input"))
        self.output_dir_var = tk.StringVar(value=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"))
        self.dedup_var = tk.BooleanVar(value=True)
        self.is_processing = False
        self.preview_images: List[ImageTk.PhotoImage] = []

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self.root, bg=self.bg_color, pady=10)
        header.pack(fill=tk.X, padx=20)

        tk.Label(
            header,
            text="🎁 TOOL CẮT ẢNH ITEM / VẬT PHẨM TỰ ĐỘNG",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.accent
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Tự động nhận diện mọi vật phẩm bất kỳ, cắt sát viền chuẩn 216x216 px đồng nhất",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg="#a6adc8"
        ).pack(anchor="w")

        body = tk.Frame(self.root, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        left_col = tk.Frame(body, bg=self.card_bg, padx=15, pady=15)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        tk.Label(left_col, text="CẤU HÌNH THƯ MỤC", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.accent).pack(anchor="w", pady=(0, 8))

        tk.Label(left_col, text="Thư mục Input:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        in_frame = tk.Frame(left_col, bg=self.card_bg)
        in_frame.pack(fill=tk.X, pady=(2, 8))
        tk.Entry(in_frame, textvariable=self.input_dir_var, font=("Segoe UI", 9), bg="#313244", fg=self.fg_color, width=28).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(in_frame, text="Chọn", font=("Segoe UI", 8), bg="#45475a", fg=self.fg_color, command=self._browse_input).pack(side=tk.LEFT)

        tk.Label(left_col, text="Thư mục Output:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        out_frame = tk.Frame(left_col, bg=self.card_bg)
        out_frame.pack(fill=tk.X, pady=(2, 12))
        tk.Entry(out_frame, textvariable=self.output_dir_var, font=("Segoe UI", 9), bg="#313244", fg=self.fg_color, width=28).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(out_frame, text="Chọn", font=("Segoe UI", 8), bg="#45475a", fg=self.fg_color, command=self._browse_output).pack(side=tk.LEFT)

        tk.Checkbutton(
            left_col,
            text="Lọc bỏ vật phẩm trùng lặp khi cuộn",
            variable=self.dedup_var,
            font=("Segoe UI", 9),
            bg=self.card_bg,
            fg=self.fg_color,
            selectcolor="#313244",
            activebackground=self.card_bg
        ).pack(anchor="w", pady=(0, 15))

        self.btn_run = tk.Button(
            left_col,
            text="🚀 BẮT ĐẦU CẮT ITEM",
            font=("Segoe UI", 12, "bold"),
            bg=self.btn_green,
            fg="#11111b",
            relief=tk.FLAT,
            pady=10,
            command=self._start_process
        )
        self.btn_run.pack(fill=tk.X, pady=(0, 8))

        btn_open_out = tk.Button(
            left_col,
            text="📂 Mở Thư Mục Kết Quả",
            font=("Segoe UI", 9),
            bg="#45475a",
            fg=self.fg_color,
            relief=tk.FLAT,
            pady=4,
            command=self._open_output
        )
        btn_open_out.pack(fill=tk.X)

        right_col = tk.Frame(body, bg=self.bg_color)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        preview_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        preview_panel.pack(fill=tk.X, pady=(0, 8))

        tk.Label(preview_panel, text="XEM TRƯỚC VẬT PHẨM VỪA CẮT", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent).pack(anchor="w", pady=(0, 4))

        self.preview_frame = tk.Frame(preview_panel, bg=self.card_bg)
        self.preview_frame.pack(fill=tk.X)
        self.preview_labels = []
        for i in range(5):
            lbl = tk.Label(self.preview_frame, bg="#11111b", width=12, height=6, relief=tk.RIDGE, bd=1)
            lbl.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.BOTH)
            self.preview_labels.append(lbl)

        log_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        log_panel.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_panel, text="NHẬT KÝ XỬ LÝ", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent).pack(anchor="w", pady=(0, 4))

        self.log_text = tk.Text(log_panel, font=("Consolas", 9), bg="#11111b", fg="#a6adc8", relief=tk.FLAT)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = tk.Scrollbar(log_panel, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def log(self, msg: str):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def _browse_input(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get())
        if d: self.input_dir_var.set(d)

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if d: self.output_dir_var.set(d)

    def _open_output(self):
        d = self.output_dir_var.get()
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _add_preview(self, path: str, img_bgr: np.ndarray):
        try:
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            thumb = cv2.resize(img_rgb, (80, 80), interpolation=cv2.INTER_AREA)
            pil_img = Image.fromarray(thumb)
            tk_img = ImageTk.PhotoImage(pil_img)
            self.preview_images.append(tk_img)
            if len(self.preview_images) > 5:
                self.preview_images.pop(0)

            for idx, img_obj in enumerate(self.preview_images):
                if idx < len(self.preview_labels):
                    self.preview_labels[idx].configure(image=img_obj)
        except Exception:
            pass

    def _start_process(self):
        if self.is_processing: return
        in_dir = self.input_dir_var.get()
        out_dir = self.output_dir_var.get()

        if not os.path.exists(in_dir):
            messagebox.showwarning("Cảnh báo", "Thư mục Input không tồn tại!")
            return

        self.is_processing = True
        self.btn_run.configure(state=tk.DISABLED, text="⏳ ĐANG CẮT...", bg="#6c7086")
        self.log_text.delete(1.0, tk.END)

        def thread_fn():
            res = process_batch(
                input_dir=in_dir,
                output_dir=out_dir,
                enable_dedup=self.dedup_var.get(),
                log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview(p, im))
            )

            def finish():
                self.is_processing = False
                self.btn_run.configure(state=tk.NORMAL, text="🚀 BẮT ĐẦU CẮT ITEM", bg=self.btn_green)
                messagebox.showinfo("Thành công", f"Đã cắt xong {res['total_saved']} ảnh item!")

            self.root.after(0, finish)

        threading.Thread(target=thread_fn, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Tool cắt ảnh Item tự động")
    parser.add_argument("--cli", action="store_true", help="Chạy chế độ dòng lệnh CLI")
    parser.add_argument("-i", "--input", default="input", help="Thư mục input")
    parser.add_argument("-o", "--output", default="output", help="Thư mục output")
    parser.add_argument("-a", "--acc", default=None, help="Mã tài khoản")
    args = parser.parse_args()

    if args.cli:
        process_batch(
            input_dir=args.input,
            output_dir=args.output,
            acc_id=args.acc,
            log_fn=print
        )
    else:
        root = tk.Tk()
        app = ItemCropperGUI(root)
        if args.input != "input":
            app.input_dir_var.set(args.input)
        if args.output != "output":
            app.output_dir_var.set(args.output)
        root.mainloop()


if __name__ == "__main__":
    main()
