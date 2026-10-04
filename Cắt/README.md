# 🎮 AUTO-CUT PUBG MOBILE INVENTORY & WORKSHOP SCREENSHOTS

> **Hệ thống tự động hóa thông minh (Computer Vision - OpenCV / NumPy / Tkinter GUI & CLI):**
> Phân loại chính xác 100% từng loại màn hình game PUBG Mobile từ ảnh chụp màn hình thô ➔ Tự động phân chia vào các tool chuyên biệt ➔ Nhận diện vị trí động, khử trùng lặp khi cuộn và cắt ảnh chuẩn pixel theo từng mã tài khoản (Account ID).

---

## ✨ TÍNH NĂNG NỔI BẬT

1. **Nhận diện & Phân loại thông minh 11 loại màn hình (AI Classifier)**:
   - 🔫 **Súng (`SUNG`)**: Nhận diện Xưởng Nâng Cấp Súng (Gun Lab) qua nút *Nâng Cấp* vàng, logo *Xưởng*, checkbox cam *Đã có*.
   - 🚗 **Xe (`XE`)**: Nhận diện Tab *Vô Lăng* xanh hoặc tỷ lệ khung thẻ xe hình chữ nhật (`2.1 <= aspect <= 3.1`).
   - ✨ **Trang Phục Toàn Thân (`TRANG_PHUC`)**: Nhận diện màn hình nhân vật toàn thân (tự động phân biệt Sảnh thường và Sảnh siêu xe).
   - 👕 **Đồ 3 Ô (`DO`)**: Nhận diện thẻ popup đỏ/trắng chi tiết set đồ và định vị chính xác 3 ô đồ theo chu kỳ đa hàng Sobel-Y.
   - 🪖 **Mũ (`MU`)**: Nhận diện Tab Mũ trong Kho Đồ, tự động lấy 9 ô trên cùng (lưới 3x3), mép hàng đầu quanh $y \approx 208$.
   - 🎒 **Balo (`BALO`)**: Nhận diện Tab Balo trong Kho Đồ, tự động lấy 9 ô trên cùng (lưới 3x3), mép hàng đầu quanh $y \approx 208$.
   - 🎭 **Mặt Nạ (`MAT_NA`)**: Nhận diện Tab Mặt Nạ / Kính trong Kho Đồ, tự động dò biên X (Sobel-X) và Y (Sobel-Y) lấy 9 ô trên cùng.
   - 💣 **Lựu Đạn (`LUU_DAN`)**: Nhận diện Tab Vũ Khí Ném / Lựu Đạn trong Kho Đồ, cắt thẻ không viền.
   - 🪂 **Dù (`DU`)**: Nhận diện Tab Dù Lượn trong Kho Đồ, cắt thẻ chuẩn hóa ô vuông.
   - 💇 **Item (`ITEM`)**: Nhận diện Tab Vật Phẩm / Ngoại Hình (kiểu tóc huy hiệu 4 xanh, 5 đỏ, khuôn mặt mở khóa, thẻ đổi tên,...).
   - 💃 **Hành Động (`HANH_DONG`)**: Nhận diện Tab Động Tác / Emote nhảy múa trong Kho Đồ.

2. **Khử trùng lặp thông minh khi cuộn (Deduplication)**:
   - Tự động so khớp độ tương đồng ảnh thẻ khi người dùng cuộn danh sách (Súng, Xe), chỉ lưu lại các vật phẩm chưa từng xuất hiện.

3. **Cắt động theo thanh cuộn (Dynamic Sobel-Y Edge Detection)**:
   - Tự động quét cạnh gradient để tìm chính xác mép bắt đầu của ô đồ đầu tiên, khắc phục hoàn toàn việc thanh cuộn bị lệch vị trí.

4. **Đồng bộ hóa 1-Click theo mã tài khoản**:
   - Quét toàn bộ ảnh đặt trực tiếp trong `input/` ➔ Thêm ảnh kết quả vào `output/<mã_acc>/` theo mã đã nhập trên giao diện.
   - Khi chạy lại cùng mã acc, ảnh cũ được giữ nguyên và ảnh mới được đánh số tiếp nối; không xóa hoặc ghi đè kết quả đã có.

---

