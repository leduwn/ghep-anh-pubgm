#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOOL CẮT ẢNH LỰU ĐẠN TỰ ĐỘNG - KHO ĐỒ PUBG MOBILE (CHỈ LỌC NỀN ĐỎ & TÍM)
========================================================================
Đặc điểm:
1. Nhận diện lưới 3 cột vật phẩm ném / lựu đạn trong kho đồ.
2. Tự động phân tích màu nền của từng ô: CHỈ CẮT CÁC Ô CÓ NỀN ĐỎ (Thần thoại) VÀ TÍM (Nâng cấp).
3. Bỏ qua các ô lựu đạn màu xanh lá, xanh dương, xám, trắng,...
4. Cắt bỏ viền ngoài (borderless) và chuẩn hóa kích thước đồng nhất 216x216 px.
5. Hỗ trợ lọc trùng lặp (Deduplication) khi vuốt cuộn màn hình.
6. Đặt tên chuẩn hóa: luudan_001.png, luudan_002.png,...
7. Tự động đồng bộ xuất kết quả ra thư mục output/<mã_acc>/
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


def cv2_imread_utf8(path: str) -> Optional[np.ndarray]:
    """Đọc ảnh an toàn với đường dẫn tiếng Việt."""
    try:
        if not os.path.exists(path):
            return None
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[Lỗi đọc ảnh] {path}: {e}")
        return None


def cv2_imwrite_utf8(path: str, img: np.ndarray, quality: int = 95) -> bool:
    """Ghi ảnh an toàn với đường dẫn tiếng Việt."""
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


