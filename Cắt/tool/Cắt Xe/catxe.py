#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool tự động nhận diện và cắt ảnh Thẻ Xe (Vehicle Cards - Ô xe trong Gara / Kho xe)
- TỰ ĐỘNG ĐỊNH VỊ KHUNG Ô XE: Tự nhận diện vị trí ô xe dù bị cuộn lệch ở bất kỳ vị trí nào
- TỰ ĐỘNG CẮT BỎ HOÀN TOÀN VIỀN NGOÀI CÙNG (cắt lẹm thêm mép trên và mép trái 1px để sạch viền 100%)
- Tự động nhận diện mọi phẩm chất xe (Đỏ / Thần thoại, Tím / Nâng cấp, Vàng, Lam,...)
- Tự động cắt đầy đủ toàn bộ ô xe: gồm màu nền phẩm chất, tick chọn cam, logo hãng xe (Ferrari, Lamborghini, Koenigsegg,...) và số lượng
- Tự động bỏ qua các ô xe bị cắt lửng/khuyết ở mép cuộn trên và dưới
- Tự động lọc trùng lặp các ô xe khi chụp màn hình cuộn danh sách (Smart Deduplication)
- Chuẩn hóa kích thước đầu ra đồng nhất 100% (498 x 190 px)
- Hỗ trợ chọn MÃ ACC, đặt tên chuẩn xe_001.png,... và đồng bộ ra d:\Ghep-Anh\output\<mã_acc>\
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
# BỘ NHẬN DIỆN KHUNG Ô XE THÔNG MINH (VEHICLE CARD DETECTOR)
# ==============================================================================
class VehicleCardDetector:
    """
    Module tự động định vị và nhận diện ô xe:
    - Tìm cột danh sách xe (x ~ 1850-2385 ở màn hình 2778x1284)
    - Tự nhận diện tất cả các khung ô xe hoàn chỉnh (kể cả khi cuộn lệch lên/xuống)
    - CẮT BỎ VIỀN NGOÀI CÙNG: cắt lẹm mép trên và mép trái thêm 1px để không còn thấy bất kỳ vệt viền thừa nào
    - Tự động bỏ qua các ô xe bị cắt lửng ở mép trên hoặc mép dưới màn hình
    - Chuẩn hóa kích thước khung hình đầu ra đúng chuẩn (498 x 190 px)
    """

    def __init__(
        self,
        target_size: Tuple[int, int] = (498, 190),
        border_margin: int = 3,
        extra_left: int = 1,
        extra_top: int = 2,
        extra_bottom: int = 5,
        extra_right: int = 1
    ):
        self.target_width, self.target_height = target_size
        self.border_margin = border_margin
        self.extra_left = extra_left
        self.extra_top = extra_top
        self.extra_bottom = extra_bottom
        self.extra_right = extra_right

    def detect_cards(self, img: np.ndarray, log_fn=print) -> List[Dict]:
        """
        Nhận diện tất cả các ô xe hợp lệ trong ảnh và cắt bỏ viền ngoài.
        Trả về danh sách {bbox: (x, y, w, h), crop: np.ndarray, is_full: bool}
        """
        if img is None:
            return []

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        # Tọa độ chuẩn của cột xe
        std_w = int(round(498 * scale_x))
        std_h = int(round(190 * scale_y))
        col_x_min = int(round(1840 * scale_x))
        col_x_max = min(W, int(round(2400 * scale_x)))

        # Vùng cột chứa xe
        col_roi = img[:, col_x_min:col_x_max]
        if col_roi.size == 0:
            return []

        gray_col = cv2.cvtColor(col_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray_col, 30, 100)

        # Tìm contours trong cột xe
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            aspect = cw / max(1, ch)
            # Ô xe có chiều rộng ~ std_w (>= 0.85 * std_w) và tỉ lệ aspect ~ 2.2 đến 3.0
            if (cw >= 0.85 * std_w) and (ch >= 0.70 * std_h) and (2.1 <= aspect <= 3.1):
                global_x = col_x_min + cx
                candidates.append((global_x, cy, cw, ch))

        # Nếu không tìm thấy contour nào phù hợp, dùng vị trí ước tính
        if not candidates:
            log_fn("  [Cảnh báo] Không tìm thấy contour ô xe qua Canny, dùng tọa độ mặc định...")
            candidates = [(int(1868 * scale_x), int(217 * scale_y), std_w, std_h)]

        # Tìm tọa độ X trung vị của các ô xe
        med_x = int(np.median([c[0] for c in candidates]))
        med_w = int(np.median([c[2] for c in candidates]))
        if med_w < 0.85 * std_w:
            med_w = std_w

        # Lọc các box nằm trong cột xe
        matched = []
        for (x, y, w, h) in candidates:
            if abs(x - med_x) <= max(15, int(0.015 * W)) and (w >= 0.85 * std_w):
                matched.append((med_x, y, med_w, h))

        # Sắp xếp theo thứ tự Y từ trên xuống
        matched = sorted(matched, key=lambda b: b[1])

        # Khử các box trùng lặp vị trí Y
        dedup_boxes = []
        for b in matched:
            if not dedup_boxes or (b[1] - dedup_boxes[-1][1]) > (0.4 * std_h):
                dedup_boxes.append(b)

        valid_cards = []
        for (x, y, w, h) in dedup_boxes:
            # 1. Kiểm tra tính trọn vẹn: nếu h quá ngắn (< 88% std_h) -> ô bị cắt khuyết khi cuộn
            if h < 0.88 * std_h:
                log_fn(f"  [-] Bỏ qua ô xe bị cắt khuyết tại y={y}, chiều cao={h}px (chuẩn={std_h}px)")
                continue

            # 2. Kiểm tra nếu chạm mép trên hoặc mép dưới màn hình
            if y < 10 or (y + std_h) > (H - 10):
                log_fn(f"  [-] Bỏ qua ô xe chạm mép màn hình tại y={y} (vượt ngoài khung hiển thị)")
                continue

            # Tọa độ khung gốc trước khi bỏ viền
            box_x = max(0, min(x, W - std_w))
            box_y = max(0, min(y, H - std_h))
            box_w = std_w
            box_h = std_h

            # CẮT BỎ VIỀN NGOÀI CÙNG (cắt kỹ cả 4 cạnh, đặc biệt cạnh dưới viền dày hơn)
            m_left = max(0, int(round((self.border_margin + self.extra_left) * scale_x)))
            m_top = max(0, int(round((self.border_margin + self.extra_top) * scale_y)))
            m_right = max(0, int(round((self.border_margin + self.extra_right) * scale_x)))
            m_bottom = max(0, int(round((self.border_margin + self.extra_bottom) * scale_y)))

            inner_x = box_x + m_left
            inner_y = box_y + m_top
            inner_w = max(10, box_w - m_left - m_right)
            inner_h = max(10, box_h - m_top - m_bottom)

            # Cắt ảnh ruột (đã xóa sạch viền đỏ/sáng màu ở cả 4 cạnh, đặc biệt mép trên và mép trái)
            crop = img[inner_y:inner_y + inner_h, inner_x:inner_x + inner_w]
            if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
                continue

            # Chuẩn hóa kích thước đầu ra đúng target_size (498 x 190)
            if crop.shape[1] != self.target_width or crop.shape[0] != self.target_height:
                crop_normalized = cv2.resize(
                    crop,
                    (self.target_width, self.target_height),
                    interpolation=cv2.INTER_LANCZOS4
                )
            else:
                crop_normalized = crop.copy()

            log_fn(f"  [+] Nhận diện ô xe tại y={inner_y}, x={inner_x} (cắt sạch viền: trái={m_left}px, trên={m_top}px, phải={m_right}px, dưới={m_bottom}px -> {crop_normalized.shape[1]}x{crop_normalized.shape[0]} px)")

            valid_cards.append({
                "bbox": (inner_x, inner_y, inner_w, inner_h),
                "crop": crop_normalized,
                "orig_crop": crop,
                "is_full": True
            })

        return valid_cards


