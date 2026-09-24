# Google Play Casual VN — thử tính khả thi nguồn HTML

Ngày kiểm tra: 24/09/2026. Phạm vi: thử nguồn chart, chưa tích hợp Android.

## Kết luận

Truy cập HTTP trực tiếp được, nhưng phương án parse anchor trong HTML ban đầu
chưa lấy được bảng Top Free. Chưa đủ bằng chứng kết luận toàn bộ crawl Android
không khả thi; cần kiểm tra trang sau khi JavaScript tải xong hoặc request dữ liệu
mà trang công khai sử dụng.

## Thử nghiệm thực tế

URL: https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN

Header: `User-Agent: CasualScout/1.0 (+local-market-research)`;
`Accept-Language: vi-VN,vi;q=0.9`. Không đăng nhập, không bypass.

| Lần | HTTP | Thời gian request và phân tích | HTML bytes | Package khác nhau toàn trang |
|---|---|---|---|---|
| 1 | 200 | 0.812 giây | 1,643,485 | 27 |
| 2 | 200 | 0.906 giây | 1,643,484 | 27 |

Vùng `section` chứa nút `id="ct|apps_topselling_free"` có
`aria-pressed="true"`, nhãn “Miễn phí phổ biến”. Trong vùng đó chỉ có các số
1–9 và markup khung chờ; không có link `/store/apps/details?id=...`.
27 package toàn trang thuộc các vùng khác, không được gán rank Top Free.
Không có heading h1/h2/h3 trong kết quả inventory; giả định heading trong plan
cần được sửa sau khi xác minh cách trang tải dữ liệu.

Đây là kết quả hai request cùng thời điểm, chưa phải đo độ ổn định dài hạn.
Không đo thời gian crawl metadata từng game. `gl=VN` là thị trường yêu cầu,
chưa đối chiếu thứ hạng với ứng dụng Play Store trên điện thoại.

## Code và evidence

Script: `scripts/probe_google_play.py`.

```powershell
.\.venv\Scripts\python.exe scripts/probe_google_play.py
```

Mỗi lần chạy tạo thư mục riêng tại `data/google-play-probe/<UTC timestamp>/`:

- `response.html`: nội dung response lưu nguyên bytes.
- `report.json`: URL gốc/cuối, HTTP status, thời điểm, dung lượng, SHA-256,
  thời gian, package theo thứ tự toàn trang, vùng Top Free và cảnh báo chưa xác minh rank.
- Khi lỗi kết nối, `report.json` lưu lỗi; không tạo bảng xếp hạng giả.

Evidence thành công:

- `data/google-play-probe/20260924T045659777961Z/`
- `data/google-play-probe/20260924T045818440028Z/` (có tách vùng Top Free).

Không ghi vào database sản xuất. Code lưu trong repository; evidence nằm dưới
`data/` đang được Git ignore. Chưa commit.

## Giới hạn kiểm chứng và hướng thử tiếp

Không có browser khả dụng qua công cụ trình duyệt trong phiên thử này,
nên chưa xác minh DOM sau JavaScript hoặc lưu screenshot bảng đã render.
Hướng thử tiếp là render trang công khai, đối chiếu tên/package/thứ hạng
hiển thị và đo thời gian thực tế. Chỉ khi có bằng chứng đó mới chốt parser chart.
Các vấn đề queue, metadata, migration và scheduler chưa triển khai trong thử nghiệm này.