class GrenadeCardDetector:
    """
    Nhận diện lưới 3 cột ô lựu đạn và lọc chỉ lấy nền ĐỎ & TÍM.
    """
    def __init__(self, target_size: Tuple[int, int] = (216, 216), border_margin: int = 5):
        self.target_width, self.target_height = target_size
        self.border_margin = border_margin

    @staticmethod
    def check_card_color(crop_img: np.ndarray) -> str:
        """
        Kiểm tra màu nền của ô:
        - ĐỎ (Mythic): Hue 0..15 & 160..180
        - TÍM (Upgrade): Hue 125..165
        """
        if crop_img is None or crop_img.size == 0:
            return "OTHER"

        h, w = crop_img.shape[:2]
        margin_w = int(w * 0.25)
        margin_h = int(h * 0.25)

        # Lấy mẫu nền từ 4 góc và 4 cạnh biên (tránh icon ở giữa)
        sample1 = crop_img[0:margin_h, 0:w]
        sample2 = crop_img[h-margin_h:h, 0:w]
        sample3 = crop_img[:, 0:margin_w]
        sample4 = crop_img[:, w-margin_w:w]

        samples = [sample1, sample2, sample3, sample4]
        total_pixels = sum(s.shape[0] * s.shape[1] for s in samples)
        if total_pixels == 0:
            return "OTHER"

        red_pixels = 0
        purple_pixels = 0

        for s in samples:
            hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
            # Mask Đỏ (Hue 0..15 và 160..180, S >= 45, V >= 40)
            red_mask1 = cv2.inRange(hsv, np.array([0, 45, 40]), np.array([15, 255, 255]))
            red_mask2 = cv2.inRange(hsv, np.array([160, 45, 40]), np.array([180, 255, 255]))
            red_pixels += np.sum((red_mask1 | red_mask2) > 0)

            # Mask Tím (Hue 125..165, S >= 35, V >= 35)
            purple_mask = cv2.inRange(hsv, np.array([125, 35, 35]), np.array([165, 255, 255]))
            purple_pixels += np.sum(purple_mask > 0)

        red_ratio = red_pixels / float(total_pixels)
        purple_ratio = purple_pixels / float(total_pixels)

        if red_ratio >= 0.12:
            return "RED"
        elif purple_ratio >= 0.12:
            return "PURPLE"

        return "OTHER"

    @staticmethod
    def find_grid_rows(img: np.ndarray) -> List[Tuple[int, int]]:
        """Dò các hàng lựu đạn đầy đủ theo lưới thật 250/267 px."""
        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        slot_h = max(80, int(round(250 * scale_y)))
        step_y = max(slot_h + 4, int(round(267 * scale_y)))
        min_full_y = int(round(280 * scale_y))
        bottom_limit = H - max(8, int(round(10 * scale_y)))
        search_radius = max(2, int(round(4 * scale_y)))

        strips = []
        for x1, x2 in [(1730, 1927), (1967, 2164), (2203, 2399)]:
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

        # Màn Lựu Đạn có thanh loại vật phẩm cố định phía trên, vì vậy hàng
        # đầu neo quanh y=299. Ưu tiên neo này để ảnh chỉ còn 1-4 thẻ không bị
        # các hàng trống làm thuật toán chu kỳ chọn nhầm xuống phía dưới.
        anchor_y1 = max(0, int(round(291 * scale_y)))
        anchor_y2 = min(len(row_diff), int(round(307 * scale_y)))
        if anchor_y2 > anchor_y1:
            anchor_band = row_diff[anchor_y1:anchor_y2]
            if anchor_band.size and float(np.max(anchor_band)) >= 25.0:
                first_top = anchor_y1 + int(np.argmax(anchor_band))
                anchored_rows: List[Tuple[int, int]] = []
                nominal_y = first_top
                while nominal_y + slot_h <= bottom_limit:
                    lo = max(0, nominal_y - search_radius)
                    hi = min(len(row_diff), nominal_y + search_radius + 1)
                    local_band = row_diff[lo:hi]
                    if local_band.size and float(np.max(local_band)) >= 12.0:
                        top_y = lo + int(np.argmax(local_band))
                    else:
                        top_y = nominal_y
                    anchored_rows.append((top_y, top_y + slot_h))
                    nominal_y += step_y
                if anchored_rows:
                    return anchored_rows

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
        """Cắt và lọc các ô lựu đạn có nền ĐỎ hoặc TÍM."""
        if img is None:
            return []

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        col_coords_base = [
            (1718, 1939),
            (1955, 2176),
            (2191, 2411),
        ]
        cols = [(int(c[0] * scale_x), int(c[1] * scale_x)) for c in col_coords_base]
        rows = GrenadeCardDetector.find_grid_rows(img)

        valid_cards = []
        for r_idx, (r_top, r_bot) in enumerate(rows):
            for c_idx, (c_left, c_right) in enumerate(cols):
                raw_crop = img[r_top:r_bot, c_left:c_right]
                if raw_crop.size == 0 or raw_crop.shape[0] < 50 or raw_crop.shape[1] < 50:
                    continue

                if np.std(raw_crop) < 18:
                    continue

                color_type = self.check_card_color(raw_crop)
                if color_type not in ["RED", "PURPLE"]:
                    continue

                ch, cw = raw_crop.shape[:2]
                margin_x = max(1, int(round(self.border_margin * scale_x)))
                margin_y = max(1, int(round(self.border_margin * scale_y)))
                inner = raw_crop[
                    margin_y:ch - margin_y,
                    margin_x:cw - margin_x,
                ]
                if inner.size == 0:
                    continue

                crop_normalized = cv2.resize(
                    inner,
                    (self.target_width, self.target_height),
                    interpolation=cv2.INTER_LANCZOS4
                )

                log_fn(f"  [+] Nhận diện ô LỰU ĐẠN ({'ĐỎ/Thần Thoại' if color_type == 'RED' else 'TÍM/Nâng Cấp'}) hàng {r_idx+1}, cột {c_idx+1}")

                valid_cards.append({
                    "bbox": (
                        c_left + margin_x,
                        r_top + margin_y,
                        cw - 2 * margin_x,
                        ch - 2 * margin_y,
                    ),
                    "crop": crop_normalized,
                    "color": color_type
                })

        return valid_cards


