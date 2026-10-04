#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool tự động nhận diện và cắt ảnh Trang Phục / Nhân Vật Toàn Thân (Outfit Showcase / Full Body Character)
- Tự động định vị và cắt chính xác nhân vật đứng tạo dáng toàn thân trong Kho Đồ (không có popup chi tiết)
- Chuẩn hóa kích thước đầu ra đồng nhất 100% (774 x 1220 px hoặc theo tùy chọn)
- Hỗ trợ xử lý hàng loạt mọi định dạng ảnh (PNG, JPG, WEBP)
- Hỗ trợ chọn MÃ ACC, đặt tên chuẩn tp_001.png,... và đồng bộ ra d:\\Ghep-Anh\\output\\<mã_acc>\\
- Hỗ trợ cả giao diện đồ họa (GUI) trực quan và chạy nhanh qua dòng lệnh (CLI)
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


# ==============================================================================
# HÀM XỬ LÝ ẢNH HỖ TRỢ ĐƯỜNG DẪN UNICODE TRÊN WINDOWS
# ==============================================================================
def cv2_imread_utf8(path: str) -> Optional[np.ndarray]:
    """Đọc ảnh an toàn với đường dẫn có dấu tiếng Việt trên Windows."""
    try:
        if not os.path.exists(path):
            return None
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"[Lỗi đọc ảnh] {path}: {e}")
        return None


