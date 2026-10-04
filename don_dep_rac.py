#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script dọn dẹp file rác và bộ nhớ đệm tạm trong toàn bộ hệ thống Auto-Cut.
Bao gồm:
- Toàn bộ thư mục __pycache__ và các file *.pyc, *.pyo
- Thư mục bộ đệm tạm GhepPSD/Temp
- Thư mục input/output tạm trong các tool con (Cắt/tool/<tool>/(input|output))
- Tuyệt đối giữ nguyên ảnh gốc trong Cắt/input và kết quả trong Cắt/output
"""

import os
import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
GLOBAL_INPUT = ROOT_DIR / "Cắt" / "input"
GLOBAL_OUTPUT = ROOT_DIR / "Cắt" / "output"
PSD_TEMP = ROOT_DIR / "GhepPSD" / "Temp"
TOOLS_DIR = (
    ROOT_DIR / "Cắt" / "tool"
    if (ROOT_DIR / "Cắt" / "tool").is_dir()
    else ROOT_DIR / "Cắt" / "Cắt"
)


def clean_pycache():
    print("[1] Đang dọn dẹp __pycache__ và bytecode *.pyc...")
    count_dirs = 0
    count_files = 0

    for root, dirs, files in os.walk(ROOT_DIR, topdown=False):
        # Bỏ qua thư mục .git và DienLV standalone nếu có
        if ".git" in root or "standalone" in root:
            continue

        for fname in files:
            if fname.endswith((".pyc", ".pyo")):
                fpath = os.path.join(root, fname)
                try:
                    os.remove(fpath)
                    count_files += 1
                except Exception as e:
                    print(f"    [-] Không xóa được {fpath}: {e}")

        for dname in dirs:
            if dname == "__pycache__":
                dpath = os.path.join(root, dname)
                try:
                    shutil.rmtree(dpath)
                    count_dirs += 1
                except Exception as e:
                    print(f"    [-] Không xóa được {dpath}: {e}")

    print(f"    -> Đã xóa {count_dirs} thư mục __pycache__ và {count_files} file bytecode.")


def clean_psd_temp():
    print("[2] Đang dọn dẹp thư mục tạm GhepPSD/Temp...")
    if not PSD_TEMP.is_dir():
        print("    -> Thư mục GhepPSD/Temp không tồn tại.")
        return

    count = 0
    for item in PSD_TEMP.iterdir():
        if item.name == ".gitkeep":
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            count += 1
        except Exception as e:
            print(f"    [-] Lỗi khi xóa {item}: {e}")

    print(f"    -> Đã dọn {count} mục trong GhepPSD/Temp.")


def clean_subtools_io():
    print("[3] Đang dọn dẹp input/output tạm trong các tool con...")
    if not TOOLS_DIR.is_dir():
        print(f"    -> Không tìm thấy thư mục {TOOLS_DIR}.")
        return

    count = 0
    for tool_folder in TOOLS_DIR.iterdir():
        if not tool_folder.is_dir():
            continue

        for sub_name in ("input", "output"):
            target_dir = tool_folder / sub_name
            if not target_dir.is_dir():
                continue

            for item in target_dir.iterdir():
                if item.name == ".gitkeep":
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    count += 1
                except Exception as e:
                    print(f"    [-] Lỗi khi xóa {item}: {e}")

    print(f"    -> Đã dọn {count} mục tạm trong các tool con ({TOOLS_DIR.name}/*).")
    print(f"    -> Giữ nguyên 100% dữ liệu tại {GLOBAL_OUTPUT.name}/ và {GLOBAL_INPUT.name}/.")


def main():
    print("=" * 65)
    print("            DỌN DẸP FILE RÁC & BỘ NHỚ ĐỆM AUTO-CUT")
    print("=" * 65)
    clean_pycache()
    clean_psd_temp()
    clean_subtools_io()
    print("=" * 65)
    print("                     DỌN DẸP HOÀN TẤT!")
    print("=" * 65)


if __name__ == "__main__":
    main()