## 📁 CẤU TRÚC THƯ MỤC DỰ ÁN

```text
Auto-Cut/
├── GhepAnh/                    # Bảng điều khiển Master tích hợp toàn bộ quy trình
│   ├── GhepAnh.py              # GUI tổng: Cắt ảnh -> Tạo súng -> Ghép PSD
│   └── CHAY_GHEP_ANH.cmd       # Phím tắt 1-Click mở bảng điều khiển tổng
│
├── Cắt/                        # Hệ thống phân loại & cắt ảnh tự động
│   ├── Start.py                # Master Dashboard (Giao diện trung tâm & CLI điều phối cắt)
│   ├── Sung.py                 # Chuyển ảnh được nhận diện là Súng sang DienLV/standalone/input
│   ├── CHAY_START.cmd          # Phím tắt 1-Click khởi chạy Master GUI Cắt
│   ├── clean_tools.py          # Tiện ích dọn dẹp input/output tạm trong các tool con
│   ├── check_tabs.py           # Tiện ích kiểm tra độ chính xác phân loại tab
│   ├── README.md               # Tài liệu hướng dẫn sử dụng hệ thống Cắt
│   │
│   ├── input/                  # Đặt trực tiếp toàn bộ ảnh chụp màn hình gốc tại đây
│   ├── output/                 # Thư mục xuất ảnh kết quả cuối cùng theo mã acc
│   │   └── <mã_acc>/           # sung_xxx, xe_xxx, tp_xxx, do_xxx, mu_xxx, balo_xxx, matna_xxx,...
│   │
│   ├── tests/                  # Bộ kiểm thử tự động (unittest)
│   │
│   └── tool/                   # Các module công cụ cắt chuyên biệt độc lập
│       ├── Cắt Súng/           # catsung.py + CHAY_CAT_SUNG.cmd (prefix: sung_)
│       ├── Cắt Xe/             # catxe.py + CHAY_CAT_XE.cmd (prefix: xe_)
│       ├── Cắt Trang Phục/     # cattrangphuc.py + CHAY_CAT_TRANG_PHUC.cmd (prefix: tp_)
│       ├── Cắt Đồ/             # catdo.py + CHAY_CAT_DO.cmd (prefix: do_)
│       ├── Cắt Mũ/             # catmu.py + CHAY_CAT_MU.cmd (prefix: mu_)
│       ├── Cắt Balo/           # catbalo.py + CHAY_CAT_BALO.cmd (prefix: balo_)
│       ├── Cắt Mặt Nạ/         # catmatna.py + CHAY_CAT_MAT_NA.cmd (prefix: matna_)
│       ├── Cắt Lựu Đạn/        # catluudan.py + CHAY_CAT_LUU_DAN.cmd (prefix: luudan_)
│       ├── Cắt Dù/             # catdu.py + CHAY_CAT_DU.cmd (prefix: du_)
│       ├── Cắt Item/           # catitem.py + CHAY_CAT_ITEM.cmd (prefix: item_)
│       └── Cắt Hành Động/      # cathanhdong.py + CHAY_CAT_HANH_DONG.cmd (prefix: hd_)
│
├── GhepPSD/                    # Công cụ ghép ảnh tự động vào template Photoshop PSD
├── DienLV/                     # Công cụ tạo ảnh súng nâng cấp (DienLV.exe)
└── preset/                     # Các template file mẫu PSD (.psd)
```

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG

### 1. Yêu cầu hệ thống
- **Hệ điều hành**: Windows 10 / 11
- **Python**: Phiên bản 3.9 trở lên
- Cài đặt các thư viện cần thiết:
```bash
pip install opencv-python pillow numpy
```

### 2. Sử dụng Giao diện Master (Khuyên dùng)
1. Thả toàn bộ ảnh chụp màn hình của tài khoản trực tiếp vào `input/`, không tạo thư mục con theo mã acc.
2. Nhấp đúp chạy file **`CHAY_START.cmd`**.
3. Trên giao diện:
   - Bắt buộc nhập mã tài khoản vào ô **1. NHẬP MÃ ACC**.
   - Bấm nút xanh **🚀 1-CLICK TỰ ĐỘNG TẤT CẢ**.