def cv2_imwrite_utf8(path: str, img: np.ndarray, quality: int = 95) -> bool:
    """Ghi ảnh an toàn với đường dẫn có dấu tiếng Việt trên Windows."""
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
# BỘ NHẬN DIỆN VÀ CẮT TRANG PHỤC (OUTFIT DETECTOR)
# ==============================================================================
class OutfitDetector:
    """
    Module tự động định vị và cắt trang phục / nhân vật toàn thân:
    - Cắt chuẩn xác theo mẫu nhân vật đứng tạo dáng bên trái kho đồ
    - Sảnh thường: giữ khung cũ và tự cân vị trí ngang theo acc.
    - Sảnh siêu xe: khung riêng x=786, y=123, w=642, h=994 ở 2778x1284.
    - Chuẩn hóa kích thước đầu ra đúng target_size (774 x 1220 px)
    """

    NORMAL_LOBBY = "normal"
    SUPERCAR_LOBBY = "supercar"
    LOBBY_LABELS = {NORMAL_LOBBY: "Sảnh thường", SUPERCAR_LOBBY: "Sảnh siêu xe"}
    SUPERCAR_CROP = (786, 123, 642, 994)
    _supercar_ceiling: Optional[np.ndarray] = None

    def __init__(self, target_size: Tuple[int, int] = (774, 1220)):
        self.target_width, self.target_height = target_size
        self._batch_anchor_x: Optional[float] = None

    @classmethod
    def _matches_supercar_lobby(cls, img: np.ndarray) -> bool:
        """So hình học trần đèn của sảnh mẫu, tránh nhận nhầm chỉ vì có xe/nền tối.

        Vùng (0, 0, 1500, 280) nằm trên nhân vật sảnh siêu xe, ngoài lưới đồ
        và nút nâng cấp. Mẫu xám thu nhỏ đi kèm tool, không cần ảnh trong input.
        Tương quan chuẩn hóa chịu được thay đổi độ sáng và ảnh nén/thu nhỏ.
        """
        if cls._supercar_ceiling is None:
            path = os.path.join(os.path.dirname(__file__), "assets", "supercar_ceiling.png")
            reference = cv2_imread_utf8(path)
            if reference is None:
                raise FileNotFoundError(f"Thiếu mẫu nhận diện sảnh siêu xe: {path}")
            cls._supercar_ceiling = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)

        height, width = img.shape[:2]
        roi = img[:max(1, round(280 * height / 1284.0)),
                  :max(1, round(1500 * width / 2778.0))]
        reference = cls._supercar_ceiling
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        thumbnail = cv2.resize(gray, (reference.shape[1], reference.shape[0]),
                               interpolation=cv2.INTER_AREA)
        score = float(cv2.matchTemplate(thumbnail, reference, cv2.TM_CCOEFF_NORMED)[0, 0])
        return score >= 0.80

    @classmethod
    def detect_lobby_type(cls, img: np.ndarray) -> Optional[str]:
        """Phân biệt hai sảnh sau khi xác nhận đây là màn trang phục toàn thân."""
        if img is None or not cls._is_full_body_outfit_screen(img):
            return None
        return cls.SUPERCAR_LOBBY if cls._matches_supercar_lobby(img) else cls.NORMAL_LOBBY

    @staticmethod
    def _selected_indicator_y(
        img: np.ndarray,
        base_x1: float,
        base_x2: float,
    ) -> Optional[float]:
        """Tìm vạch xanh bằng ngưỡng chuẩn, sau đó thử ngưỡng màu dự phòng."""
        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        x1 = max(0, int(round(base_x1 * scale_x)))
        x2 = min(width, int(round(base_x2 * scale_x)))

        color_ranges = (
            ((100, 120, 120), (130, 255, 255)),
            ((92, 65, 75), (142, 255, 255)),
        )
        for lower, upper in color_ranges:
            blue = cv2.inRange(
                hsv,
                np.array(lower, dtype=np.uint8),
                np.array(upper, dtype=np.uint8),
            )
            strip = (blue[:, x1:x2] > 0).astype(np.uint8)
            if strip.size == 0:
                continue

            count, _, stats, centers = cv2.connectedComponentsWithStats(strip, 8)
            min_height = max(18, int(round(42 * scale_y)))
            candidates = []
            for index in range(1, count):
                _, _, comp_w, comp_h, area = stats[index]
                if comp_h < min_height or area < max(24, int(round(65 * scale_x * scale_y))):
                    continue
                score = float(area) * min(8.0, comp_h / max(1.0, float(comp_w))) * comp_h
                candidates.append((score, float(centers[index][1]) / scale_y))
            if candidates:
                return max(candidates, key=lambda item: item[0])[1]
        return None

    @classmethod
    def _selected_subtab_y(cls, img: np.ndarray) -> Optional[float]:
        """Tìm vạch xanh của mục con trong tab Trang Phục."""
        return cls._selected_indicator_y(img, 2390, 2495)

    @classmethod
    def _selected_main_tab_y(cls, img: np.ndarray) -> Optional[float]:
        """Tìm vạch xanh của tab Kho Đồ ngoài cùng bên phải."""
        return cls._selected_indicator_y(img, 2520, 2620)

    @staticmethod
    def _has_wardrobe_layout(img: np.ndarray) -> bool:
        """Chặn sảnh/profile giả vạch xanh, chỉ giữ giao diện Kho Đồ thật."""
        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        grid = img[
            int(round(180 * scale_y)):int(round(1130 * scale_y)),
            int(round(1710 * scale_x)):min(width, int(round(2415 * scale_x))),
        ]
        if grid.size == 0 or float(np.std(grid)) < 22.0:
            return False

        rail = img[:, int(round(2390 * scale_x)):min(width, int(round(2495 * scale_x)))]
        if rail.size == 0 or rail.shape[0] < 2:
            return False
        rail_gray = cv2.cvtColor(rail, cv2.COLOR_BGR2GRAY).astype(np.float32)
        row_change = np.mean(np.abs(np.diff(rail_gray, axis=0)), axis=1)
        rail_limit = 14.0 + max(0.0, min(6.0, (1.0 / max(scale_y, 0.25) - 1.0) * 4.0))
        return float(np.percentile(row_change, 95)) <= rail_limit

    @staticmethod
    def _has_item_detail_popup(img: np.ndarray) -> bool:
        """Nhận bảng chi tiết để giữ hai tool Đồ và Trang Phục tách biệt."""
        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        y1 = max(0, int(round(930 * scale_y)))
        y2 = min(height, int(round(1240 * scale_y)))
        radius = max(2, int(round(5 * scale_x)))
        scores = []
        for base_x in (1325, 1685):
            x = int(round(base_x * scale_x))
            band = gray[
                y1:y2,
                max(0, x - radius):min(width, x + radius + 1),
            ]
            if band.shape[0] < 2 or band.shape[1] < 2:
                return False
            scores.append(float(np.mean(np.abs(np.diff(band, axis=1)))))
        threshold = 2.82 * max(1.0, max(scale_y, 0.25) ** -0.80)
        return min(scores) >= threshold

    @classmethod
    def _is_full_body_outfit_screen(cls, img: np.ndarray) -> bool:
        """Kiểm tra ảnh hợp lệ để cắt: ảnh ngang, không rỗng và có vùng giao diện bên phải."""
        if img is None or getattr(img, "size", 0) == 0:
            return False
        height, width = img.shape[:2]
        if width < height:
            return False
        # Chặn ảnh rỗng/đen hoàn toàn hoặc bị che mất vùng giao diện kho đồ bên phải
        wardrobe_roi = img[:, int(1700 * width / 2778.0):]
        if wardrobe_roi.size == 0 or float(np.std(wardrobe_roi)) < 15.0:
            return False
        return True

    @staticmethod
    def _estimate_character_anchor_x(img: np.ndarray) -> Optional[float]:
        """Ước lượng tâm ngang của nhân vật bằng vùng có mật độ biên cao."""
        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        x1 = max(0, int(round(250 * scale_x)))
        x2 = min(width, int(round(1500 * scale_x)))
        y1 = max(0, int(round(80 * scale_y)))
        y2 = min(height, int(round(1180 * scale_y)))
        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edge_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
        edge_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
        profile = np.mean(edge_x + edge_y, axis=0)
        window = max(80, int(round(350 * scale_x)))
        if profile.size <= window:
            return None
        scores = np.convolve(profile, np.ones(window, dtype=np.float32), mode="valid")
        left = int(np.argmax(scores))
        return float(x1 + left + window / 2.0) / scale_x

    def calibrate_batch(self, images: List[np.ndarray], log_fn=print) -> None:
        """Chỉ cân sảnh thường; sảnh siêu xe không được kéo lệch khung của nhóm này."""
        self._batch_anchor_x = None
        anchors = [
            anchor
            for image in images
            if self.detect_lobby_type(image) == self.NORMAL_LOBBY
            for anchor in [self._estimate_character_anchor_x(image)]
            if anchor is not None and 600.0 <= anchor <= 1300.0
        ]
        if anchors:
            self._batch_anchor_x = float(np.median(anchors))
            log_fn(f"[*] Đã tự cân vị trí nhân vật sảnh thường: anchor_x={self._batch_anchor_x:.1f}")

    def detect_and_crop(self, img: np.ndarray, log_fn=print) -> Optional[np.ndarray]:
        """
        Định vị khung nhân vật toàn thân và cắt ảnh chuẩn.
        """
        if img is None:
            return None

        lobby_type = self.detect_lobby_type(img)
        if lobby_type is None:
            log_fn("  [X] Không phải màn Trang Phục toàn thân (đã chặn ảnh Balo/Mặt Nạ/khác).")
            return None

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        if lobby_type == self.SUPERCAR_LOBBY:
            # Khớp chính xác ảnh mẫu số 5; không bám theo súng, rương hay xe.
            crop_x_base, crop_y_base, crop_w_base, crop_h_base = self.SUPERCAR_CROP
        else:
            # Cắt sảnh thường: mẫu IMG_7944 có anchor≈842, x=408 (đẩy khung qua trái 88px để nhân vật ở giữa).
            anchor_x = self._batch_anchor_x
            if anchor_x is None:
                anchor_x = self._estimate_character_anchor_x(img) or 842.0
            if abs(anchor_x - 842.0) <= 30.0:
                anchor_x = 842.0
            crop_x_base = max(120.0, min(408.0 + (anchor_x - 842.0), 920.0))
            crop_y_base, crop_w_base, crop_h_base = 0, 774, 1220

        x = int(round(crop_x_base * scale_x))
        y = int(round(crop_y_base * scale_y))
        w = int(round(crop_w_base * scale_x))
        h = int(round(crop_h_base * scale_y))

        # Đảm bảo không vượt quá biên ảnh
        x = max(0, min(x, W - 10))
        y = max(0, min(y, H - 10))
        w = min(w, W - x)
        h = min(h, H - y)

        log_fn(
            f"  [+] Cắt Trang Phục — {self.LOBBY_LABELS[lobby_type]}: "
            f"x={x}, y={y}, w={w}, h={h}"
        )

        crop = img[y:y+h, x:x+w]
        if crop.size == 0:
            log_fn("  [X] Vùng cắt không hợp lệ!")
            return None

        # Chuẩn hóa kích thước đầu ra đúng target_size (774 x 1220)
        if crop.shape[1] != self.target_width or crop.shape[0] != self.target_height:
            crop_normalized = cv2.resize(
                crop,
                (self.target_width, self.target_height),
                interpolation=cv2.INTER_LANCZOS4
            )
        else:
            crop_normalized = crop.copy()

        return crop_normalized


