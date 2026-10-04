# Hướng dẫn tool ghép ảnh account thành PSD

Chạy duy nhất file `D:\Ghep-Anh\Auto-Cut\CHAY_GHEP_PSD.cmd`. Toàn bộ thành
phần nội bộ của tool nằm riêng trong `D:\Ghep-Anh\Auto-Cut\GhepPSD`; không cần
mở hoặc chạy thủ công các file bên trong.

## Mục tiêu

- Hàng đầu có ba ô độc lập: hồ sơ trái, hồ sơ giữa, sảnh phải.
- Đọc toàn bộ ảnh con còn lại trong `output/<mã acc>/`.
- Cho chọn một mã súng từ `DienLV/standalone/<mã>/anhle`.
- Ghép theo form gần với ảnh mẫu 732/733/736 mà không che hoặc cắt mất ảnh.
- Tạo cả PNG xem nhanh và PSD thật; mỗi ảnh con là một Smart Object riêng.
- Có thể thêm form mới bằng JSON, không phải sửa lõi Python.

## Những gì đã xác nhận từ dữ liệu thật

- Hai ảnh lớn của lượt hiện tại là `IMG_1264.PNG` và `IMG_1263.PNG`, cùng kích
  thước `2778 × 1284`. Khi đặt mỗi ảnh chiếm nửa chiều rộng, hàng đầu khớp tỷ lệ
  của ảnh mẫu 732.
- Các ảnh con đã có tiền tố ổn định: `sung`, `xe`, `tp`, `do`, `mu`, `balo`,
  `matna`, `luudan`, `du`, `item`, `hd`.
- `1 cat chu.psd` là thư viện chữ/nhãn, không phải template bố cục. File có 75
  layer, gồm chữ VIP, sao, ID, PK và một số icon.
- Photoshop 2025 đã có trên máy và nhận script JSX, nên có thể tạo PSD Smart
  Object thật mà không cần cài thư viện Python ghi PSD hạn chế tính năng.

## Luồng ghép PSD

1. Nhập mã acc và chọn mã súng DienLV trong danh sách.
2. Tool quét `output/<mã acc>` và đề xuất ảnh trái/phải trong `input`.
   Chọn thêm ảnh hồ sơ giữa nếu cần. Mỗi ô có nút `Bỏ` để để trống.
3. Tool đối chiếu các file trong `anhle` với PNG súng đã ghép cạnh PSD DienLV để
   khôi phục đúng thứ tự level và đúng số cột. PNG này chỉ làm bản đồ; không được
   đưa nguyên khối vào PSD mới.
4. Nếu hai ảnh lớn được đề xuất đúng, bấm `CHỌN NHÃN & GHÉP PSD`. Nếu sai, chọn lại.
5. Bảng ảnh trang phục hiện ra. Chọn Thánh giáp 1–7 sao hoặc Thần giáp VIP;
   ảnh còn lại là trang phục thường. Bảng tự đổi thứ tự ngay khi chọn.
6. Bảng xe hiện ra. Mỗi xe mặc định không có nhãn; có thể chọn một dạng vé
   (`3VÉ`, `1VÉ - 4C`, `3VÉ - 2CMT`...) hoặc `VIP`.
7. Bấm `XÁC NHẬN & GHÉP PSD`. Tool xếp Thánh giáp từ 7 sao xuống 1 sao,
   tiếp theo Thần giáp VIP, cuối cùng là trang phục thường. Ảnh xem trước và
   PSD dùng cùng bố cục. Nút `XEM TRƯỚC BỐ CỤC` cũng mở hai bảng chọn này.
8. Photoshop tự mở, đặt từng file nguồn thành Smart Object và lưu kết quả.

Ảnh nguồn vẫn nằm nguyên trong `Cắt\input` và `Cắt\output`. Kết quả không được
ghi lẫn vào đó. Các file hiện trực tiếp trong thư mục mã acc:

```text
GhepPSD/KetQua/<mã acc>/
├── <mã acc>.psd
├── <mã acc>.png
├── xem_truoc.jpg
├── layout.json
├── trang_phuc.json     (lựa chọn loại và sao cho ảnh hiện tại)
├── ve_xe.json          (lựa chọn nhãn cho từng xe)
├── <mã acc>_02.psd       (nếu ghép lại)
├── <mã acc>_02.png
├── xem_truoc_02.jpg
└── layout_02.json
```

Hai lần chạy cùng một acc không ghi đè nhau; bản sau dùng `_02`, `_03`... ngay
trong thư mục mã. Nút xem trước tạo ảnh trong `GhepPSD\Temp` và lưu lựa chọn
trang phục/xe để dùng lại. Mã súng mới xuất hiện khi mở ô chọn; có thể bấm `Làm mới`
bên cạnh ô mã súng mà không cần thoát tool.

