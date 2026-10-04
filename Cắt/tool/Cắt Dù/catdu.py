#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tool cắt Dù và đồ bay trong Kho Đồ PUBG Mobile.

- Dò lưới 3 cột theo pha cuộn của ảnh, không dùng tọa độ Y cố định.
- Cắt sát viền trong và chuẩn hóa từng thẻ về 216x216.
- Chỉ giữ thẻ nền vàng, đỏ hoặc tím; loại thẻ nền xám.
- Loại ảnh trùng khi nhiều ảnh chụp có vùng cuộn chồng nhau.
"""

import argparse
import os
import sys
import threading
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox


TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(TOOL_DIR))
ITEM_TOOL_DIR = os.path.join(os.path.dirname(TOOL_DIR), "Cắt Item")
if ITEM_TOOL_DIR not in sys.path:
    sys.path.insert(0, ITEM_TOOL_DIR)

from catitem import (  # noqa: E402
    Deduplicator,
    ItemCardDetector,
    cv2_imread_utf8,
    cv2_imwrite_utf8,
)


class ParachuteCardDetector(ItemCardDetector):
    """Dò thẻ Dù/đồ bay rồi lọc theo màu nền độ hiếm."""

    @staticmethod
    def _background_hsv(card: np.ndarray) -> Tuple[float, float, float]:
        """Lấy màu nền bền vững từ bốn góc, tránh vật phẩm ở giữa thẻ."""
        hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
        height, width = hsv.shape[:2]
        corner = max(8, int(round(min(height, width) * 0.20)))
        samples = np.concatenate([
            hsv[:corner, :corner].reshape(-1, 3),
            hsv[:corner, -corner:].reshape(-1, 3),
            hsv[-corner:, :corner].reshape(-1, 3),
            hsv[-corner:, -corner:].reshape(-1, 3),
        ])
        hue, saturation, value = np.median(samples, axis=0)
        return float(hue), float(saturation), float(value)

    @classmethod
    def has_allowed_background(cls, card: np.ndarray) -> bool:
        """Giữ vàng/đỏ/tím và bỏ nền xám hoặc màu không thuộc yêu cầu."""
        if card is None or card.size == 0:
            return False
        hue, saturation, _ = cls._background_hsv(card)
        if saturation < 55.0:
            return False

        # OpenCV HSV: vàng/đỏ nằm gần 0..35 hoặc 170..179; tím của giao diện
        # PUBG nằm khoảng 125..160. Dải >=120 bao trọn tím nhưng vẫn loại nền
        # xám bằng điều kiện độ bão hòa phía trên.
        return hue <= 35.0 or hue >= 120.0

    def detect_and_crop(self, img: np.ndarray, log_fn=print) -> List[np.ndarray]:
        cards = super().detect_and_crop(img, log_fn=lambda _message: None)
        kept = [card for card in cards if self.has_allowed_background(card)]
        removed = len(cards) - len(kept)
        log_fn(
            f"  [+] Dò được {len(cards)} ô Dù/đồ bay; giữ {len(kept)} ô "
            f"nền vàng/đỏ/tím, bỏ {removed} ô nền xám."
        )
        return kept


def process_batch(
    input_dir: str,
    output_dir: str,
    enable_dedup: bool = True,
    border_margin: int = 5,
    target_size: Tuple[int, int] = (216, 216),
    file_prefix: str = "du_",
    acc_id: Optional[str] = None,
    sync_global_output: bool = True,
    log_fn=print,
    on_card_saved_fn=None,
) -> Dict:
    """Cắt hàng loạt ảnh Dù/đồ bay và đồng bộ ra output tổng."""
    os.makedirs(output_dir, exist_ok=True)
    global_out_dir = None
    if sync_global_output and acc_id:
        global_out_dir = os.path.join(PROJECT_ROOT, "output", acc_id)
        os.makedirs(global_out_dir, exist_ok=True)

    supported = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    files = []
    if os.path.isdir(input_dir):
        for root, _, names in os.walk(input_dir):
            for name in names:
                if os.path.splitext(name)[1].lower() in supported:
                    files.append(os.path.join(root, name))
    files = sorted(set(files))

    log_fn(f"[*] Tìm thấy {len(files)} ảnh Dù/đồ bay trong '{input_dir}'.")
    detector = ParachuteCardDetector(
        target_size=target_size,
        border_margin=border_margin,
    )
    # Dù và đồ bay thường có silhouette rất giống nhau. Ngưỡng mặc định của
    # Item (12) từng gộp nhầm hai món khác nhau; 8 vẫn loại ảnh cuộn trùng thật
    # nhưng giữ đủ các mẫu gần giống.
    deduplicator = Deduplicator(diff_threshold=8.0) if enable_dedup else None
    saved_count = 0

    for index, path in enumerate(files, 1):
        name = os.path.basename(path)
        log_fn(f"\n[{index}/{len(files)}] Đang xử lý: {name}")
        image = cv2_imread_utf8(path)
        if image is None:
            log_fn(f"  [-] Bỏ qua ảnh lỗi: {name}")
            continue

        cards = detector.detect_and_crop(image, log_fn=log_fn)
        image_saved = 0
        for card in cards:
            if deduplicator and deduplicator.is_duplicate(card):
                continue
            saved_count += 1
            image_saved += 1
            output_name = f"{file_prefix}{saved_count:03d}.png"
            output_path = os.path.join(output_dir, output_name)
            cv2_imwrite_utf8(output_path, card)

            if global_out_dir:
                cv2_imwrite_utf8(os.path.join(global_out_dir, output_name), card)
            if on_card_saved_fn:
                on_card_saved_fn(output_path, card)

        log_fn(f"  [✓] {name} ➔ Đã lưu {image_saved} ô Dù/đồ bay mới.")

    log_fn(f"\n[✓] HOÀN TẤT: Đã lưu {saved_count} ảnh Dù/đồ bay vào '{output_dir}'.")
    return {"total_saved": saved_count, "total_files": len(files)}


class ParachuteCropperGUI:
    """Giao diện gọn để chạy riêng tool Cắt Dù."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TOOL CẮT DÙ / ĐỒ BAY")
        self.root.geometry("760x310")
        self.root.configure(bg="#1e1e2e")
        self.input_var = tk.StringVar(value=os.path.join(TOOL_DIR, "input"))
        self.output_var = tk.StringVar(value=os.path.join(TOOL_DIR, "output"))
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self._build()

    def _build(self):
        tk.Label(
            self.root,
            text="CẮT DÙ / ĐỒ BAY — CHỈ NỀN VÀNG, ĐỎ, TÍM",
            font=("Segoe UI", 14, "bold"), bg="#1e1e2e", fg="#cdd6f4",
        ).pack(pady=(18, 14))

        for label, variable, chooser in (
            ("Input", self.input_var, self._choose_input),
            ("Output", self.output_var, self._choose_output),
        ):
            row = tk.Frame(self.root, bg="#1e1e2e")
            row.pack(fill=tk.X, padx=24, pady=5)
            tk.Label(row, text=label, width=8, anchor="w", bg="#1e1e2e", fg="#cdd6f4").pack(side=tk.LEFT)
            tk.Entry(row, textvariable=variable, bg="#313244", fg="#cdd6f4", relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            tk.Button(row, text="Chọn", command=chooser, bg="#45475a", fg="#cdd6f4", relief=tk.FLAT).pack(side=tk.LEFT, padx=(8, 0))

        self.run_button = tk.Button(
            self.root, text="BẮT ĐẦU CẮT DÙ", command=self._run,
            font=("Segoe UI", 11, "bold"), bg="#a6e3a1", fg="#11111b",
            relief=tk.FLAT, pady=8,
        )
        self.run_button.pack(fill=tk.X, padx=24, pady=(18, 8))
        tk.Label(self.root, textvariable=self.status_var, bg="#1e1e2e", fg="#bac2de").pack()

    def _choose_input(self):
        path = filedialog.askdirectory(initialdir=self.input_var.get())
        if path:
            self.input_var.set(path)

    def _choose_output(self):
        path = filedialog.askdirectory(initialdir=self.output_var.get())
        if path:
            self.output_var.set(path)

    def _run(self):
        self.run_button.configure(state=tk.DISABLED)
        self.status_var.set("Đang xử lý...")

        def worker():
            result = process_batch(
                self.input_var.get(), self.output_var.get(),
                sync_global_output=False,
            )
            def finish():
                self.run_button.configure(state=tk.NORMAL)
                self.status_var.set(f"Hoàn tất: {result['total_saved']} ảnh")
                messagebox.showinfo("Hoàn tất", f"Đã cắt {result['total_saved']} ảnh Dù/đồ bay.")
            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Tool cắt Dù và đồ bay")
    parser.add_argument("--cli", action="store_true")
    parser.add_argument("-i", "--input", default=os.path.join(TOOL_DIR, "input"))
    parser.add_argument("-o", "--output", default=os.path.join(TOOL_DIR, "output"))
    parser.add_argument("-a", "--acc", default=None)
    args = parser.parse_args()

    if args.cli:
        process_batch(args.input, args.output, acc_id=args.acc)
    else:
        root = tk.Tk()
        ParachuteCropperGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()