4. Tool sẽ tự động phân loại, chạy từng module và thêm ảnh thành phẩm vào `output/<mã_acc>/`. Nếu mã acc đã từng cắt, ảnh mới sẽ nối tiếp sau ảnh cũ.
5. Nút đỏ **XÓA TOÀN BỘ ẢNH TRONG INPUT** nằm ở góc dưới bên trái của cột điều khiển, chỉ xóa ảnh nguồn sau khi người dùng xác nhận; không xóa output.

### 3. Sử dụng dòng lệnh (CLI Mode)
```bash
# Chạy tự động cho mã tài khoản 654
python Start.py --cli -a 654
```

### 4. Chuyển riêng ảnh Súng sang DienLV

Chạy `python Sung.py`. Tool dùng lại bộ nhận diện màn **Xưởng Súng** của `Start.py`, di chuyển các ảnh có bố cục Xưởng Súng từ `input/` sang `../DienLV/standalone/input/` và giữ nguyên các ảnh loại khác.

### Tự chọn khung cắt trang phục theo sảnh

Tool Trang Phục tự phân biệt hai bố cục, dùng được cả trong Start và khi chạy riêng:

- **Sảnh thường** (mẫu IMG_9804, IMG_9806): giữ nguyên cách cắt và cân vị trí nhân vật hiện tại.
- **Sảnh siêu xe** (mẫu IMG_9925, IMG_9920): nhận diện cấu trúc trần đèn, dùng khung `x=786, y=123, rộng=642, cao=994` trên ảnh gốc `2778 × 1284`, khớp ảnh cắt mẫu đã cung cấp. Tọa độ tự đổi theo kích thước ảnh nguồn.
- Khi trộn hai loại trong cùng input, chỉ ảnh sảnh thường tham gia cân vị trí ngang; ảnh siêu xe dùng khung riêng. Nhật ký phân loại và cắt hiển thị loại sảnh.

Cả hai loại vẫn xuất `tp_*.png`, mặc định được đổi về `774 × 1220` như quy trình ghép hiện tại. Khi gọi module với `target_size=(642, 994)`, ảnh siêu xe ở độ phân giải nguồn chuẩn sẽ giữ nguyên từng pixel của khung mẫu.

Mẫu nhận diện đi kèm tại `Cắt/tool/Cắt Trang Phục/assets/supercar_ceiling.png`; cần giữ file này khi sao chép tool. Bộ nhận diện được hiệu chỉnh cho bố cục sảnh siêu xe trong các ảnh mẫu; phông hoặc góc camera khác cần mẫu bổ sung. Màn không khớp mẫu siêu xe tiếp tục dùng cách cắt sảnh thường sau khi vượt qua kiểm tra giao diện trang phục.

Kiểm tra lại với bốn ảnh mẫu trong `input/`: chạy `python -m unittest discover -s tests -v` tại thư mục chứa `Start.py`. Bộ kiểm tra dùng thư mục tạm cho ảnh xuất.

### 5. Sử dụng từng Tool con riêng lẻ
Mỗi thư mục trong `Cắt/tool/` đều có file launcher `.cmd` độc lập:
- `Cắt/tool/Cắt Súng/CHAY_CAT_SUNG.cmd`
- `Cắt/tool/Cắt Xe/CHAY_CAT_XE.cmd`
- `Cắt/tool/Cắt Trang Phục/CHAY_CAT_TRANG_PHUC.cmd`
- `Cắt/tool/Cắt Đồ/CHAY_CAT_DO.cmd`
- `Cắt/tool/Cắt Mũ/CHAY_CAT_MU.cmd`
- `Cắt/tool/Cắt Balo/CHAY_CAT_BALO.cmd`
- `Cắt/tool/Cắt Mặt Nạ/CHAY_CAT_MAT_NA.cmd`
- `Cắt/tool/Cắt Lựu Đạn/CHAY_CAT_LUU_DAN.cmd`
- `Cắt/tool/Cắt Dù/CHAY_CAT_DU.cmd`
- `Cắt/tool/Cắt Item/CHAY_CAT_ITEM.cmd`
- `Cắt/tool/Cắt Hành Động/CHAY_CAT_HANH_DONG.cmd`

### Lọc riêng ảnh Kiểu tóc trong tool Item