# ==============================================================================
# BỘ QUẢN LÝ XỬ LÝ HÀNG LOẠT (PROCESS MANAGER)
# ==============================================================================
def process_batch(
    input_dir: str,
    output_dir: str,
    target_size: Tuple[int, int] = (774, 1220),
    file_prefix: str = "tp_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    progress_fn=None,
    on_card_saved_fn=None
) -> Dict:
    """
    Hàm xử lý cắt ảnh trang phục / nhân vật hàng loạt từ input sang output.
    Hỗ trợ đồng bộ sang d:\\Ghep-Anh\\output\\<mã_acc>\\
    """
    os.makedirs(output_dir, exist_ok=True)

    # Thư mục tổng của toàn bộ project
    global_out_dir = None
    if sync_global_output and acc_id:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
        global_out_dir = os.path.join(root_dir, "output", acc_id)
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
    if total_files == 0:
        log_fn(f"[!] Không tìm thấy ảnh nào trong thư mục: {input_dir}")
        return {"total_files": 0, "total_saved": 0}

    log_fn(f"[*] Tìm thấy {total_files} ảnh cần xử lý trong '{input_dir}'")
    log_fn(f"[*] Thư mục lưu cục bộ: '{output_dir}'")
    if global_out_dir:
        log_fn(f"[*] Thư mục lưu đồng bộ tổng: '{global_out_dir}'")
    log_fn(f"[*] Kích thước chuẩn đầu ra: {target_size[0]}x{target_size[1]} px")
    log_fn(f"[*] Tiền tố tên file kết quả: '{file_prefix}'")
    log_fn("-" * 60)

    detector = OutfitDetector(target_size=target_size)
    calibration_images = []
    for calibration_path in files:
        calibration_img = cv2_imread_utf8(calibration_path)
        if detector.detect_lobby_type(calibration_img) == detector.NORMAL_LOBBY:
            calibration_images.append(calibration_img)
            if len(calibration_images) >= 24:
                break
    detector.calibrate_batch(calibration_images, log_fn=log_fn)

    # Không để kết quả thừa của lần chạy cũ còn lẫn trong output khi số ảnh
    # hợp lệ của lần mới ít hơn.
    for cleanup_dir in (output_dir, global_out_dir):
        if not cleanup_dir or not os.path.isdir(cleanup_dir):
            continue
        for old_path in glob.glob(os.path.join(cleanup_dir, f"{file_prefix}*.png")):
            try:
                os.remove(old_path)
            except OSError:
                pass

    saved_count = 0

    for idx, file_path in enumerate(files):
        fname = os.path.basename(file_path)
        log_fn(f"\n[{idx + 1}/{total_files}] Đang xử lý: {fname}")

        img = cv2_imread_utf8(file_path)
        if img is None:
            log_fn(f"  [X] Không thể mở ảnh: {fname}")
            continue

        crop = detector.detect_and_crop(img, log_fn=log_fn)
        if crop is None:
            log_fn(f"  [X] Bỏ qua (không thể cắt được ảnh): {fname}")
            continue

        saved_count += 1
        out_filename = f"{file_prefix}{saved_count:03d}.png"
        out_path = os.path.join(output_dir, out_filename)

        if cv2_imwrite_utf8(out_path, crop):
            # Đồng bộ sang thư mục output chung nếu có
            if global_out_dir and os.path.abspath(global_out_dir) != os.path.abspath(output_dir):
                cv2_imwrite_utf8(os.path.join(global_out_dir, out_filename), crop)

            log_fn(f"  [V] Đã cắt thành công: {out_filename} ({crop.shape[1]}x{crop.shape[0]} px)")
            if on_card_saved_fn:
                on_card_saved_fn(out_path, crop)
        else:
            log_fn(f"  [X] Không thể lưu file: {out_filename}")

        if progress_fn:
            progress_fn((idx + 1) / total_files * 100)

    log_fn("\n" + "=" * 60)
    log_fn(f"[HOÀN TẤT] Tổng kết:")
    log_fn(f" - Tổng số ảnh gốc đã quét: {total_files}")
    log_fn(f" - Tổng số ảnh trang phục đã cắt và lưu thành công: {saved_count} ảnh")
    log_fn(f" - Vị trí lưu ảnh: {output_dir}")
    if global_out_dir:
        log_fn(f" - Đồng bộ tới: {global_out_dir}")
    log_fn("=" * 60)

    return {
        "total_files": total_files,
        "total_saved": saved_count
    }