def process_batch(
    input_dir: str,
    output_dir: str,
    enable_dedup: bool = True,
    border_margin: int = 5,
    target_size: Tuple[int, int] = (216, 216),
    file_prefix: str = "luudan_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    on_card_saved_fn=None
) -> Dict:
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

    detector = GrenadeCardDetector(target_size=target_size, border_margin=border_margin)
    deduplicator = Deduplicator() if enable_dedup else None
    saved_count = 0

    for idx, fpath in enumerate(files):
        fname = os.path.basename(fpath)
        img = cv2_imread_utf8(fpath)
        if img is None:
            log_fn(f"  [-] Bỏ qua ảnh lỗi: {fname}")
            continue

        cards = detector.detect_cards(img, log_fn=log_fn)
        img_saved_count = 0

        for card in cards:
            crop_img = card["crop"]
            if deduplicator and deduplicator.is_duplicate(crop_img):
                continue

            saved_count += 1
            img_saved_count += 1
            out_name = f"{file_prefix}{saved_count:03d}.png"
            out_path = os.path.join(output_dir, out_name)
            cv2_imwrite_utf8(out_path, crop_img)

            if global_out_dir:
                global_path = os.path.join(global_out_dir, out_name)
                cv2_imwrite_utf8(global_path, crop_img)

            if on_card_saved_fn:
                on_card_saved_fn(out_path, crop_img)

        log_fn(f"  [+] ({idx + 1}/{total_files}) {fname} ➔ Đã lưu {img_saved_count} ô lựu đạn Đỏ/Tím.")

    log_fn(f"[✓] HOÀN TẤT: Đã cắt & lưu tổng cộng {saved_count} ảnh lựu đạn vào '{output_dir}'.")
    return {"total_saved": saved_count, "total_files": total_files}


class GrenadeCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TOOL CẮT ẢNH LỰU ĐẠN TỰ ĐỘNG (CHỈ NỀN ĐỎ & TÍM)")
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
            text="💣 TOOL CẮT ẢNH LỰU ĐẠN TỰ ĐỘNG (ĐỎ & TÍM)",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.accent
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Tự động nhận diện ô lựu đạn, lọc CHỈ LẤY NỀN ĐỎ VÀ TÍM, cắt chuẩn 216x216 px không viền",
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
            text="Lọc bỏ ô lựu đạn trùng lặp khi cuộn",
            variable=self.dedup_var,
            font=("Segoe UI", 9),
            bg=self.card_bg,
            fg=self.fg_color,
            selectcolor="#313244",
            activebackground=self.card_bg
        ).pack(anchor="w", pady=(0, 15))

        self.btn_run = tk.Button(
            left_col,
            text="🚀 BẮT ĐẦU CẮT LỰU ĐẠN",
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

        tk.Label(preview_panel, text="XEM TRƯỚC LỰU ĐẠN ĐỎ & TÍM VỪA CẮT", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent).pack(anchor="w", pady=(0, 4))

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
                self.btn_run.configure(state=tk.NORMAL, text="🚀 BẮT ĐẦU CẮT LỰU ĐẠN", bg=self.btn_green)
                messagebox.showinfo("Thành công", f"Đã cắt xong {res['total_saved']} ảnh lựu đạn Đỏ & Tím!")

            self.root.after(0, finish)

        threading.Thread(target=thread_fn, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Tool cắt ảnh Lựu Đạn tự động")
    parser.add_argument("--cli", action="store_true", help="Chạy chế độ CLI")
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
        app = GrenadeCropperGUI(root)
        if args.input != "input":
            app.input_dir_var.set(args.input)
        if args.output != "output":
            app.output_dir_var.set(args.output)
        root.mainloop()


if __name__ == "__main__":
    main()