Màn **Kiểu tóc** vẫn chọn riêng tóc nam huy hiệu **4 xanh** và tóc buộc đuôi huy hiệu **5 đỏ**. Ngoài ra, tool dùng hai ảnh khuôn mặt nghiêng/chính diện làm mẫu hình dạng để lấy mọi ô khuôn mặt tương tự, thay vì coi chúng là hai kiểu tóc cố định. Mỗi ô đều được kiểm tra trạng thái khóa; ô khóa bị bỏ qua. Nhóm khuôn mặt được cắt sâu hơn vào trong để loại hết khung xám thừa.

Kết quả vẫn là `item_*.png`, mặc định `216 × 216`, dùng chung cơ chế loại trùng của tool Item. Các màn item khác giữ cách cắt hiện tại. Áp dụng cho cả Start và tool Item chạy riêng; giữ thư mục `Cắt/tool/Cắt Item/assets/` khi sao chép tool. Nhận diện tiêu đề và hai mẫu được hiệu chỉnh theo giao diện tiếng Việt trong ảnh đã cung cấp.

Ảnh xuất cũ trong output của acc không tự bị xóa khi cập nhật bộ lọc; quy tắc này áp dụng cho lượt cắt mới. Chạy `python -m unittest discover -s tests -v` để kiểm tra với ảnh nguồn mẫu; các ca khóa/cuộn dùng biến thể mô phỏng từ ảnh gốc.

### Chọn 9 ô trên cùng của Mũ và Mặt nạ

Hai tool **Mũ** và **Mặt nạ** đều lấy đúng vùng 3 cột × 3 hàng đầu tiên của lưới. Mép trên được dò quanh hàng đầu (`y≈208` trên ảnh `2778 × 1284`), sau đó cắt từ phía trong viền (`y≈212`) với vùng chuẩn `683 × 773`. Tool Mặt nạ không còn bắt đầu từ hàng thứ hai ở `y≈479`.

---

## 📐 KÍCH THƯỚC CHUẨN ĐẦU RA (OUTPUT DIMENSIONS)

| Vật phẩm | Tiền tố file | Kích thước xuất chuẩn | Đặc tính |
| :--- | :--- | :--- | :--- |
| **Súng** | `sung_xxx.png` | `368 x 180 px` | Khử trùng lặp cuộn, cắt sạch viền mép ngoài |
| **Xe** | `xe_xxx.png` | `498 x 190 px` | Khử trùng lặp cuộn, loại bỏ viền đen |
| **Trang Phục** | `tp_xxx.png` | `774 x 1220 px` | Cắt nhân vật toàn thân không méo tỷ lệ (Sảnh thường & Siêu xe) |
| **Đồ (Set)** | `do_xxx.png` | `683 x 773 px` | Tự động dò mép đỉnh theo thanh cuộn |
| **Mũ** | `mu_xxx.png` | `683 x 773 px` | Tự động lấy 9 ô trên cùng (lưới 3x3), cắt chuẩn 3 ô Mũ |
| **Balo** | `balo_xxx.png` | `683 x 773 px` | Tự động lấy 9 ô trên cùng (lưới 3x3), cắt chuẩn 3 ô Balo |
| **Mặt Nạ** | `matna_xxx.png` | `683 x 773 px` | Tự động dò biên X & Y lấy 9 ô trên cùng (lưới 3x3) |
| **Lựu Đạn** | `luudan_xxx.png` | `216 x 216 px` | Khử trùng lặp cuộn, cắt sát thẻ ô vuông |
| **Dù** | `du_xxx.png` | `216 x 216 px` | Khử trùng lặp cuộn, chuẩn hóa ô vuông |
| **Item (Kiểu tóc/Mặt)** | `item_xxx.png` | `216 x 216 px` | Nhận diện tóc 4 xanh, 5 đỏ, khuôn mặt mở khóa |
| **Hành Động** | `hd_xxx.png` | `216 x 216 px` | Khử trùng lặp cuộn, cắt chuẩn ô hành động |

---

## 👤 TÁC GIẢ & BẢN QUYỀN
- Repository: [https://github.com/leduwn/auto-cut-raw](https://github.com/leduwn/auto-cut-raw)
- Tác giả: **leduwn**
