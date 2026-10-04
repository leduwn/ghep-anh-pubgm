#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Tool tự động nhận diện và cắt danh sách 3 ô đồ (Lựa chọn đồ / Phụ kiện / Skin / Xe / Mũ)
- Tự động định vị cột và 3 ô đồ hoàn chỉnh từ ảnh chụp màn hình input
- Tự động nhận diện chính xác mép bắt đầu của ô đồ số 1 (loại bỏ phần nền xám thừa bên trên khi cuộn lệch)
- Cắt sát viền trong y hệt như ảnh mẫu output, chuẩn hóa kích thước 100% (683 x 773 px)
- Hỗ trợ chọn MÃ ACC, đặt tên chuẩn do_001.png,... và đồng bộ ra d:\Ghep-Anh\output\<mã_acc>\
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
# BỘ NHẬN DIỆN VÀ CẮT 3 Ô ĐỒ (ITEM SELECTION DETECTOR)
# ==============================================================================
class ItemSelectionDetector:
    """
    Module tự động định vị và cắt 3 ô đồ (Item Selection 3-Slot Grid):
    - Tọa độ cột chuẩn ở màn hình 2778x1284: x=1723, w=683, h=773
    - Tự động nhận diện chính xác mép bắt đầu của ô đồ đầu tiên bằng cách phân tích:
      1. Cạnh ngang (Sobel Gradient)
      2. Sự chuyển tiếp màu từ nền xám container sang viền sáng màu của ô đồ (loại bỏ hoàn toàn phần thừa)
    - Cắt sát viền trong y hệt như ảnh mẫu trong output
    - Chuẩn hóa kích thước đầu ra đồng nhất 100% (683 x 773 px)
    """

    def __init__(self, target_size: Tuple[int, int] = (683, 773)):
        self.target_width, self.target_height = target_size

    @staticmethod
    def _has_item_detail_popup(img: np.ndarray) -> bool:
        """Chỉ cho Cắt Đồ chạy khi bảng chi tiết thật đang mở.

        Dò đồng thời hai cạnh dọc kéo dài của popup. Đây là lớp bảo vệ thứ hai
        nếu ảnh được chép tay hoặc input cũ còn sót, để Trang Phục thường không
        thể bị cắt thành ảnh ``do_``.
        """
        if img is None or img.size == 0:
            return False

        height, width = img.shape[:2]
        scale_x = width / 2778.0
        scale_y = height / 1284.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        edge_y1 = max(0, int(round(930 * scale_y)))
        edge_y2 = min(height, int(round(1240 * scale_y)))
        radius = max(2, int(round(5 * scale_x)))
        edge_scores = []
        for base_x in (1325, 1685):
            x = int(round(base_x * scale_x))
            band = gray[
                edge_y1:edge_y2,
                max(0, x - radius):min(width, x + radius + 1),
            ]
            if band.shape[0] < 2 or band.shape[1] < 2:
                return False
            edge_scores.append(float(np.mean(np.abs(np.diff(band, axis=1)))))
        resolution_factor = max(1.0, max(scale_y, 0.25) ** -0.80)
        return min(edge_scores) >= 2.82 * resolution_factor

    def detect_and_crop(self, img: np.ndarray, log_fn=print) -> Optional[np.ndarray]:
        """
        Định vị 3 ô đồ đầy đủ và cắt ảnh chuẩn.
        Tự động nhận diện đỉnh bắt đầu của ô đồ đầu tiên theo thanh cuộn (dynamic scroll offset).
        """
        if img is None:
            return None

        if not self._has_item_detail_popup(img):
            log_fn("  [BỎ QUA] Đây là ảnh Trang Phục thường, không có bảng chi tiết thật.")
            return None

        H, W = img.shape[:2]
        scale_x = W / 2778.0
        scale_y = H / 1284.0

        # Tọa độ X và Width của cột lựa chọn đồ
        inner_x1 = int(round(1723 * scale_x))
        inner_w = int(round(683 * scale_x))
        target_h = int(round(773 * scale_y))

        # Cắt dải cột trung tâm để phân tích viền ngang.
        col_x_start = max(0, int(round(1715 * scale_x)))
        col_x_end = min(W, int(round(2415 * scale_x)))
        col_strip = img[:, col_x_start:col_x_end]

        # Tính gradient cạnh ngang (Sobel Y), bỏ hai mép dọc để icon/tab bên
        # cạnh không làm sai vị trí hàng.
        gray = cv2.cvtColor(col_strip, cv2.COLOR_BGR2GRAY)
        sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3))
        side_margin = max(8, int(round(40 * scale_x)))
        edge_core = sobel_y[:, side_margin:-side_margin]
        if edge_core.size == 0:
            edge_core = sobel_y
        row_edges = np.mean(edge_core, axis=1)

        # Mỗi hàng đồ cao khoảng 250px và cách hàng kế tiếp khoảng 267px.
        # Khi danh sách bị cuộn, hàng trên cùng có thể chỉ còn một phần. Không
        # lấy cạnh mạnh đầu tiên nữa; chấm điểm cả chuỗi 3 hàng đầy đủ để tìm
        # đúng mép trên của hàng hoàn chỉnh đầu tiên.
        slot_h = max(80, int(round(250 * scale_y)))
        row_step = max(slot_h + 4, int(round(267 * scale_y)))
        edge_radius = max(3, int(round(8 * scale_y)))
        inner_margin_y = max(1, int(round(4 * scale_y)))
        start_search_y = int(round(275 * scale_y))
        max_search_y = min(
            H - target_h - inner_margin_y,
            int(round(510 * scale_y)),
            len(row_edges) - 2,
        )

        def edge_peak(position: int) -> float:
            lo = max(0, position - edge_radius)
            hi = min(len(row_edges), position + edge_radius + 1)
            return float(np.max(row_edges[lo:hi])) if hi > lo else 0.0

        scored_candidates = []
        if max_search_y >= start_search_y:
            for y in range(start_search_y + 2, max_search_y - 1):
                # Ngưỡng thấp chỉ dùng để loại nhiễu. Điểm quyết định nằm ở
                # sáu mép lặp lại (trên + dưới của ba hàng), không ở một cạnh.
                if row_edges[y] < 35.0:
                    continue
                if row_edges[y] != np.max(row_edges[y - 2:y + 3]):
                    continue

                boundary_scores = []
                for row_index in range(3):
                    row_top = y + row_index * row_step
                    row_bottom = row_top + slot_h - edge_radius
                    boundary_scores.append(edge_peak(row_top))
                    boundary_scores.append(edge_peak(row_bottom))

                median_score = float(np.median(boundary_scores))
                structure_score = median_score + 0.25 * float(np.mean(boundary_scores))
                scored_candidates.append((structure_score, median_score, y))

        if scored_candidates:
            best_score, best_median, best_y_outer = max(
                scored_candidates,
                key=lambda entry: (entry[0], -entry[2]),
            )
        else:
            best_score = 0.0
            best_median = 0.0
            best_y_outer = -1

        # Ảnh hiện có đều cho điểm cấu trúc >180. Giữ fallback mềm để ảnh bị
        # nén/mờ vẫn được xử lý, nhưng fallback cũng quét toàn vùng cuộn.
        if best_y_outer < 0 or best_median < 80.0:
            search = row_edges[start_search_y:max_search_y + 1]
            if search.size > 0 and float(np.max(search)) > 35.0:
                best_y_outer = start_search_y + int(np.argmax(search))
            else:
                best_y_outer = int(round(294 * scale_y))
            detection_note = "fallback"
        else:
            detection_note = f"grid_score={best_score:.1f}"

        # Tọa độ Y trong (cắt sát vào 4px loại bỏ viền ngoài để vào ruột chuẩn như mẫu output)
        y_inner = best_y_outer + inner_margin_y

        # Đảm bảo không vượt quá biên ảnh
        if y_inner + target_h > H:
            y_inner = H - target_h
        y_inner = max(0, y_inner)

        log_fn(
            f"  [+] Định vị chính xác 3 hàng Đồ (Dynamic Scroll/{detection_note}): "
            f"x={inner_x1}, y={y_inner} (outer_y={best_y_outer}), "
            f"w={inner_w}, h={target_h}"
        )

        crop = img[y_inner:y_inner + target_h, inner_x1:inner_x1 + inner_w]

        if crop.size == 0:
            log_fn("  [X] Vùng cắt không hợp lệ!")
            return None

        # Chuẩn hóa kích thước đầu ra đúng target_size (683 x 773)
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
    file_prefix: str = "do_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    progress_fn=None,
    on_card_saved_fn=None
) -> Dict:
    r"""
    Hàm xử lý cắt ảnh 3 ô đồ hàng loạt từ input sang output.
    Hỗ trợ đồng bộ sang d:\Ghep-Anh\output\<mã_acc>\
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

    detector = ItemSelectionDetector(target_size=target_size)

    # Xóa riêng kết quả do_ cũ trước khi tạo lại. Nếu lần trước phân loại sai
    # nhiều ảnh Trang Phục, các file sai sẽ không còn nằm lẫn sau lần chạy mới.
    for cleanup_dir in (output_dir, global_out_dir):
        if not cleanup_dir or not os.path.isdir(cleanup_dir):
            continue
        for old_path in glob.glob(os.path.join(cleanup_dir, f"{file_prefix}*.png")):
            try:
                os.remove(old_path)
            except OSError:
                pass

    saved_count = 0
    skipped_count = 0

    for idx, file_path in enumerate(files):
        fname = os.path.basename(file_path)

        log_fn(f"\n[{idx + 1}/{total_files}] Đang xử lý: {fname}")

        img = cv2_imread_utf8(file_path)
        if img is None:
            log_fn(f"  [X] Không thể mở ảnh: {fname}")
            continue

        crop = detector.detect_and_crop(img, log_fn=log_fn)
        if crop is None:
            skipped_count += 1
            continue

        saved_count += 1
        out_fname = f"{file_prefix}{saved_count:03d}.png"
        out_path = os.path.join(output_dir, out_fname)
        if cv2_imwrite_utf8(out_path, crop):
            # Đồng bộ sang thư mục output chung nếu có
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
    log_fn(f" - Tổng số ảnh 3 ô đồ đã cắt và lưu thành công: {saved_count} ảnh")
    log_fn(f" - Ảnh Trang Phục thường đã chặn: {skipped_count} ảnh")
    log_fn(f" - Vị trí lưu ảnh: {output_dir}")
    if global_out_dir:
        log_fn(f" - Đồng bộ tới: {global_out_dir}")
    log_fn("=" * 60)

    return {
        "total_files": total_files,
        "total_saved": saved_count,
        "total_skipped": skipped_count,
    }


# ==============================================================================
# GIAO DIỆN ĐỒ HỌA TRỰC QUAN (MODERN TKINTER GUI)
# ==============================================================================
class ItemCropperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Công Cụ Cắt 3 Ô Đồ Tự Động (Auto 3-Item Slots Cropper)")
        self.root.geometry("980x740")
        self.root.minsize(850, 620)

        # Thiết lập màu sắc Dark Modern
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
        self.prefix_var = tk.StringVar(value="do_")

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
            text="TOOL CẮT 3 Ô ĐỒ TỰ ĐỘNG - LỰA CHỌN ĐỒ",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title_lbl.pack(anchor="w")

        desc_lbl = tk.Label(
            header_frame,
            text="Tự động nhận diện 3 ô đồ đầy đủ, tự căn chỉnh khi cuộn bị lệch, đồng bộ theo Mã Acc & chuẩn 683x773 px.",
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
        tk.Label(left_col, text="TÙY CHỌN KÍCH THƯỚC", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))

        size_frame = tk.Frame(left_col, bg=self.card_bg)
        size_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(size_frame, text="Kích thước đầu ra:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        
        size_inputs = tk.Frame(size_frame, bg=self.card_bg)
        size_inputs.pack(fill=tk.X, pady=(2, 0))
        tk.Entry(size_inputs, textvariable=self.target_w_var, width=6, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(side=tk.LEFT)
        tk.Label(size_inputs, text="x", bg=self.card_bg, fg=self.fg_color).pack(side=tk.LEFT, padx=5)
        tk.Entry(size_inputs, textvariable=self.target_h_var, width=6, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(side=tk.LEFT)
        tk.Label(size_inputs, text="px (Chuẩn: 683x773)", font=("Segoe UI", 8), bg=self.card_bg, fg="#a6adc8").pack(side=tk.LEFT, padx=5)

        prefix_frame = tk.Frame(left_col, bg=self.card_bg)
        prefix_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(prefix_frame, text="Tiền tố tên file:", font=("Segoe UI", 9), bg=self.card_bg, fg=self.fg_color).pack(anchor="w")
        tk.Entry(prefix_frame, textvariable=self.prefix_var, width=15, font=("Segoe UI", 9), bg=self.input_bg, fg=self.fg_color, insertbackground="white").pack(anchor="w", pady=(2, 0))

        # Nút điều khiển chính
        self.btn_run = tk.Button(
            left_col,
            text="▶  BẮT ĐẦU CẮT ẢNH ĐỒ",
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

        tk.Label(preview_panel, text="XEM TRƯỚC 3 Ô ĐỒ VỪA CẮT (MẪU MỚI NHẤT)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.accent_color).pack(anchor="w", pady=(0, 5))
        
        self.preview_canvas_frame = tk.Frame(preview_panel, bg=self.card_bg)
        self.preview_canvas_frame.pack(fill=tk.X)

        self.preview_labels = []
        for i in range(4):
            lbl = tk.Label(self.preview_canvas_frame, bg="#11111b", width=16, height=8, relief=tk.RIDGE, bd=1)
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
        """Hiển thị thumbnail ảnh 3 ô đồ vừa cắt vào giao diện."""
        try:
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            thumb_h = 130
            thumb_w = int(w * (thumb_h / h))
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
                self.btn_run.configure(state=tk.NORMAL, bg=self.btn_green, text="▶  BẮT ĐẦU CẮT ẢNH ĐỒ")
                self.progress_bar["value"] = 100
                self.lbl_status.configure(
                    text=f"Hoàn tất: Đã lưu {res['total_saved']} ảnh 3 ô đồ!", 
                    fg=self.btn_green
                )
                messagebox.showinfo("Thành công", f"Đã cắt và lưu thành công {res['total_saved']} ảnh 3 ô đồ vào:\n{out_dir}")

            self.root.after(0, finish)

        threading.Thread(target=run_thread, daemon=True).start()


# ==============================================================================
# ĐIỂM BẮT ĐẦU CHƯƠNG TRÌNH (ENTRY POINT)
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Tool cắt 3 ô đồ tự động từ ảnh input")
    parser.add_argument("--cli", action="store_true", help="Chạy trực tiếp ở chế độ dòng lệnh (không mở GUI)")
    parser.add_argument("-a", "--acc", default=None, help="Mã tài khoản (ví dụ: 654)")
    parser.add_argument("-i", "--input", default=None, help="Thư mục chứa ảnh gốc (mặc định: ./input/<acc> hoặc ./input)")
    parser.add_argument("-o", "--output", default=None, help="Thư mục lưu kết quả (mặc định: ./output/<acc> hoặc ./output)")
    parser.add_argument("-W", "--width", type=int, default=683, help="Chiều rộng chuẩn đầu ra (mặc định: 683)")
    parser.add_argument("-H", "--height", type=int, default=773, help="Chiều cao chuẩn đầu ra (mặc định: 773)")
    parser.add_argument("-p", "--prefix", default="do_", help="Tiền tố tên file kết quả (mặc định: do_)")

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
        print("[*] Khởi động Tool Cắt 3 Ô Đồ ở chế độ CLI...")
        process_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            target_size=(args.width, args.height),
            file_prefix=args.prefix,
            acc_id=acc_id,
            sync_global_output=True,
            log_fn=print
        )
    else:
        root = tk.Tk()
        app = ItemCropperGUI(root)
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
