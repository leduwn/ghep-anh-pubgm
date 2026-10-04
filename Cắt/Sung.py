#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Di chuyển ảnh màn Xưởng Súng sang input của DienLV."""

import os
import shutil
import sys
from typing import Tuple

from Start import ImageClassifier, PROJECT_ROOT, cv2_imread_utf8, list_source_images


SOURCE_DIR = os.path.join(PROJECT_ROOT, "input")
DIENLV_INPUT_DIR = os.path.join(
    os.path.dirname(PROJECT_ROOT),
    "DienLV",
    "standalone",
    "input",
)


def is_gun_workshop_image(image) -> bool:
    """Chỉ nhận màn Xưởng Súng giống các ảnh mẫu, không nhận nhãn SÚNG rộng."""
    return bool(ImageClassifier.is_gun_lab_screen(image))


def unique_destination(folder_path: str, file_name: str) -> str:
    """Tạo tên đích không trùng để tuyệt đối không ghi đè ảnh đã có."""
    destination = os.path.join(folder_path, file_name)
    if not os.path.exists(destination):
        return destination

    stem, extension = os.path.splitext(file_name)
    counter = 1
    while True:
        destination = os.path.join(folder_path, f"{stem}_{counter:03d}{extension}")
        if not os.path.exists(destination):
            return destination
        counter += 1


def move_gun_images(
    source_dir: str = SOURCE_DIR,
    destination_dir: str = DIENLV_INPUT_DIR,
) -> Tuple[int, int, int, int]:
    """Trả về (tổng ảnh, đã di chuyển, không phải súng, ảnh lỗi)."""
    os.makedirs(source_dir, exist_ok=True)
    os.makedirs(destination_dir, exist_ok=True)

    image_files = list_source_images(source_dir)
    moved = 0
    not_gun = 0
    failed = 0

    print(f"[*] Nguồn: {source_dir}")
    print(f"[*] Đích:  {destination_dir}")
    print(f"[*] Tìm thấy {len(image_files)} ảnh cần kiểm tra.")

    for source_path in image_files:
        file_name = os.path.basename(source_path)
        image = cv2_imread_utf8(source_path)
        if image is None:
            failed += 1
            print(f"  [LỖI] Không đọc được ảnh: {file_name}")
            continue

        try:
            is_gun_workshop = is_gun_workshop_image(image)
        except Exception as exc:
            failed += 1
            print(f"  [LỖI] Không thể nhận diện {file_name}: {exc}")
            continue

        if not is_gun_workshop:
            not_gun += 1
            print(f"  [GIỮ LẠI] {file_name} (không phải màn Xưởng Súng)")
            continue

        destination = unique_destination(destination_dir, file_name)
        try:
            shutil.move(source_path, destination)
            moved += 1
            print(f"  [SÚNG] {file_name} -> {os.path.basename(destination)}")
        except Exception as exc:
            failed += 1
            print(f"  [LỖI] Không thể di chuyển {file_name}: {exc}")

    print("=" * 65)
    print(f"Tổng ảnh đã kiểm tra : {len(image_files)}")
    print(f"Ảnh súng đã di chuyển: {moved}")
    print(f"Ảnh được giữ lại     : {not_gun}")
    print(f"Ảnh lỗi              : {failed}")
    print(f"Thư mục đích         : {destination_dir}")
    print("=" * 65)
    return len(image_files), moved, not_gun, failed


def main() -> int:
    _, _, _, failed = move_gun_images()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
