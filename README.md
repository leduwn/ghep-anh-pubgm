# Auto-Cut PUBG Mobile Suite

Bộ công cụ tự động cắt, lọc, nhận diện và ghép ảnh trang bị PUBG Mobile (Súng, Trang phục, Xe, Balo, Mũ, Item...).

## Tổng Quan Các Phân Hệ

1. **DienLV (`DienLV/`):**
   - Tool tự động nhận diện thẻ súng PUBG Mobile, đọc cấp độ (Level) bằng OCR, trích xuất bộ đếm Kill Counter.
   - Chuẩn hoá kích thước ô lưới ảnh (Grid Layout), tự động sắp xếp ưu tiên Level cao và dòng súng.
   - Xuất file `.png`, `.psd` (nhiều layer) và `.jsx`.

2. **Cắt (`Cắt/`):**
   - Bộ module nhận diện và cắt chi tiết các loại trang bị:
     - Cắt Balo (`tool/Cắt Balo/`)
     - Cắt Dù (`tool/Cắt Dù/`)
     - Cắt Hành Động (`tool/Cắt Hành Động/`)
     - Cắt Item (`tool/Cắt Item/`)
     - Cắt Lựu Đạn (`tool/Cắt Lựu Đạn/`)
     - Cắt Mũ (`tool/Cắt Mũ/`)
     - Cắt Mặt Nạ (`tool/Cắt Mặt Nạ/`)
     - Cắt Súng (`tool/Cắt Súng/`)
     - Cắt Trang Phục (`tool/Cắt Trang Phục/`)
     - Cắt Xe (`tool/Cắt Xe/`)
     - Cắt Đồ (`tool/Cắt Đồ/`)
   - Điều khiển tự động hoá qua `Start.py` và `Sung.py`.

3. **Ghép PSD (`GhepPSD/`):**
   - Hệ thống tự động dàn trang và xuất bản thiết kế Photoshop PSD chất lượng cao theo template định dạng sẵn (`classic_compact.json`, `classic_wide.json`...).
   - Tự động gắn nhãn số sao trang phục (1-7 sao, VIP) và vé xe nâng cấp.

4. **Ghép Ảnh (`GhepAnh/`):**
   - Module xử lý ghép nối ảnh trang bị nhanh dạng lưới.

5. **LV Studio Python (`LV-Studio-Python/`):**
   - Ứng dụng Desktop UI / Web UI (Bản 19) hỗ trợ ghép Account + Súng toàn diện.
   - Tính năng tự nhận diện lưới linh tinh (động tác, mũ, dù, tóc, mặt...), tự động bỏ ô khóa/ô trống và giữ nguyên tỷ lệ ảnh.
   - Hỗ trợ xếp cột linh hoạt, gắn VIP / Star, trích xuất UID, chỉnh màu GPU / WebGL2 và xuất bản thành phẩm.

6. **Dọn Rác (`don_dep_rac.py`):**
   - Script dọn dẹp các tệp tạm thời, bộ nhớ đệm `__pycache__` và dữ liệu trung gian giữa các phiên chạy.

## Cài Đặt

Cài đặt các thư viện cần thiết:
```bash
pip install -r DienLV/requirements.txt
```
Thư viện sử dụng: `opencv-python`, `easyocr`, `numpy`, `Pillow`, `pytoshop`, `requests`.