## Cấu trúc PSD

```text
Background
IMG_...              (ảnh lớn)
IMG_... / sung_...   (từng ảnh súng)
xe_...               (từng ảnh xe)
tp_...               (từng ảnh trang phục)
do_... / mu_... / balo_... / matna_...
du_... / luudan_... / item_... / hd_...
ACC_WATERMARK_EDIT_ME
```

Không tạo group cho header, súng, xe, trang phục, kho hoặc phụ kiện. Tên layer
lấy thẳng từ tên file nguồn để tìm và đổi thứ tự nhanh trong bảng Layers.

Tool mặc định không chép kho nhãn vào file kết quả để PSD nhẹ và sạch. Người dùng
chọn nhãn trang phục trong bảng trước khi ghép. Tool lấy hình sao/VIP từ
`assets/1 cat chu.psd`, xuất thành ảnh trong `assets/outfit_labels`, rồi đặt từng
nhãn vào group `31_OUTFIT_LABELS` trên đúng ảnh trang phục. Nếu muốn mang thêm
cả kho nhãn theo PSD, có thể bật tùy chọn; chúng sẽ nằm trong group ẩn.
Watermark `Z<mã acc>` vẫn là text layer riêng.

Các kiểu chữ vé xe được xuất từ cùng file PSD vào `assets/vehicle_labels`.
Nhãn vé hoặc VIP được đặt ở góc dưới bên trái mỗi ô xe. Chữ vé đủ lớn để đọc
rõ như mẫu và có thể che một phần nhỏ của xe; VIP được cân riêng theo kích thước
ô xe. Mỗi nhãn nằm trong group
`21_VEHICLE_LABELS` và có thể chỉnh riêng trong Photoshop.

Mỗi ảnh súng trong `anhle` là một Smart Object độc lập. Ví dụ
chọn `HUQ2MQQ7YU` sẽ tạo 22 Smart Object theo đúng bố cục 2 cột × 11 hàng của
`HUQ2MQQ7YU.png`. Các file `sung_*.png` trong output sẽ không bị ghép trùng khi
đã chọn một mã DienLV.

Các file kho `do_*.png`, `mu_*.png`, `balo_*.png`, `matna_*.png` được dùng đúng
nguyên trạng. Tool không crop, không chia panel và không tạo thêm ảnh nhỏ. Một
file đầu vào tương ứng đúng một Smart Object trong danh sách layer phẳng. Thứ
tự là Đồ → Mũ → Balo → Mặt nạ, xếp từ trên xuống rồi mới sang cột kế tiếp.

Ảnh `tp_*.png` cũng được giữ nguyên: một file là một Smart Object độc lập, không
gộp cả bảng trang phục thành group. Lựa chọn được lưu theo mã acc và chỉ được
dùng lại khi nội dung file ảnh vẫn khớp; nếu ảnh thay đổi, ảnh đó trở về loại
trang phục thường để người dùng phân loại lại.

## Form hiện có

- `classic_compact`: rộng 3904 px, gần mẫu 733; kho đồ dùng 2 cột ảnh nguồn.
- `classic_wide`: rộng 5648 px, gần mẫu 732; kho đồ dùng 3 cột ảnh nguồn.
- `classic_small_736`: theo bố cục của chính `Acc/736.psd`; súng/xe cùng
  hai cột trái, trang phục 4 cột, kho đồ 2 cột. Các súng lẽ ra ở vùng trống cạnh
  bảng súng được chuyển xuống hàng cuối để xe, item và phụ kiện lấp phần trên.
  Hàng đồ được cân chiều cao với hàng trang phục; chiều cao súng/xe/phụ kiện
  cũng cân theo tổng chiều cao trang phục, nhưng không giãn/nén vượt 35%.
- Kích thước canvas 5048 px trong JSON chỉ là giá trị mặc định tham khảo; các
  vùng chia theo tỷ lệ, chiều cao dựa trên ảnh đang ghép. Có thể đổi
  `canvas_width` của form mà không đổi quy tắc xếp ảnh. Canvas tự cao vừa đủ
  vùng ảnh dài nhất, không ép theo chiều cao của PSD mẫu.
- `Tự động`: chọn form dựa trên tổng số ảnh, số panel kho đồ và số trang phục.

