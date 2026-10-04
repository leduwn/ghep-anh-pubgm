#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dọn input/output tạm của từng tool, tuyệt đối không đụng output tổng."""

import os
import shutil


ROOT = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = (
    os.path.realpath(os.path.join(ROOT, "tool"))
    if os.path.isdir(os.path.join(ROOT, "tool"))
    else os.path.realpath(os.path.join(ROOT, "Cắt"))
)
GLOBAL_OUT = os.path.realpath(os.path.join(ROOT, "output"))


def _is_link_like(path: str) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return os.path.islink(path) or bool(is_junction(path))


def _is_safe_tool_folder(folder_path: str, tool_path: str) -> bool:
    """Chỉ cho phép xóa đúng Cắt/<tên tool>/(input|output)."""
    folder_real = os.path.realpath(folder_path)
    tool_real = os.path.realpath(tool_path)

    if os.path.basename(folder_real) not in {"input", "output"}:
        return False
    if os.path.dirname(folder_real) != tool_real:
        return False
    if os.path.dirname(tool_real) != TOOLS_DIR:
        return False

    # Chặn rõ ràng output tổng và mọi đường dẫn nằm bên trong output tổng.
    try:
        if os.path.commonpath([folder_real, GLOBAL_OUT]) == GLOBAL_OUT:
            return False
    except ValueError:
        return False

    return True


def _remove_contents(folder_path: str) -> int:
    deleted = 0
    for item_name in os.listdir(folder_path):
        if item_name == ".gitkeep":
            continue

        item_path = os.path.join(folder_path, item_name)
        try:
            # Không đi theo liên kết sang vị trí khác.
            if _is_link_like(item_path):
                if os.path.isdir(item_path):
                    os.rmdir(item_path)
                else:
                    os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
            deleted += 1
        except Exception as exc:
            print(f"[-] Lỗi xóa {item_path}: {exc}")
    return deleted


def clean_all_temp_images() -> int:
    print("[*] Đang dọn input/output tạm của từng tool...")
    count_deleted = 0

    if not os.path.isdir(TOOLS_DIR):
        print(f"[!] Không tìm thấy thư mục tool: {TOOLS_DIR}")
        return 0

    for tool_name in os.listdir(TOOLS_DIR):
        tool_path = os.path.join(TOOLS_DIR, tool_name)
        if not os.path.isdir(tool_path) or _is_link_like(tool_path):
            continue

        for folder_name in ("input", "output"):
            folder_path = os.path.join(tool_path, folder_name)
            if not os.path.isdir(folder_path) or _is_link_like(folder_path):
                continue
            if not _is_safe_tool_folder(folder_path, tool_path):
                print(f"[!] Bỏ qua đường dẫn không an toàn: {folder_path}")
                continue
            count_deleted += _remove_contents(folder_path)

    print("=" * 60)
    print(f"✓ Đã dọn {count_deleted} mục tạm trong các tool.")
    print(f"✓ Giữ nguyên 100% output tổng: {GLOBAL_OUT}")
    print("=" * 60)
    return count_deleted


if __name__ == "__main__":
    clean_all_temp_images()
