#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool tự động nhận diện và cắt ảnh Hành Động (Emotes / Actions)
- Tự động định vị lưới ô hành động trong kho đồ (3 cột)
- Cắt thành từng hành động 1 bằng nhau, chuẩn hóa kích thước 100% (216 x 216 px)
- Tự động CẮT BỎ VIỀN NGOÀI CÙNG (chỉ giữ ruột ảnh + nền)
- BỘ LỌC MÀU CHÍNH XÁC: CHỈ CẮT CÁC Ô HÀNH ĐỘNG CÓ NỀN MÀU ĐỎ (Thần thoại), bỏ qua màu vàng, tím, lam, lục,...
- Tự động loại bỏ ô bị khuyết khi cuộn và lọc trùng lặp khi chụp màn hình cuộn (Deduplication)
- Hỗ trợ chọn MÃ ACC, đặt tên chuẩn hd_001.png,... và đồng bộ ra output/<mã_acc>/
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
# BỘ NHẬN DIỆN VÀ LỌC MÀU HÀNH ĐỘNG ĐỎ (EMOTE DETECTOR)
# ==============================================================================
class EmoteCardDetector:
    """
    Module phân tích nhận diện từng ô hành động:
    - Định vị lưới 3 cột trong kho đồ
    - Kiểm tra màu nền: CHỈ GIỮ LẠI NỀN ĐỎ (Thần thoại)
    - Cắt bỏ viền ngoài cùng
    - Chuẩn hóa kích thước đầu ra (216 x 216 px)
    """

    def __init__(self, target_size: Tuple[int, int] = (216, 216), border_margin: int = 5):
        self.target_width, self.target_height = target_size
        self.border_margin = border_margin

    @staticmethod
    def is_red_card(crop_img: np.ndarray) -> bool:
        """
        Kiểm tra xem ô hành động có nền màu ĐỎ (Thần thoại) hay không.
        """
        if crop_img is None or crop_img.size == 0:
            return False

        h, w = crop_img.shape[:2]
        margin_w = int(w * 0.25)
        margin_h = int(h * 0.25)

        # Lấy mẫu nền 4 góc và dải biên (tránh icon người trắng ở giữa)
        sample1 = crop_img[0:margin_h, 0:w]
        sample2 = crop_img[h-margin_h:h, 0:w]
        sample3 = crop_img[:, 0:margin_w]
        sample4 = crop_img[:, w-margin_w:w]

        samples = [sample1, sample2, sample3, sample4]
        total_pixels = sum(s.shape[0] * s.shape[1] for s in samples)
        if total_pixels == 0:
            return False

        red_pixels = 0
        for s in samples:
            hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
            red_mask1 = cv2.inRange(hsv, np.array([0, 45, 40]), np.array([15, 255, 255]))
            red_mask2 = cv2.inRange(hsv, np.array([160, 45, 40]), np.array([180, 255, 255]))
            red_pixels += np.sum((red_mask1 | red_mask2) > 0)

        red_ratio = red_pixels / float(total_pixels)
        return red_ratio >= 0.12

    @staticmethod
    def find_grid_rows(img: np.ndarray) -> List[Tuple[int, int]]:
        """Tìm các hàng thẻ đầy đủ theo lưới thật 250 px, bước 267 px.

        Bố cục Hành Động có thẻ cao 250 px chứ không phải 216 px. Thuật toán
        cũ dùng bước 228 px nên từ hàng thứ hai trở đi bị trượt dần, cắt dính
        khoảng trống và mất phần dưới thẻ. Ở đây chỉ dò pha cuộn của lưới rồi
        tinh chỉnh từng mép trên bằng gradient ngang.
        """
        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        slot_h = max(80, int(round(250 * scale_y)))
        step_y = max(slot_h + 4, int(round(267 * scale_y)))
        min_full_y = int(round(280 * scale_y))
        bottom_limit = H - max(8, int(round(10 * scale_y)))

        # Chỉ lấy phần ruột ngang của cả ba cột để icon không làm lệch mép.
        inner_ranges = [
            (1730, 1927),
            (1967, 2164),
            (2203, 2399),
        ]
        strips = []
        for x1, x2 in inner_ranges:
            sx1 = max(0, int(round(x1 * scale_x)))
            sx2 = min(W, int(round(x2 * scale_x)))
            if sx2 > sx1:
                strips.append(img[:, sx1:sx2])
        if not strips:
            return []

        gray = cv2.cvtColor(np.concatenate(strips, axis=1), cv2.COLOR_BGR2GRAY)
        row_diff = np.mean(
            np.abs(np.diff(gray.astype(np.float32), axis=0)), axis=1
        )
        search_radius = max(2, int(round(4 * scale_y)))

        best_score = -1.0
        best_rows: List[int] = []
        for phase in range(step_y):
            candidate_rows = [
                y for y in range(phase, H, step_y)
                if y >= min_full_y and y + slot_h <= bottom_limit
            ]
            if len(candidate_rows) < 2:
                continue

            boundary_scores = []
            for top_y in candidate_rows:
                top_slice = row_diff[
                    max(0, top_y - search_radius):
                    min(len(row_diff), top_y + search_radius + 1)
                ]
                bottom_pos = top_y + slot_h - 1
                bottom_slice = row_diff[
                    max(0, bottom_pos - search_radius):
                    min(len(row_diff), bottom_pos + search_radius + 1)
                ]
                if top_slice.size and bottom_slice.size:
                    boundary_scores.append(float(np.max(top_slice) + np.max(bottom_slice)))

            if len(boundary_scores) < 2:
                continue
            score = float(np.median(boundary_scores) + 0.25 * np.mean(boundary_scores))
            if score > best_score:
                best_score = score
                best_rows = candidate_rows

        if best_score < 30.0 or not best_rows:
            return []

        rows: List[Tuple[int, int]] = []
        for nominal_y in best_rows:
            lo = max(0, nominal_y - search_radius)
            hi = min(len(row_diff), nominal_y + search_radius + 1)
            top_y = lo + int(np.argmax(row_diff[lo:hi]))
            if top_y + slot_h <= bottom_limit:
                rows.append((top_y, top_y + slot_h))
        return rows

    def detect_cards(self, img: np.ndarray, log_fn=print) -> List[Dict]:
        """
        Nhận diện tất cả các ô hành động có nền ĐỎ.
        """
        if img is None:
            return []

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        # Mép ngoài thực tế của ba thẻ trên ảnh chuẩn 2778x1284.
        col_coords_base = [
            (1718, 1939),
            (1955, 2176),
            (2191, 2411),
        ]
        cols = [(int(c[0] * scale_x), int(c[1] * scale_x)) for c in col_coords_base]
        rows = EmoteCardDetector.find_grid_rows(img)

        valid_cards = []
        for r_idx, (r_top, r_bot) in enumerate(rows):
            for c_idx, (c_left, c_right) in enumerate(cols):
                raw_crop = img[r_top:r_bot, c_left:c_right]
                if raw_crop.size == 0 or raw_crop.shape[0] < 50 or raw_crop.shape[1] < 50:
                    continue

                if np.std(raw_crop) < 18:
                    continue

                # CHỈ LẤY NỀN ĐỎ
                if not self.is_red_card(raw_crop):
                    log_fn(f"  [-] Bỏ qua ô hành động tại hàng {r_idx+1}, cột {c_idx+1} (Không phải nền Đỏ)")
                    continue

                # Cắt bỏ viền ngoài
                ch, cw = raw_crop.shape[:2]
                margin_x = max(1, int(round(self.border_margin * scale_x)))
                margin_y = max(1, int(round(self.border_margin * scale_y)))
                inner = raw_crop[
                    margin_y:ch - margin_y,
                    margin_x:cw - margin_x,
                ]
                if inner.size == 0:
                    continue

                # Chuẩn hóa kích thước
                crop_normalized = cv2.resize(
                    inner,
                    (self.target_width, self.target_height),
                    interpolation=cv2.INTER_LANCZOS4
                )

                log_fn(f"  [+] Nhận diện ô HÀNH ĐỘNG ĐỎ tại hàng {r_idx+1}, cột {c_idx+1}")

                valid_cards.append({
                    "bbox": (
                        c_left + margin_x,
                        r_top + margin_y,
                        cw - 2 * margin_x,
                        ch - 2 * margin_y,
                    ),
                    "crop": crop_normalized,
                    "orig_crop": inner,
                    "color": "RED",
                    "is_full": True
                })

        return valid_cards


