#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool tự động nhận diện và cắt danh sách 3 ô Mũ (Helmet Selection / Cấp 1, 2, 3)
- Tự động định vị cột và 3 ô Mũ hoàn chỉnh từ ảnh chụp màn hình input
- Tự động nhận diện chính xác mép bắt đầu của ô mũ đầu tiên (loại bỏ phần nền xám thừa bên trên khi cuộn lệch)
- Cắt sát viền trong chuẩn hóa kích thước 100% (683 x 773 px)
- Hỗ trợ chọn MÃ ACC, đặt tên chuẩn mu_001.png,... và đồng bộ ra output/<mã_acc>/
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
# BỘ NHẬN DIỆN VÀ CẮT 3 Ô MŨ (HELMET SELECTION DETECTOR)
# ==============================================================================
class HelmetSelectionDetector:
    """
    Module tự động định vị và cắt 3 ô Mũ (Helmet Selection 3-Slot Grid):
    - Tọa độ cột chuẩn ở màn hình 2778x1284: x=1723, w=683, h=773
    - Tự động nhận diện chính xác mép bắt đầu của ô mũ đầu tiên bằng cách phân tích:
      1. Cạnh ngang (Sobel Gradient)
      2. Sự chuyển tiếp màu từ nền xám container sang viền sáng màu của ô mũ
    - Cắt sát viền trong chuẩn hóa kích thước 100% (683 x 773 px)
    """

    def __init__(self, target_size: Tuple[int, int] = (683, 773)):
        self.target_width, self.target_height = target_size

    def detect_and_crop(self, img: np.ndarray, log_fn=print) -> Optional[np.ndarray]:
        if img is None:
            return None

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        inner_x1 = int(round(1723 * scale_x))
        inner_w = int(round(683 * scale_x))
        target_h = int(round(773 * scale_y))

        col_x_start = max(0, int(round(1715 * scale_x)))
        col_x_end = min(W, int(round(2415 * scale_x)))
        col_strip = img[:, col_x_start:col_x_end]

        gray = cv2.cvtColor(col_strip, cv2.COLOR_BGR2GRAY)
        sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3))
        row_edges = np.mean(sobel_y[:, int(40*scale_x):-int(40*scale_x)], axis=1)

        # Mũ phải lấy 3 hàng TRÊN: mép hàng đầu nằm khoảng y=208 trên ảnh
        # chuẩn 2778x1284. Không quét từ y=275 vì sẽ bắt mép hàng thứ hai.
        start_search_y = int(round(180 * scale_y))
        max_search_y = min(H - target_h, int(round(300 * scale_y)))

        candidates = []
        for y in range(start_search_y, max_search_y + 1):
            if row_edges[y] >= 100:
                w_win = 3
                if row_edges[y] == np.max(row_edges[max(0, y - w_win):min(len(row_edges), y + w_win + 1)]):
                    mean_after = np.mean(gray[y+3:y+12, int(40*scale_x):-int(40*scale_x)])
                    if mean_after < 130:
                        candidates.append(y)

        if candidates:
            best_y_outer = candidates[0]
        else:
            sub = row_edges[int(190*scale_y):int(235*scale_y)]
            if len(sub) > 0 and np.max(sub) > 50:
                best_y_outer = int(190*scale_y) + int(np.argmax(sub))
            else:
                best_y_outer = int(round(208 * scale_y))

        y_inner = best_y_outer + int(round(4 * scale_y))

        if y_inner + target_h > H:
            y_inner = H - target_h
        y_inner = max(0, y_inner)

        log_fn(f"  [+] Định vị 3 hàng Mũ trên cùng: x={inner_x1}, y={y_inner} (outer_y={best_y_outer}), w={inner_w}, h={target_h}")

        crop = img[y_inner:y_inner + target_h, inner_x1:inner_x1 + inner_w]

        if crop.size == 0:
            log_fn("  [X] Vùng cắt không hợp lệ!")
            return None

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
    target_size: Tuple[int, int] = (683, 773),
    file_prefix: str = "mu_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    progress_fn=None,
    on_card_saved_fn=None
) -> Dict:
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
        return {"total_files": 0, "total_saved": 0}

    log_fn(f"[*] Tìm thấy {total_files} ảnh cần xử lý trong '{input_dir}'")
    log_fn(f"[*] Thư mục lưu cục bộ: '{output_dir}'")
    if global_out_dir:
        log_fn(f"[*] Thư mục lưu đồng bộ tổng: '{global_out_dir}'")
    log_fn(f"[*] Kích thước chuẩn đầu ra: {target_size[0]}x{target_size[1]} px")
    log_fn(f"[*] Tiền tố tên file kết quả: '{file_prefix}'")
    log_fn("-" * 60)

    detector = HelmetSelectionDetector(target_size=target_size)
    saved_count = 0

    for idx, file_path in enumerate(files):
        fname = os.path.basename(file_path)
        saved_count += 1
        out_fname = f"{file_prefix}{saved_count:03d}.png"

        log_fn(f"\n[{idx + 1}/{total_files}] Đang xử lý: {fname}")

        img = cv2_imread_utf8(file_path)
        if img is None:
            log_fn(f"  [X] Không thể mở ảnh: {fname}")
            continue

        crop = detector.detect_and_crop(img, log_fn=log_fn)
        if crop is None:
            log_fn(f"  [X] Không thể cắt ảnh: {fname}")
            continue

        out_path = os.path.join(output_dir, out_fname)
        if cv2_imwrite_utf8(out_path, crop):
            if global_out_dir and os.path.abspath(global_out_dir) != os.path.abspath(output_dir):
                cv2_imwrite_utf8(os.path.join(global_out_dir, out_fname), crop)

            log_fn(f"  [V] Đã cắt thành công: {out_fname} ({crop.shape[1]}x{crop.shape[0]} px, cắt sát chuẩn)")
            if on_card_saved_fn:
                on_card_saved_fn(out_path, crop)
        else:
            log_fn(f"  [X] Không thể lưu file: {out_fname}")

        if progress_fn:
            progress_fn((idx + 1) / total_files * 100)

    log_fn("\n" + "=" * 60)
    log_fn(f"[HOÀN TẤT] Tổng kết:")
    log_fn(f" - Tổng số ảnh gốc đã quét: {total_files}")
    log_fn(f" - Tổng số ảnh Mũ đã cắt và lưu thành công: {saved_count} ảnh")
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
class HelmetCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Công Cụ Cắt Mũ Tự Động (Auto Helmet Cropper)")
        self.root.geometry("980x740")
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
        self.target_w_var = tk.IntVar(value=683)
        self.target_h_var = tk.IntVar(value=773)
        self.prefix_var = tk.StringVar(value="mu_")

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
            self.input_dir_var.set(os.path.join(self.base_dir, "input", acc))
            self.out_dir_var.set(os.path.join(self.base_dir, "output", acc))
        else:
            self.input_dir_var.set(os.path.join(self.base_dir, "input"))
            self.out_dir_var.set(os.path.join(self.base_dir, "output"))

    def _build_ui(self):
        header = tk.Frame(self.root, bg=self.bg_color, pady=10)
        header.pack(fill=tk.X, padx=20)

        title = tk.Label(
            header,
            text="🪖 CÔNG CỤ CẮT MŨ TỰ ĐỘNG (AUTO HELMET CROPPER)",
            font=("Segoe UI", 15, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title.pack(anchor="w")

        body = tk.Frame(self.root, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        left_pane = tk.Frame(body, bg=self.card_bg, padx=15, pady=15)
        left_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        tk.Label(left_pane, text="1. Chọn Mã Tài Khoản (Mã Acc):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.fg_color).pack(anchor="w", pady=(0, 4))

        acc_box = tk.Frame(left_pane, bg=self.card_bg)
        acc_box.pack(fill=tk.X, pady=(0, 12))

        self.combo_acc = ttk.Combobox(acc_box, textvariable=self.acc_id_var, font=("Segoe UI", 10), width=18)
        self.combo_acc.pack(side=tk.LEFT, padx=(0, 5))
        self.combo_acc.bind("<<ComboboxSelected>>", self._on_acc_changed)
        self.combo_acc.bind("<KeyRelease>", lambda e: self._on_acc_changed())

        btn_refresh_acc = tk.Button(acc_box, text="🔄", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=self._init_accounts)
        btn_refresh_acc.pack(side=tk.LEFT)

        tk.Label(left_pane, text="2. Thư Mục Ảnh Đầu Vào (Input):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.fg_color).pack(anchor="w", pady=(0, 4))
        in_box = tk.Frame(left_pane, bg=self.card_bg)
        in_box.pack(fill=tk.X, pady=(0, 12))
        tk.Entry(in_box, textvariable=self.input_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground=self.fg_color, relief=tk.FLAT, width=32).pack(side=tk.LEFT, padx=(0, 5), ipady=3)
        tk.Button(in_box, text="📁", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=lambda: self._browse_dir(self.input_dir_var)).pack(side=tk.LEFT)

        tk.Label(left_pane, text="3. Thư Mục Lưu Kết Quả (Output):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.fg_color).pack(anchor="w", pady=(0, 4))
        out_box = tk.Frame(left_pane, bg=self.card_bg)
        out_box.pack(fill=tk.X, pady=(0, 12))
        tk.Entry(out_box, textvariable=self.out_dir_var, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground=self.fg_color, relief=tk.FLAT, width=32).pack(side=tk.LEFT, padx=(0, 5), ipady=3)
        tk.Button(out_box, text="📁", font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT, command=lambda: self._browse_dir(self.out_dir_var)).pack(side=tk.LEFT)

        tk.Label(left_pane, text="4. Cấu Hình Cắt Chuẩn:", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.fg_color).pack(anchor="w", pady=(0, 4))

        cfg_box = tk.Frame(left_pane, bg=self.card_bg)
        cfg_box.pack(fill=tk.X, pady=(0, 12))

        tk.Label(cfg_box, text="Kích thước (WxH):", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).grid(row=0, column=0, sticky="w", pady=2)
        wh_frame = tk.Frame(cfg_box, bg=self.card_bg)
        wh_frame.grid(row=0, column=1, sticky="w", pady=2)
        tk.Entry(wh_frame, textvariable=self.target_w_var, width=5, bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Label(wh_frame, text="x", bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT, padx=2)
        tk.Entry(wh_frame, textvariable=self.target_h_var, width=5, bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT).pack(side=tk.LEFT)

        tk.Label(cfg_box, text="Tiền tố tên file:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).grid(row=1, column=0, sticky="w", pady=2)
        tk.Entry(cfg_box, textvariable=self.prefix_var, width=8, bg=self.input_bg, fg=self.fg_color, relief=tk.FLAT).grid(row=1, column=1, sticky="w", pady=2)

        self.btn_start = tk.Button(
            left_pane,
            text="🚀 BẮT ĐẦU CẮT MŨ HÀNG LOẠT",
            font=("Segoe UI", 11, "bold"),
            bg=self.btn_green,
            fg=self.btn_green_text,
            activebackground="#94e2d5",
            relief=tk.FLAT,
            cursor="hand2",
            pady=10,
            command=self._start_process_thread
        )
        self.btn_start.pack(fill=tk.X, pady=(15, 8))

        self.btn_open_out = tk.Button(
            left_pane,
            text="📂 Mở Thư Mục Kết Quả (Output)",
            font=("Segoe UI", 9),
            bg=self.input_bg,
            fg=self.fg_color,
            relief=tk.FLAT,
            command=self._open_output_dir
        )
        self.btn_open_out.pack(fill=tk.X)

        right_pane = tk.Frame(body, bg=self.card_bg, padx=15, pady=15)
        right_pane.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(right_pane, text="Nhật Ký Quá Trình Cắt (Log):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.fg_color).pack(anchor="w", pady=(0, 4))

        self.txt_log = tk.Text(right_pane, height=14, bg=self.input_bg, fg=self.fg_color, insertbackground=self.fg_color, relief=tk.FLAT, font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(right_pane, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(right_pane, text="Xem Trước Kết Quả Vừa Cắt (Live Preview):", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.fg_color).pack(anchor="w", pady=(0, 4))

        self.preview_frame = tk.Frame(right_pane, bg=self.input_bg, height=130)
        self.preview_frame.pack(fill=tk.X)
        self.preview_frame.pack_propagate(False)

        self.lbl_preview_placeholder = tk.Label(self.preview_frame, text="Chưa có ảnh nào được cắt", font=("Segoe UI", 9, "italic"), bg=self.input_bg, fg="#6c7086")
        self.lbl_preview_placeholder.pack(expand=True)

    def _browse_dir(self, var: tk.StringVar):
        d = filedialog.askdirectory(initialdir=var.get() or self.base_dir)
        if d:
            var.set(os.path.normpath(d))

    def _open_output_dir(self):
        out_dir = self.out_dir_var.get()
        if os.path.exists(out_dir):
            os.startfile(out_dir)
        else:
            messagebox.showwarning("Thông báo", f"Thư mục chưa tồn tại:\n{out_dir}")

    def _log(self, msg: str):
        def _append():
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)
        self.root.after(0, _append)

    def _update_progress(self, val: float):
        self.root.after(0, lambda: self.progress_bar.configure(value=val))

    def _on_card_saved_preview(self, card_path: str, card_img: np.ndarray):
        def _update_ui():
            if self.lbl_preview_placeholder:
                self.lbl_preview_placeholder.pack_forget()

            h, w = card_img.shape[:2]
            target_thumb_h = 110
            target_thumb_w = int(w * (target_thumb_h / float(h)))
            thumb = cv2.resize(card_img, (target_thumb_w, target_thumb_h), interpolation=cv2.INTER_AREA)
            thumb_rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(thumb_rgb)
            img_tk = ImageTk.PhotoImage(img_pil)
            self.preview_images.append(img_tk)

            for child in self.preview_frame.winfo_children():
                child.destroy()

            lbl_img = tk.Label(self.preview_frame, image=img_tk, bg=self.input_bg)
            lbl_img.pack(side=tk.LEFT, padx=10, pady=5)

            lbl_txt = tk.Label(
                self.preview_frame,
                text=f"Đã cắt: {os.path.basename(card_path)}\nKích thước: {w}x{h} px\nChuẩn 100% không lệch mép",
                font=("Segoe UI", 9),
                bg=self.input_bg,
                fg=self.btn_green,
                justify=tk.LEFT
            )
            lbl_txt.pack(side=tk.LEFT, padx=5)

        self.root.after(0, _update_ui)

    def _start_process_thread(self):
        if self.is_processing:
            return

        in_dir = self.input_dir_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        acc_id = self.acc_id_var.get().strip()
        prefix = self.prefix_var.get().strip() or "mu_"
        tw = self.target_w_var.get()
        th = self.target_h_var.get()

        if not os.path.exists(in_dir):
            messagebox.showerror("Lỗi", f"Thư mục đầu vào không tồn tại:\n{in_dir}")
            return

        self.is_processing = True
        self.btn_start.configure(state=tk.DISABLED, bg="#6c7086")
        self.txt_log.delete("1.0", tk.END)
        self.progress_bar.configure(value=0)
        self.preview_images.clear()

        def _worker():
            try:
                res = process_batch(
                    input_dir=in_dir,
                    output_dir=out_dir,
                    target_size=(tw, th),
                    file_prefix=prefix,
                    acc_id=acc_id,
                    sync_global_output=True,
                    log_fn=self._log,
                    progress_fn=self._update_progress,
                    on_card_saved_fn=self._on_card_saved_preview
                )
                self.root.after(0, lambda: messagebox.showinfo(
                    "Hoàn tất",
                    f"Đã cắt thành công {res['total_saved']}/{res['total_files']} ảnh Mũ!\n\nLưu tại: {out_dir}"
                ))
            except Exception as e:
                self._log(f"\n[Lỗi nghiêm trọng] {e}")
                self.root.after(0, lambda: messagebox.showerror("Lỗi", str(e)))
            finally:
                self.is_processing = False
                self.root.after(0, lambda: self.btn_start.configure(state=tk.NORMAL, bg=self.btn_green))

        threading.Thread(target=_worker, daemon=True).start()


# ==============================================================================
# ĐIỂM KHỞI CHẠY (CLI + GUI ENTRY POINT)
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Tool tự động cắt Mũ (Helmet Cropper)")
    parser.add_argument("--acc", type=str, default="", help="Mã tài khoản (ví dụ: 654)")
    parser.add_argument("--input", type=str, default="", help="Thư mục ảnh đầu vào")
    parser.add_argument("--output", type=str, default="", help="Thư mục lưu kết quả")
    parser.add_argument("--width", type=int, default=683, help="Chiều rộng chuẩn đầu ra (mặc định 683)")
    parser.add_argument("--height", type=int, default=773, help="Chiều cao chuẩn đầu ra (mặc định 773)")
    parser.add_argument("--prefix", type=str, default="mu_", help="Tiền tố tên file (mặc định 'mu_')")
    parser.add_argument("--no-gui", action="store_true", help="Chạy chế độ dòng lệnh (CLI không giao diện)")
    parser.add_argument("--no-sync", action="store_true", help="Không đồng bộ sang output tổng")

    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))

    if args.no_gui or args.input:
        in_dir = args.input
        if not in_dir:
            if args.acc:
                in_dir = os.path.join(base_dir, "input", args.acc)
            else:
                in_dir = os.path.join(base_dir, "input")

        out_dir = args.output
        if not out_dir:
            if args.acc:
                out_dir = os.path.join(base_dir, "output", args.acc)
            else:
                out_dir = os.path.join(base_dir, "output")

        process_batch(
            input_dir=in_dir,
            output_dir=out_dir,
            target_size=(args.width, args.height),
            file_prefix=args.prefix,
            acc_id=args.acc,
            sync_global_output=not args.no_sync,
            log_fn=print
        )
    else:
        root = tk.Tk()
        app = HelmetCropperGUI(root)
        if args.acc:
            app.acc_id_var.set(args.acc)
            app._on_acc_changed()
        root.mainloop()


if __name__ == "__main__":
    main()
