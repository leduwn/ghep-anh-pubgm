# Ghép Ảnh PUBG Mobile (Auto-Cut DienLV)

Tool tự động nhận diện thẻ súng PUBG Mobile, đọc cấp độ (Level) bằng OCR, trích xuất bộ đếm (StatTrak), cắt hình và ghép thành lưới (Grid) xuất ra các định dạng ảnh PNG, file Photoshop PSD và script JSX.

## Tính Năng Chính
- **Tự động nhận diện súng:** Tìm kiếm và cắt khung thẻ súng chính xác dựa trên đường viền và tỷ lệ aspect ratio.
- **Nhận diện Level bằng EasyOCR:** Nhận dạng cấp độ từ ảnh tiêu đề, tự động chuẩn hoá ký tự nhận diện nhầm (`|`, `l`, `i`, `[` -> `1`) và đọc số lượt nâng cấp `x/y`.
- **Nhận diện bộ đếm (Kill Counter):** Tự động phát hiện và cắt bộ đếm số mạng hạ gục.
- **Bố cục lưới (Grid Layout) chuẩn:** Tự động chuẩn hoá kích thước ô ảnh đồng đều (dựa trên kích thước median), tránh tình trạng hàng dưới bị kéo dài hay lệch kích thước.
- **Sắp xếp theo cấp độ và loại súng:** Hỗ trợ sắp xếp ưu tiên Level cao trước, phân nhóm theo loại súng (M416, AKM, UMP, AUG...) và độ hiếm.
- **Xuất đa định dạng:** Xuất ảnh tổng hợp `.png`, file nhiều layer `.psd` và file script điều khiển Photoshop `.jsx`.

## Cấu Trúc Thư Mục
```text
├── assets/
│   ├── gun/
│   │   ├── akmhoanguc.png
│   │   └── umpsinhnhat.png
│   └── itc.ttf
├── input/
├── config.json
├── dienlv.py
├── requirements.txt
└── README.md
```

## Cài Đặt & Sử Dụng
1. Cài đặt các thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

2. Đặt ảnh chụp màn hình cần cắt vào thư mục `input/`.

3. Chạy công cụ:
```bash
python dienlv.py
```
Các tham số tuỳ chọn:
- `-i <N>`: Số ảnh trên mỗi cột (mặc định 4).
- `-s`: Sắp xếp súng theo cấp độ và độ ưu tiên.