# ==============================================================================
# BỘ LỌC TRÙNG LẶP Ô XE KHI CUỘN (SMART VEHICLE DEDUPLICATOR)
# ==============================================================================
class VehicleDeduplicator:
    """
    So sánh độ tương đồng giữa các ô xe để loại bỏ ô xe bị trùng lặp
    khi chụp ảnh màn hình dạng cuộn (Scroll).
    """

    def __init__(self, threshold: float = 4.0):
        self.threshold = threshold
        self.known_cards: List[np.ndarray] = []

    def reset(self):
        self.known_cards.clear()

    def is_duplicate(self, new_card: np.ndarray) -> Tuple[bool, float]:
        """
        Kiểm tra xem new_card đã xuất hiện trong danh sách đã lưu hay chưa.
        Trả về (is_dup, min_diff).
        """
        if not self.known_cards:
            self.known_cards.append(new_card)
            return False, 999.0

        # Lấy vùng trung tâm chứa thân xe và logo
        h, w = new_card.shape[:2]
        center_new = new_card[6:h-6, 40:w-40].astype(np.float32)

        min_diff = 999.0
        for card in self.known_cards:
            center_saved = card[6:h-6, 40:w-40].astype(np.float32)
            diff = float(np.mean(np.abs(center_new - center_saved)))
            if diff < min_diff:
                min_diff = diff

        if min_diff < self.threshold:
            return True, min_diff

        self.known_cards.append(new_card)
        return False, min_diff