# ==============================================================================
# GIAO DIỆN ĐỒ HỌA TRỰC QUAN (MODERN TKINTER GUI)
# ==============================================================================
class OutfitCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Công Cụ Cắt Ảnh Trang Phục / Nhân Vật Toàn Thân Tự Động")
        self.root.geometry("980x740")
        self.root.minsize(850, 620)

        # Thiết lập màu sắc Dark Modern
        self.bg_color = "#181825"
        self.card_bg = "#1e1e2e"
        self.input_bg = "#313244"
        self.fg_color = "#cdd6f4"
        self.accent_color = "#cba6f7"
        self.btn_green = "#a6e3a1"
        self.btn_green_text = "#11111b"

        self.root.configure(bg=self.bg_color)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.acc_id_var = tk.StringVar(value="")
        self.input_dir_var = tk.StringVar(value="")
        self.out_dir_var = tk.StringVar(value="")
        self.target_w_var = tk.IntVar(value=774)
        self.target_h_var = tk.IntVar(value=1220)
        self.prefix_var = tk.StringVar(value="tp_")

        self.is_processing = False
        self.preview_images: List[ImageTk.PhotoImage] = []

        self._build_ui()
        self._init_accounts()

    def _get_account_list(self) -> List[str]:
        """Quét danh sách các mã account từ thư mục input cục bộ."""
        accounts = set()
        input_base = os.path.join(self.base_dir, "input")
        if os.path.exists(input_base):
            for d in os.listdir(input_base):
                if os.path.isdir(os.path.join(input_base, d)):
                    accounts.add(d)
        return sorted(list(accounts))

    def _init_accounts(self):
        accs = self._get_account_list()
        self.combo_acc['values'] = accs
        # Mặc định luôn trỏ thẳng vào thư mục input / output cục bộ của tool
        default_input = os.path.join(self.base_dir, "input")
        default_output = os.path.join(self.base_dir, "output")
        self.input_dir_var.set(default_input)
        self.out_dir_var.set(default_output)

    def _on_acc_changed(self, event=None):
        acc = self.acc_id_var.get().strip()
        if acc:
            acc_input = os.path.join(self.base_dir, "input", acc)
            acc_out = os.path.join(self.base_dir, "output", acc)
            self.input_dir_var.set(acc_input)
            self.out_dir_var.set(acc_out)
        else:
            self.input_dir_var.set(os.path.join(self.base_dir, "input"))
            self.out_dir_var.set(os.path.join(self.base_dir, "output"))

    def _build_ui(self):
        # 1. Header
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=10)
        header_frame.pack(fill=tk.X, padx=20)

        title = tk.Label(
            header_frame,
            text="✨ CẮT ẢNH TRANG PHỤC / NHÂN VẬT TOÀN THÂN TỰ ĐỘNG",
            font=("Segoe UI", 15, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title.pack(anchor="w")

        sub = tk.Label(
            header_frame,
            text="Tự động định vị và cắt nhân vật đứng tạo dáng toàn thân từ kho đồ (tp_001.png, tp_002.png,...)",
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg="#a6adc8"
        )
        sub.pack(anchor="w", pady=(2, 0))

        # 2. Main Content
        content = tk.Frame(self.root, bg=self.bg_color)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # Cột trái: Điều khiển & Cấu hình
        left_col = tk.Frame(content, bg=self.card_bg, padx=14, pady=14)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        # Chọn Mã Acc
        tk.Label(left_col, text="1. CHỌN MÃ ACCOUNT:", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 4))
        acc_frame = tk.Frame(left_col, bg=self.card_bg)
        acc_frame.pack(fill=tk.X, pady=(0, 12))

        self.combo_acc = ttk.Combobox(acc_frame, textvariable=self.acc_id_var, font=("Segoe UI", 10, "bold"), width=15)
        self.combo_acc.pack(side=tk.LEFT, padx=(0, 5))
        self.combo_acc.bind("<<ComboboxSelected>>", self._on_acc_changed)
        self.combo_acc.bind("<KeyRelease>", lambda e: self._on_acc_changed())

        btn_reload = tk.Button(acc_frame, text="🔄", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._init_accounts)
        btn_reload.pack(side=tk.LEFT)

        # Đường dẫn thư mục Input
        tk.Label(left_col, text="2. THƯ MỤC ẢNH ĐẦU VÀO (INPUT):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 4))
        in_frame = tk.Frame(left_col, bg=self.card_bg)
        in_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Entry(in_frame, textvariable=self.input_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(in_frame, text="📁", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._browse_input).pack(side=tk.LEFT)

        # Đường dẫn thư mục Output
        tk.Label(left_col, text="3. THƯ MỤC KẾT QUẢ (OUTPUT):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 4))
        out_frame = tk.Frame(left_col, bg=self.card_bg)
        out_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Entry(out_frame, textvariable=self.out_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(out_frame, text="📁", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._browse_output).pack(side=tk.LEFT)

        # Cấu hình Kích thước đầu ra & Tiền tố
        tk.Label(left_col, text="4. CẤU HÌNH KÍCH THƯỚC & TÊN:", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 4))
        size_frame = tk.Frame(left_col, bg=self.card_bg)
        size_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(size_frame, text="Rộng:", bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT)
        tk.Entry(size_frame, textvariable=self.target_w_var, width=5, bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT).pack(side=tk.LEFT, padx=(3, 8))

        tk.Label(size_frame, text="Cao:", bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT)
        tk.Entry(size_frame, textvariable=self.target_h_var, width=5, bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT).pack(side=tk.LEFT, padx=(3, 8))

        tk.Label(size_frame, text="Tên:", bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT)
        tk.Entry(size_frame, textvariable=self.prefix_var, width=6, bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT).pack(side=tk.LEFT, padx=(3, 0))

        # Nút Bắt đầu Cắt
        self.btn_run = tk.Button(
            left_col,
            text="🚀 BẮT ĐẦU CẮT TRANG PHỤC",
            font=("Segoe UI", 11, "bold"),
            bg=self.btn_green,
            fg=self.btn_green_text,
            activebackground="#94e2d5",
            relief=tk.FLAT,
            pady=10,
            command=self._start_process
        )
        self.btn_run.pack(fill=tk.X, pady=(0, 10))

        # Mở thư mục kết quả
        btn_open = tk.Button(
            left_col,
            text="📂 Mở Thư Mục Kết Quả",
            font=("Segoe UI", 9),
            bg=self.input_bg,
            fg=self.fg_color,
            relief=tk.FLAT,
            pady=5,
            command=self._open_output
        )
        btn_open.pack(fill=tk.X, pady=(0, 10))

        # Thanh tiến trình
        self.progress_bar = ttk.Progressbar(left_col, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(5, 5))

        self.lbl_status = tk.Label(left_col, text="Sẵn sàng xử lý", font=("Segoe UI", 9), bg=self.card_bg, fg="#a6adc8")
        self.lbl_status.pack(anchor="w")

        # Cột phải: Preview ảnh & Log
        right_col = tk.Frame(content, bg=self.bg_color)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Preview Panel
        preview_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        preview_panel.pack(fill=tk.X, pady=(0, 8))

        tk.Label(preview_panel, text="XEM TRƯỚC ẢNH VỪA CẮT MỚI NHẤT:", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

        self.preview_frame = tk.Frame(preview_panel, bg=self.card_bg)
        self.preview_frame.pack(fill=tk.X)

        self.preview_labels = []
        for i in range(4):
            lbl = tk.Label(self.preview_frame, bg="#11111b", width=16, height=5, relief=tk.RIDGE, bd=1)
            lbl.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.BOTH)
            self.preview_labels.append(lbl)

        # Log Panel
        log_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        log_panel.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_panel, text="NHẬT KÝ TIẾN TRÌNH (LOGS):", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

        self.log_text = tk.Text(
            log_panel,
            font=("Consolas", 9),
            bg="#11111b",
            fg="#a6adc8",
            insertbackground="white",
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_panel, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def _browse_input(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get(), parent=self.root)
        if d:
            self.input_dir_var.set(d)

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.out_dir_var.get(), parent=self.root)
        if d:
            self.out_dir_var.set(d)

    def _open_output(self):
        out_dir = self.out_dir_var.get().strip()
        if os.path.exists(out_dir):
            os.startfile(out_dir)
        else:
            messagebox.showwarning("Cảnh báo", "Thư mục kết quả chưa tồn tại!")

    def log(self, text: str):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _add_preview_image(self, path: str, img_bgr: np.ndarray):
        try:
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            thumb_h = 100
            thumb_w = int(w * (thumb_h / max(1, h)))
            if thumb_w > 160:
                thumb_w = 160
                thumb_h = int(h * (thumb_w / max(1, w)))

            img_resized = cv2.resize(img_rgb, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            pil_img = Image.fromarray(img_resized)
            tk_img = ImageTk.PhotoImage(pil_img)
            self.preview_images.append(tk_img)
            if len(self.preview_images) > 4:
                self.preview_images.pop(0)

            for idx, img_obj in enumerate(self.preview_images):
                if idx < len(self.preview_labels):
                    self.preview_labels[idx].configure(image=img_obj, width=thumb_w, height=thumb_h)
        except Exception:
            pass

    def _start_process(self):
        if self.is_processing:
            return

        in_dir = self.input_dir_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        acc = self.acc_id_var.get().strip()
        target_w = self.target_w_var.get()
        target_h = self.target_h_var.get()
        prefix = self.prefix_var.get().strip()

        if not os.path.exists(in_dir):
            messagebox.showerror("Lỗi", f"Thư mục đầu vào không tồn tại:\n{in_dir}")
            return

        self.is_processing = True
        self.btn_run.configure(state=tk.DISABLED, bg="#6c7086", text="⏳ ĐANG XỬ LÝ...")
        self.lbl_status.configure(text="Đang cắt ảnh trang phục...", fg=self.accent_color)
        self.progress_bar["value"] = 0
        self.log_text.delete(1.0, tk.END)

        def thread_fn():
            def log_cb(msg):
                self.root.after(0, lambda: self.log(msg))

            def prog_cb(val):
                self.root.after(0, lambda: self.progress_bar.configure(value=val))

            def prev_cb(path, img):
                self.root.after(0, lambda: self._add_preview_image(path, img))

            res = process_batch(
                input_dir=in_dir,
                output_dir=out_dir,
                target_size=(target_w, target_h),
                file_prefix=prefix,
                acc_id=acc,
                sync_global_output=True,
                log_fn=log_cb,
                progress_fn=prog_cb,
                on_card_saved_fn=prev_cb
            )

            def finish():
                self.is_processing = False
                self.btn_run.configure(state=tk.NORMAL, bg=self.btn_green, text="🚀 BẮT ĐẦU CẮT TRANG PHỤC")
                self.lbl_status.configure(text=f"Hoàn tất: Đã lưu {res['total_saved']} ảnh!", fg=self.btn_green)
                self.progress_bar["value"] = 100
                messagebox.showinfo(
                    "Thành công",
                    f"🎉 Đã cắt thành công {res['total_saved']}/{res['total_files']} ảnh trang phục!\n"
                    f"📁 Thư mục kết quả: {out_dir}"
                )

            self.root.after(0, finish)

        threading.Thread(target=thread_fn, daemon=True).start()


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Tool Cắt Ảnh Trang Phục / Nhân Vật Toàn Thân Tự Động")
    parser.add_argument("--cli", action="store_true", help="Chạy CLI không mở GUI")
    parser.add_argument("-i", "--input", help="Thư mục ảnh đầu vào")
    parser.add_argument("-o", "--output", help="Thư mục kết quả")
    parser.add_argument("-a", "--acc", help="Mã tài khoản (ví dụ: 654)")
    parser.add_argument("--width", type=int, default=774, help="Chiều rộng ảnh kết quả (px)")
    parser.add_argument("--height", type=int, default=1220, help="Chiều cao ảnh kết quả (px)")
    parser.add_argument("--prefix", default="tp_", help="Tiền tố tên file (mặc định: tp_)")

    args = parser.parse_args()

    if args.cli:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        in_dir = args.input or (os.path.join(base_dir, "input", args.acc) if args.acc else os.path.join(base_dir, "input"))
        out_dir = args.output or (os.path.join(base_dir, "output", args.acc) if args.acc else os.path.join(base_dir, "output"))

        print(f"[*] Khởi động Tool Cắt Trang Phục ở chế độ CLI...")
        process_batch(
            input_dir=in_dir,
            output_dir=out_dir,
            target_size=(args.width, args.height),
            file_prefix=args.prefix,
            acc_id=args.acc,
            sync_global_output=True,
            log_fn=print
        )
    else:
        root = tk.Tk()
        app = OutfitCropperGUI(root)
        if args.acc:
            app.acc_id_var.set(args.acc)
            app._on_acc_changed()
        root.mainloop()


if __name__ == "__main__":
    main()