# ==============================================================================
# BỘ LỌC TRÙNG LẶP HÀNH ĐỘNG
# ==============================================================================
class EmoteDeduplicator:
    def __init__(self, threshold: float = 4.0):
        self.threshold = threshold
        self.known_cards: List[np.ndarray] = []

    def reset(self):
        self.known_cards.clear()

    def is_duplicate(self, new_card: np.ndarray) -> Tuple[bool, float]:
        if not self.known_cards:
            self.known_cards.append(new_card)
            return False, 999.0

        h, w = new_card.shape[:2]
        center_new = new_card[10:h-10, 10:w-10].astype(np.float32)

        min_diff = 999.0
        for card in self.known_cards:
            center_saved = card[10:h-10, 10:w-10].astype(np.float32)
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
    border_margin: int = 5,
    target_size: Tuple[int, int] = (216, 216),
    file_prefix: str = "hd_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    progress_fn=None,
    on_card_saved_fn=None
) -> Dict:
    r"""
    Hàm xử lý cắt ảnh hành động hàng loạt từ input sang output.
    Chỉ lưu các ô hành động nền ĐỎ.
    Hỗ trợ đồng bộ sang output/<mã_acc>/
    """
    os.makedirs(output_dir, exist_ok=True)

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
    log_fn(f"[*] Kích thước chuẩn đầu ra: {target_size[0]}x{target_size[1]} px (Không viền)")
    log_fn(f"[*] Bộ lọc màu: CHỈ CẮT Ô HÀNH ĐỘNG NỀN ĐỎ")
    log_fn("-" * 60)

    detector = EmoteCardDetector(target_size=target_size, border_margin=border_margin)
    deduplicator = EmoteDeduplicator(threshold=4.0)

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
        log_fn(f"  [+] Nhận diện được {len(cards)} ô hành động ĐỎ hợp lệ")

        for card_idx, card_info in enumerate(cards):
            crop = card_info["crop"]

            if enable_dedup:
                is_dup, diff = deduplicator.is_duplicate(crop)
                if is_dup:
                    skipped_dup_count += 1
                    log_fn(f"  [~] Ô #{card_idx + 1} trùng với hành động đã lưu trước đó (Lệch {diff:.2f}) -> Bỏ qua")
                    continue

            saved_count += 1
            out_filename = f"{file_prefix}{saved_count:03d}.png"
            out_path = os.path.join(output_dir, out_filename)

            if cv2_imwrite_utf8(out_path, crop):
                if global_out_dir and os.path.abspath(global_out_dir) != os.path.abspath(output_dir):
                    cv2_imwrite_utf8(os.path.join(global_out_dir, out_filename), crop)

                log_fn(f"  [V] Đã lưu: {out_filename} ({crop.shape[1]}x{crop.shape[0]} px, Nền Đỏ)")
                if on_card_saved_fn:
                    on_card_saved_fn(out_path, crop)
            else:
                log_fn(f"  [X] Không thể lưu file: {out_filename}")

        if progress_fn:
            progress_fn((idx + 1) / total_files * 100)

    log_fn("\n" + "=" * 60)
    log_fn(f"[HOÀN TẤT] Tổng kết Hành Động:")
    log_fn(f" - Tổng ảnh gốc: {total_files}")
    log_fn(f" - Tổng ô hành động ĐỎ đã cắt & lưu: {saved_count} ảnh (không viền)")
    if enable_dedup:
        log_fn(f" - Số ô trùng lặp đã lọc bỏ: {skipped_dup_count} ô")
    log_fn(f" - Vị trí lưu: {output_dir}")
    log_fn("=" * 60)

    return {
        "total_files": total_files,
        "total_saved": saved_count,
        "total_skipped_dup": skipped_dup_count
    }