# ==============================================================================
# BỘ QUẢN LÝ XỬ LÝ HÀNG LOẠT (PROCESS MANAGER)
# ==============================================================================
def process_batch(
    input_dir: str,
    output_dir: str,
    enable_dedup: bool = True,
    border_margin: int = 3,
    extra_left: int = 1,
    extra_top: int = 1,
    extra_bottom: int = 5,
    extra_right: int = 1,
    target_size: Tuple[int, int] = (498, 190),
    file_prefix: str = "xe_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    progress_fn=None,
    on_card_saved_fn=None
) -> Dict:
    r"""
    Hàm xử lý cắt ảnh ô xe hàng loạt từ input sang output.
    Hỗ trợ tự nhận diện mọi ô xe, cắt bỏ sạch viền ngoài và đồng bộ sang d:\Ghep-Anh\output\<mã_acc>\
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
        return {"total_files": 0, "total_saved": 0, "total_skipped_dup": 0}

    log_fn(f"[*] Tìm thấy {total_files} ảnh cần xử lý trong '{input_dir}'")
    log_fn(f"[*] Thư mục lưu cục bộ: '{output_dir}'")
    if global_out_dir:
        log_fn(f"[*] Thư mục lưu đồng bộ tổng: '{global_out_dir}'")
    log_fn(f"[*] Cắt bỏ viền ngoài: cơ bản {border_margin}px + lẹm thêm (trái={extra_left}px, trên={extra_top}px, phải={extra_right}px, dưới={extra_bottom}px)")
    log_fn(f"[*] Kích thước chuẩn đầu ra: {target_size[0]}x{target_size[1]} px")
    log_fn(f"[*] Tiền tố tên file kết quả: '{file_prefix}'")
    log_fn(f"[*] Chế độ lọc trùng xe khi cuộn: {'BẬT (Deduplication ON)' if enable_dedup else 'TẮT'}")
    log_fn("-" * 60)

    detector = VehicleCardDetector(
        target_size=target_size,
        border_margin=border_margin,
        extra_left=extra_left,
        extra_top=extra_top,
        extra_bottom=extra_bottom,
        extra_right=extra_right
    )
    deduplicator = VehicleDeduplicator(threshold=4.0)
    saved_count = 0
    skipped_dup_count = 0

    for idx, file_path in enumerate(files):
        fname = os.path.basename(file_path)
        log_fn(f"\n[{idx + 1}/{total_files}] Đang xử lý: {fname}")

        img = cv2_imread_utf8(file_path)
        if img is None:
            log_fn(f"  [X] Không thể mở ảnh: {fname}")
            continue

        cards = detector.detect_cards(img, log_fn=log_fn)
        log_fn(f"  [+] Nhận diện được {len(cards)} ô xe hợp lệ (đã xóa sạch viền ngoài)")

        for card_idx, card_info in enumerate(cards):
            crop = card_info["crop"]

            # Kiểm tra lọc trùng lặp nếu bật
            if enable_dedup:
                is_dup, diff = deduplicator.is_duplicate(crop)
                if is_dup:
                    skipped_dup_count += 1
                    log_fn(f"  [~] Ô xe #{card_idx + 1} trùng với xe đã lưu trước đó (Độ lệch {diff:.2f}) -> Bỏ qua")
                    continue

            # Lưu ảnh ô xe
            saved_count += 1
            out_filename = f"{file_prefix}{saved_count:03d}.png"
            out_path = os.path.join(output_dir, out_filename)

            if cv2_imwrite_utf8(out_path, crop):
                # Đồng bộ sang thư mục output chung nếu có
                if global_out_dir and os.path.abspath(global_out_dir) != os.path.abspath(output_dir):
                    cv2_imwrite_utf8(os.path.join(global_out_dir, out_filename), crop)

                log_fn(f"  [V] Đã cắt thành công: {out_filename} ({crop.shape[1]}x{crop.shape[0]} px, không viền)")
                if on_card_saved_fn:
                    on_card_saved_fn(out_path, crop)
            else:
                log_fn(f"  [X] Không thể lưu file: {out_filename}")

        if progress_fn:
            progress_fn((idx + 1) / total_files * 100)

    log_fn("\n" + "=" * 60)
    log_fn(f"[HOÀN TẤT] Tổng kết:")
    log_fn(f" - Tổng số ảnh gốc đã quét: {total_files}")
    log_fn(f" - Tổng số ảnh ô xe đã cắt và lưu thành công: {saved_count} ảnh (đã xóa sạch viền ngoài)")
    if enable_dedup:
        log_fn(f" - Số ô xe trùng lặp khi cuộn đã lọc bỏ: {skipped_dup_count} ô")
    log_fn(f" - Vị trí lưu ảnh: {output_dir}")
    if global_out_dir:
        log_fn(f" - Đồng bộ tới: {global_out_dir}")
    log_fn("=" * 60)

    return {
        "total_files": total_files,
        "total_saved": saved_count,
        "total_skipped_dup": skipped_dup_count
    }


# ==============================================================================
# GIAO DIỆN ĐỒ HỌA TRỰC QUAN (MODERN TKINTER GUI)
# ==============================================================================
class VehicleCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Công Cụ Tự Động Nhận Diện & Cắt Ô Xe (Bỏ Viền Ngoài Cùng)")
        self.root.geometry("980x750")
        self.root.minsize(850, 620)

        # Thiết lập màu sắc Dark Modern
        self.bg_color = "#181825"
        self.card_bg = "#1e1e2e"
        self.input_bg = "#313244"
        self.fg_color = "#cdd6f4"
        self.accent_color = "#f9e2af"
        self.btn_green = "#a6e3a1"
        self.btn_green_text = "#11111b"

        self.root.configure(bg=self.bg_color)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.acc_id_var = tk.StringVar(value="")
        self.input_dir_var = tk.StringVar(value="")
        self.out_dir_var = tk.StringVar(value="")
        self.dedup_var = tk.BooleanVar(value=True)
        self.margin_var = tk.IntVar(value=3)
        self.extra_left_var = tk.IntVar(value=1)
        self.extra_top_var = tk.IntVar(value=1)
        self.target_w_var = tk.IntVar(value=498)
        self.target_h_var = tk.IntVar(value=190)
        self.prefix_var = tk.StringVar(value="xe_")

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

        title_lbl = tk.Label(
            header_frame,
            text="TOOL CẮT ẢNH Ô XE TỰ ĐỘNG (XÓA VIỀN NGOÀI CÙNG)",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title_lbl.pack(anchor="w")

        desc_lbl = tk.Label(
            header_frame,
            text="Tự động định vị ô xe (Ferrari, Sedan, UAZ,...), xóa sạch viền ngoài (lẹm trên/trái 1px), lọc trùng & cắt chuẩn 498x190 px.",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg="#a6adc8"
        )
        desc_lbl.pack(anchor="w", pady=(2, 0))

        # 2. Body container
        body = tk.Frame(self.root, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # Cột trái: Cài đặt và điều khiển
        left_col = tk.Frame(body, bg=self.card_bg, padx=15, pady=15, relief=tk.FLAT)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        # Nhóm Mã Acc
        tk.Label(left_col, text="QUẢN LÝ MÃ TÀI KHOẢN (ACC)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))
        
        acc_frame = tk.Frame(left_col, bg=self.card_bg)
        acc_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(acc_frame, text="Chọn Mã Acc:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT)
        self.combo_acc = ttk.Combobox(acc_frame, textvariable=self.acc_id_var, width=15, font=("Segoe UI", 9))
        self.combo_acc.pack(side=tk.LEFT, padx=5)
        self.combo_acc.bind("<<ComboboxSelected>>", self._on_acc_changed)
        self.combo_acc.bind("<KeyRelease>", lambda e: self._on_acc_changed())
        
        btn_refresh_acc = tk.Button(acc_frame, text="🔄", font=("Segoe UI", 8), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._refresh_accounts)
        btn_refresh_acc.pack(side=tk.LEFT)

        # Nhóm thư mục
        tk.Label(left_col, text="THƯ MỤC LÀM VIỆC", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(5, 5))

        tk.Label(left_col, text="Thư mục ảnh gốc (input):", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        input_box = tk.Frame(left_col, bg=self.card_bg)
        input_box.pack(fill=tk.X, pady=(2, 10))
        tk.Entry(input_box, textvariable=self.input_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white", width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(input_box, text="Chọn...", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._browse_input).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Label(left_col, text="Thư mục kết quả (output):", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        out_box = tk.Frame(left_col, bg=self.card_bg)
        out_box.pack(fill=tk.X, pady=(2, 15))
        tk.Entry(out_box, textvariable=self.out_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white", width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(out_box, text="Chọn...", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._browse_output).pack(side=tk.RIGHT, padx=(5, 0))

        # Nhóm tùy chọn
        tk.Label(left_col, text="TÙY CHỌN XỬ LÝ", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

        dedup_chk = tk.Checkbutton(
            left_col,
            text="Lọc bỏ ô xe trùng lặp khi cuộn",
            variable=self.dedup_var,
            font=("Segoe UI", 9),
            bg=self.card_bg,
            fg=self.fg_color,
            selectcolor=self.input_bg,
            activebackground=self.card_bg,
            activeforeground=self.fg_color
        )
        dedup_chk.pack(anchor="w", pady=(0, 8))

        margin_frame = tk.Frame(left_col, bg=self.card_bg)
        margin_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(margin_frame, text="Cắt viền ngoài (cơ bản):", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT)
        tk.Entry(margin_frame, textvariable=self.margin_var, width=4, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(side=tk.LEFT, padx=4)
        tk.Label(margin_frame, text="+Lẹm trên/trái:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT, padx=(5, 2))
        tk.Entry(margin_frame, textvariable=self.extra_left_var, width=3, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(side=tk.LEFT)
        tk.Label(margin_frame, text="px", font=("Segoe UI", 8), bg=self.card_bg, fg="#a6adc8").pack(side=tk.LEFT, padx=2)

        size_frame = tk.Frame(left_col, bg=self.card_bg)
        size_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(size_frame, text="Kích thước đầu ra:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        
        size_inputs = tk.Frame(size_frame, bg=self.card_bg)
        size_inputs.pack(fill=tk.X, pady=(2, 0))
        tk.Entry(size_inputs, textvariable=self.target_w_var, width=6, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(side=tk.LEFT)
        tk.Label(size_inputs, text="x", bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT, padx=5)
        tk.Entry(size_inputs, textvariable=self.target_h_var, width=6, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(side=tk.LEFT)
        tk.Label(size_inputs, text="px (Chuẩn: 498x190)", font=("Segoe UI", 8), bg=self.card_bg, fg="#a6adc8").pack(side=tk.LEFT, padx=5)

        prefix_frame = tk.Frame(left_col, bg=self.card_bg)
        prefix_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(prefix_frame, text="Tiền tố tên file:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        tk.Entry(prefix_frame, textvariable=self.prefix_var, width=15, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(anchor="w", pady=(2, 0))

        # Nút điều khiển chính
        self.btn_run = tk.Button(
            left_col,
            text="▶  BẮT ĐẦU CẮT ẢNH XE",
            font=("Segoe UI", 11, "bold"),
            bg=self.btn_green,
            fg=self.btn_green_text,
            activebackground="#94e2d5",
            relief=tk.FLAT,
            pady=8,
            command=self._start_processing
        )
        self.btn_run.pack(fill=tk.X, pady=(10, 5))

        self.btn_open_out = tk.Button(
            left_col,
            text="📂  Mở Thư Mục Kết Quả",
            font=("Segoe UI", 9),
            bg=self.input_bg,
            fg=self.fg_color,
            relief=tk.FLAT,
            pady=6,
            command=self._open_output_folder
        )
        self.btn_open_out.pack(fill=tk.X, pady=(0, 10))

        # Tiến trình
        self.progress_bar = ttk.Progressbar(left_col, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(5, 5))

        self.lbl_status = tk.Label(left_col, text="Sẵn sàng thực hiện", font=("Segoe UI", 9), bg=self.card_bg, fg="#a6adc8")
        self.lbl_status.pack(anchor="w")

        # Cột phải: Gallery xem trước và Nhật ký xử lý (Log)
        right_col = tk.Frame(body, bg=self.bg_color)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Phần Gallery ảnh vừa cắt
        preview_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        preview_panel.pack(fill=tk.X, pady=(0, 10))

        tk.Label(preview_panel, text="XEM TRƯỚC Ô XE VỪA CẮT (ĐÃ XÓA VIỀN NGOÀI)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))
        
        self.preview_canvas_frame = tk.Frame(preview_panel, bg=self.card_bg)
        self.preview_canvas_frame.pack(fill=tk.X)

        self.preview_labels = []
        for i in range(4):
            lbl = tk.Label(self.preview_canvas_frame, bg="#11111b", width=18, height=5, relief=tk.RIDGE, bd=1)
            lbl.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.BOTH)
            self.preview_labels.append(lbl)

        # Phần Nhật ký xử lý (Log Console)
        log_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        log_panel.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_panel, text="NHẬT KÝ XỬ LÝ (LOGS)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

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

    def log(self, text: str):
        """Thêm log vào cửa sổ giao diện."""
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _refresh_accounts(self):
        accs = self._get_account_list()
        self.combo_acc['values'] = accs
        if accs:
            if self.acc_id_var.get() not in accs:
                self.combo_acc.current(0)
            self._on_acc_changed()
        messagebox.showinfo("Thông báo", f"Đã quét được {len(accs)} mã account!")

    def _browse_input(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get(), title="Chọn thư mục ảnh gốc (input)")
        if d:
            self.input_dir_var.set(os.path.abspath(d))

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.out_dir_var.get(), title="Chọn thư mục lưu kết quả (output)")
        if d:
            self.out_dir_var.set(os.path.abspath(d))

    def _open_output_folder(self):
        out_dir = self.out_dir_var.get()
        if os.path.exists(out_dir):
            os.startfile(out_dir)
        else:
            messagebox.showwarning("Thông báo", f"Thư mục kết quả chưa tồn tại:\n{out_dir}")

    def _add_preview_image(self, img_bgr: np.ndarray):
        """Hiển thị thumbnail ảnh ô xe vừa cắt vào giao diện."""
        try:
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            thumb_w = 150
            thumb_h = int(h * (thumb_w / w))
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

    def _start_processing(self):
        if self.is_processing:
            return

        input_dir = self.input_dir_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        acc_id = self.acc_id_var.get().strip() or None

        if not os.path.exists(input_dir):
            messagebox.showerror("Lỗi", f"Thư mục ảnh gốc không tồn tại:\n{input_dir}")
            return

        self.is_processing = True
        self.btn_run.configure(state=tk.DISABLED, bg="#6c7086", text="⏳ Đang xử lý cắt ảnh...")
        self.progress_bar["value"] = 0
        self.lbl_status.configure(text="Đang xử lý...", fg=self.accent_color)
        self.log_text.delete(1.0, tk.END)

        target_size = (self.target_w_var.get(), self.target_h_var.get())
        border_margin = self.margin_var.get()
        extra_left = self.extra_left_var.get()
        extra_top = self.extra_top_var.get()
        enable_dedup = self.dedup_var.get()
        prefix = self.prefix_var.get()

        def run_thread():
            def log_callback(msg):
                self.root.after(0, lambda: self.log(msg))

            def progress_callback(val):
                self.root.after(0, lambda: self.progress_bar.configure(value=val))

            def card_saved_callback(path, img_bgr):
                self.root.after(0, lambda: self._add_preview_image(img_bgr))

            res = process_batch(
                input_dir=input_dir,
                output_dir=out_dir,
                enable_dedup=enable_dedup,
                border_margin=border_margin,
                extra_left=extra_left,
                extra_top=extra_top,
                target_size=target_size,
                file_prefix=prefix,
                acc_id=acc_id,
                sync_global_output=True,
                log_fn=log_callback,
                progress_fn=progress_callback,
                on_card_saved_fn=card_saved_callback
            )

            def finish():
                self.is_processing = False
                self.btn_run.configure(state=tk.NORMAL, bg=self.btn_green, text="▶  BẮT ĐẦU CẮT ẢNH XE")
                self.progress_bar["value"] = 100
                self.lbl_status.configure(
                    text=f"Hoàn tất: Đã lưu {res['total_saved']} ảnh ô xe!", 
                    fg=self.btn_green
                )
                messagebox.showinfo("Thành công", f"Đã cắt và lưu thành công {res['total_saved']} ảnh ô xe (đã xóa viền ngoài) vào:\n{out_dir}")

            self.root.after(0, finish)

        threading.Thread(target=run_thread, daemon=True).start()


# ==============================================================================
# ĐIỂM BẮT ĐẦU CHƯƠNG TRÌNH (ENTRY POINT)
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Tool cắt ảnh ô xe tự động từ ảnh input")
    parser.add_argument("--cli", action="store_true", help="Chạy trực tiếp ở chế độ dòng lệnh (không mở GUI)")
    parser.add_argument("-a", "--acc", default=None, help="Mã tài khoản (ví dụ: 654)")
    parser.add_argument("-i", "--input", default=None, help="Thư mục chứa ảnh gốc (mặc định: ./input/<acc> hoặc ./input)")
    parser.add_argument("-o", "--output", default=None, help="Thư mục lưu kết quả (mặc định: ./output/<acc> hoặc ./output)")
    parser.add_argument("-m", "--margin", type=int, default=3, help="Độ dày viền ngoài cần cắt bỏ (px, mặc định: 3)")
    parser.add_argument("--extra-left", type=int, default=1, help="Lẹm thêm viền trái (px, mặc định: 1)")
    parser.add_argument("--extra-top", type=int, default=1, help="Lẹm thêm viền trên (px, mặc định: 1)")
    parser.add_argument("--keep-all", action="store_true", help="Không lọc trùng lặp khi cuộn danh sách xe")
    parser.add_argument("-W", "--width", type=int, default=498, help="Chiều rộng chuẩn đầu ra (mặc định: 498)")
    parser.add_argument("-H", "--height", type=int, default=190, help="Chiều cao chuẩn đầu ra (mặc định: 190)")
    parser.add_argument("-p", "--prefix", default="xe_", help="Tiền tố tên file kết quả (mặc định: xe_)")

    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    acc_id = args.acc
    if acc_id:
        default_input = os.path.join(base_dir, "input", acc_id)
        default_output = os.path.join(base_dir, "output", acc_id)
    else:
        default_input = os.path.join(base_dir, "input")
        default_output = os.path.join(base_dir, "output")

    input_dir = args.input if args.input else default_input
    output_dir = args.output if args.output else default_output

    if args.cli:
        print("[*] Khởi động Tool Cắt Xe ở chế độ CLI...")
        process_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            enable_dedup=not args.keep_all,
            border_margin=args.margin,
            extra_left=args.extra_left,
            extra_top=args.extra_top,
            target_size=(args.width, args.height),
            file_prefix=args.prefix,
            acc_id=acc_id,
            sync_global_output=True,
            log_fn=print
        )
    else:
        root = tk.Tk()
        app = VehicleCropperGUI(root)
        if args.acc:
            app.acc_id_var.set(args.acc)
            app._on_acc_changed()
        if args.input:
            app.input_dir_var.set(args.input)
        if args.output:
            app.out_dir_var.set(args.output)
        if args.margin != 3:
            app.margin_var.set(args.margin)
        if args.extra_left != 1:
            app.extra_left_var.set(args.extra_left)
        if args.extra_top != 1:
            app.extra_top_var.set(args.extra_top)
        if args.keep_all:
            app.dedup_var.set(False)
        root.mainloop()


if __name__ == "__main__":
    main()
