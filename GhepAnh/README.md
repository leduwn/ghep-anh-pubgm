# Bảng điều khiển ghép ảnh acc

Nhấp đúp `CHAY_GHEP_ANH.cmd`. Bảng điều khiển có hai tab:

- **Cắt ảnh và tạo súng:** nhập mã acc, chuyển ảnh Xưởng Súng bằng `Sung.py`, bấm **Bắt đầu cắt** để chạy chức năng cắt của `Start.py`, hoặc bấm **Xóa ảnh input** khi cần. Nút xóa hỏi xác nhận và chỉ xóa ảnh trực tiếp trong `Cắt/input`. Nút DienLV mở chương trình tạo ảnh súng.
- **Ghép PSD:** toàn bộ giao diện và chức năng của `GhepPSD.py` nằm ngay trong tab: quét ảnh, chọn form và mã súng, chọn ba ảnh đầu, cấu hình đường dẫn, xem trước, chọn nhãn, ghép PSD và xem nhật ký. Mã acc được dùng chung giữa hai tab.

Các thư mục dữ liệu giữ nguyên: `Cắt/input`, `Cắt/output/<mã acc>`, `DienLV/standalone/input`, và `GhepPSD/KetQua/<mã acc>`. `DienLV.exe` là chương trình đóng gói riêng nên phần thao tác bên trong vẫn diễn ra trong cửa sổ của nó.