# ==============================================================================
# GIAO DIỆN ĐỒ HỌA TRỰC QUAN (TKINTER GUI)
# ==============================================================================
class EmoteCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Công Cụ Cắt Ảnh Hành Động Tự Động (Auto Emote Card Cropper - Chỉ Nền Đỏ)")
        self.root.geometry("980x750")
        self.root.minsize(850, 620)

        self.bg_color = "#181825"
        self.card_bg = "#1e1e2e"
        self.input_bg = "#313244"
        self.fg_color = "#cdd6f4"
        self.accent_color = "#fab387"
        self.btn_green = "#a6e3a1"
        self.btn_green_text = "#11111b"

        self.root.configure(bg=self.bg_color)
        self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.acc_id_var = tk.StringVar(value="")
        self.input_dir_var = tk.StringVar(value="")
        self.out_dir_var = tk.StringVar(value="")
        self.dedup_var = tk.BooleanVar(value=True)
        self.margin_var = tk.IntVar(value=5)
        self.target_w_var = tk.IntVar(value=216)
        self.target_h_var = tk.IntVar(value=216)
        self.prefix_var = tk.StringVar(value="hd_")

        self.is_processing = False
        self.preview_images: List[ImageTk.PhotoImage] = []

        self._build_ui()
        self._init_accounts()

    def _get_account_list(self) -> List[str]:
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
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=10)
        header_frame.pack(fill=tk.X, padx=20)

        title_lbl = tk.Label(
            header_frame,
            text="TOOL CẮT ẢNH HÀNH ĐỘNG TỰ ĐỘNG (CHỈ NỀN ĐỎ)",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title_lbl.pack(anchor="w")

        desc_lbl = tk.Label(
            header_frame,
            text="Tự động nhận diện ô hành động, lọc chỉ lấy ô nền ĐỎ (Thần thoại), cắt sạch viền ngoài, kích thước 216x216 px.",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg="#a6adc8"
        )
        desc_lbl.pack(anchor="w", pady=(2, 0))

        body = tk.Frame(self.root, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        left_col = tk.Frame(body, bg=self.card_bg, padx=15, pady=15)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        tk.Label(left_col, text="QUẢN LÝ MÃ TÀI KHOẢN (ACC)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))
        acc_frame = tk.Frame(left_col, bg=self.card_bg)
        acc_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(acc_frame, text="Chọn Mã Acc:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT)
        self.combo_acc = ttk.Combobox(acc_frame, textvariable=self.acc_id_var, width=15, font=("Segoe UI", 9))
        self.combo_acc.pack(side=tk.LEFT, padx=5)
        self.combo_acc.bind("<<ComboboxSelected>>", self._on_acc_changed)

        tk.Label(left_col, text="THƯ MỤC LÀM VIỆC", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(5, 5))
        tk.Label(left_col, text="Thư mục ảnh gốc (input):", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        input_box = tk.Frame(left_col, bg=self.card_bg)
        input_box.pack(fill=tk.X, pady=(2, 10))
        tk.Entry(input_box, textvariable=self.input_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(input_box, text="Chọn...", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._browse_input).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Label(left_col, text="Thư mục kết quả (output):", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        out_box = tk.Frame(left_col, bg=self.card_bg)
        out_box.pack(fill=tk.X, pady=(2, 15))
        tk.Entry(out_box, textvariable=self.out_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(out_box, text="Chọn...", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._browse_output).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Label(left_col, text="TÙY CHỌN XỬ LÝ", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))
        tk.Checkbutton(left_col, text="Lọc trùng lặp khi cuộn", variable=self.dedup_var, font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color, selectcolor=self.input_bg).pack(anchor="w", pady=(0, 8))

        self.btn_run = tk.Button(
            left_col,
            text="▶  BẮT ĐẦU CẮT HÀNH ĐỘNG",
            font=("Segoe UI", 11, "bold"),
            bg=self.btn_green,
            fg=self.btn_green_text,
            relief=tk.FLAT,
            pady=8,
            command=self._start_processing
        )
        self.btn_run.pack(fill=tk.X, pady=(10, 5))

        self.progress_bar = ttk.Progressbar(left_col, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(5, 5))

        self.lbl_status = tk.Label(left_col, text="Sẵn sàng", font=("Segoe UI", 9), bg=self.card_bg, fg="#a6adc8")
        self.lbl_status.pack(anchor="w")

        right_col = tk.Frame(body, bg=self.bg_color)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        preview_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        preview_panel.pack(fill=tk.X, pady=(0, 10))
        tk.Label(preview_panel, text="XEM TRƯỚC CÁC Ô HÀNH ĐỘNG ĐÃ CẮT (CHỈ NỀN ĐỎ)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

        self.preview_canvas_frame = tk.Frame(preview_panel, bg=self.card_bg)
        self.preview_canvas_frame.pack(fill=tk.X)
        self.preview_labels = []
        for i in range(4):
            lbl = tk.Label(self.preview_canvas_frame, bg="#11111b", width=14, height=5, relief=tk.RIDGE, bd=1)
            lbl.pack(side=tk.LEFT, padx=4, expand=True, fill=tk.BOTH)
            self.preview_labels.append(lbl)

        log_panel = tk.Frame(right_col, bg=self.card_bg, padx=10, pady=10)
        log_panel.pack(fill=tk.BOTH, expand=True)
        tk.Label(log_panel, text="NHẬT KÝ XỬ LÝ (LOGS)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

        self.log_text = tk.Text(log_panel, font=("Consolas", 9), bg="#11111b", fg="#a6adc8", relief=tk.FLAT, wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(log_panel, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, text: str):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _browse_input(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get(), title="Chọn thư mục ảnh gốc")
        if d: self.input_dir_var.set(os.path.abspath(d))

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.out_dir_var.get(), title="Chọn thư mục output")
        if d: self.out_dir_var.set(os.path.abspath(d))

    def _add_preview_image(self, img_bgr: np.ndarray):
        try:
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            thumb_w = 90
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

    def _start_processing(self):
        if self.is_processing: return
        input_dir = self.input_dir_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        acc_id = self.acc_id_var.get().strip() or None

        if not os.path.exists(input_dir):
            messagebox.showerror("Lỗi", f"Thư mục không tồn tại:\n{input_dir}")
            return

        self.is_processing = True
        self.btn_run.configure(state=tk.DISABLED, bg="#6c7086", text="⏳ Đang cắt ảnh...")
        self.progress_bar["value"] = 0
        self.lbl_status.configure(text="Đang xử lý...", fg=self.accent_color)
        self.log_text.delete(1.0, tk.END)

        def run_thread():
            res = process_batch(
                input_dir=input_dir,
                output_dir=out_dir,
                enable_dedup=self.dedup_var.get(),
                border_margin=self.margin_var.get(),
                target_size=(self.target_w_var.get(), self.target_h_var.get()),
                file_prefix=self.prefix_var.get(),
                acc_id=acc_id,
                sync_global_output=True,
                log_fn=lambda m: self.root.after(0, lambda: self.log(m)),
                progress_fn=lambda v: self.root.after(0, lambda: self.progress_bar.configure(value=v)),
                on_card_saved_fn=lambda p, im: self.root.after(0, lambda: self._add_preview_image(im))
            )

            def finish():
                self.is_processing = False
                self.btn_run.configure(state=tk.NORMAL, bg=self.btn_green, text="▶  BẮT ĐẦU CẮT HÀNH ĐỘNG")
                self.lbl_status.configure(text=f"Hoàn tất: {res['total_saved']} ô!", fg=self.btn_green)
                messagebox.showinfo("Thành công", f"Đã cắt và lưu thành công {res['total_saved']} ô hành động (Đỏ) vào:\n{out_dir}")

            self.root.after(0, finish)

        threading.Thread(target=run_thread, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Tool cắt ảnh hành động tự động (chỉ nền Đỏ)")
    parser.add_argument("--cli", action="store_true", help="Chạy chế độ CLI")
    parser.add_argument("-a", "--acc", default=None, help="Mã tài khoản")
    parser.add_argument("-i", "--input", default=None, help="Thư mục input")
    parser.add_argument("-o", "--output", default=None, help="Thư mục output")
    parser.add_argument("--keep-all", action="store_true", help="Không lọc trùng lặp")
    parser.add_argument("-p", "--prefix", default="hd_", help="Tiền tố tên file")

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
        process_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            enable_dedup=not args.keep_all,
            file_prefix=args.prefix,
            acc_id=acc_id,
            sync_global_output=True,
            log_fn=print
        )
    else:
        root = tk.Tk()
        app = EmoteCropperGUI(root)
        if args.acc:
            app.acc_id_var.set(args.acc)
            app._on_acc_changed()
        if args.input:
            app.input_dir_var.set(args.input)
        if args.output:
            app.out_dir_var.set(args.output)
        root.mainloop()


if __name__ == "__main__":
    main()