Form 736 được tự chọn khi acc có 1–6 ảnh đồ, không quá 12 ảnh trang phục và
không quá 55 ảnh con. Nếu bạn muốn dùng form khác, chọn tay trong ô `Form`.
Số sao và VIP được người dùng chọn trong bảng ảnh. Tool tự sắp xếp và gắn nhãn
theo lựa chọn đó; từng layer ảnh vẫn có thể kéo/sắp lại trong Photoshop.

Số cột trang phục được tự đổi theo đúng số ảnh đã lọc:

- 12 ảnh: 3 hàng × 4 cột.
- 15 ảnh: 3 hàng × 5 cột.
- 20 ảnh: 4 hàng × 5 cột.
- 36 ảnh: 6 hàng × 6 cột.

Nếu số lượng khác bốn mốc này, tool dùng số cột mặc định của form và ghi rõ
trong nhật ký để người dùng kiểm tra lại danh sách ảnh.

Giao diện có ba vị trí để chọn: hồ sơ trái, hồ sơ giữa và sảnh phải. Chỉ các ảnh
được chọn mới được ghép và chúng luôn chia đều toàn bộ chiều ngang: 3 ảnh chia
ba, 2 ảnh chia đôi như bố cục cũ, 1 ảnh chiếm toàn bộ. Không tạo cột đen cho vị
trí bỏ trống. Hàng dưới có ba vùng linh hoạt:

- trái: súng, xe, lựu đạn, dù, item, hành động;
- giữa: trang phục;
- phải: đồ, mũ, balo, mặt nạ.

Khi cột phụ nằm cạnh bảng súng, tool giữ nguyên chiều rộng và kéo giãn chiều cao
của cả ảnh xe, dù, lựu đạn, item và hành động bằng đúng chiều cao một hàng súng.
Toàn bộ ảnh súng cũng được chuẩn hóa theo chiều cao giữa của cả bộ, nên một ảnh
súng cao bất thường không làm các hàng sau lệch xuống. Nhờ vậy các đường ngang
hai bên luôn thẳng nhau; ảnh dư tiếp tục chạy xuống dưới.

## Cấu hình đường dẫn khi chuyển máy

Mọi thư mục liên quan nằm trong một file:

`GhepPSD/config.json`

Trong giao diện có nút `CẤU HÌNH THƯ MỤC`. Nút này mở cửa sổ sửa trực tiếp từng
đường dẫn, có nút chọn file/thư mục, đặt lại mặc định và `LƯU & ÁP DỤNG`. Các
đường dẫn mặc định là đường dẫn tương đối tính từ thư mục `GhepPSD`, nên nếu chép
nguyên thư mục `Auto-Cut` sang máy khác thì thường không cần sửa. Nếu bố cục thư
mục trên máy mới khác, chỉ cần sửa các mục trong `paths`: input, output, kết quả,
tạm, form, script Photoshop, kho nhãn và thư mục DienLV. Có thể dùng đường dẫn
tuyệt đối hoặc sửa `config.json` bằng tay.

Xe được tự phân loại theo màu nền của thẻ: toàn bộ ảnh nền đỏ đứng trước, sau đó
mới tới nền tím/xanh. Trong cùng một nhóm màu, thứ tự tên file được giữ nguyên.

Vùng nào không có dữ liệu sẽ bị bỏ và chiều rộng được chia lại. Chiều cao canvas
luôn lấy theo vùng dài nhất, vì vậy không có ảnh nào bị mất. Sau khi xóa bớt ảnh
thừa để số lượng các vùng cân nhau, ảnh tự co về bố cục sát mẫu.

## Giới hạn hiện tại

- Tool chưa tự nhận diện số sao, VIP hoặc loại vé từ hình; người dùng chọn trong
  hai bảng ảnh. Các nhãn LV và tên xe/đồ vẫn ghép tay từ kho nhãn nếu cần.
- Tool đề xuất hai ảnh tổng quan bằng bộ phân loại hiện tại và thứ tự chụp. Khi
  có nhiều ảnh ITEM/OTHER, người dùng vẫn có nút chọn lại.
- Tool chỉ đọc ảnh còn tồn tại trong output. Việc xóa ảnh thừa vẫn do người dùng
  quyết định như yêu cầu.
- Chữ level của súng hiện đã nằm trong từng file `anhle`. Việc tách chữ level
  thành text layer chỉnh sửa riêng có thể làm ở bản sau nếu cần.

## Mở rộng sau này

- Thêm form mới trong `GhepPSD/forms/*.json`.
- Thêm màn chọn/bỏ ảnh bằng checkbox thay cho xóa file vật lý.
- Mở rộng bảng chọn để đặt thêm LV và tên xe/đồ.
- Khi ổn định, gắn nút ghép PSD vào giao diện `Start.py`.
