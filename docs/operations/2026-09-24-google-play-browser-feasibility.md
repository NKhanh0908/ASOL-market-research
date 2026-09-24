# Google Play VN: kết quả thử Chrome/Selenium

## Kết luận

Đã chứng minh lấy được bảng Top Free và Top Grossing Casual VN sau khi trang
render JavaScript. Đây là thử nghiệm độc lập, chưa tích hợp provider, DB hay lịch chạy.

Nguồn: https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN

Ngày thử: 24/09/2026. Evidence được chọn:
`data/google-play-browser-probe/20260924T052100861486Z/`.

| Hạng mục | Kết quả |
|---|---|
| Top Free | 45 package khác nhau, rank 1–45 liên tiếp |
| Top Grossing | 45 package khác nhau, rank 1–45 liên tiếp |
| Metadata | 3/3 game mẫu có JSON-LD và developer link |
| Thời gian Top Free | 5.797 giây |
| Thời gian Top Grossing | 5.750 giây |
| Tổng thời gian | 25.547 giây, gồm mở Chrome, hai bảng, ba trang chi tiết và lưu evidence |
| Lỗi lần chạy được chọn | Không |

Top Free đầu bảng: ZingPlay - Cổng game - iCa, Rhythm Tiles: Pop Songs, Hole.io.
Top Grossing đầu bảng: Coin Master - VTC Game, Candy Crush Saga, Play Together VNG.
Ảnh `top-grossing-section.png` được đối chiếu trực quan: tab doanh thu đang chọn,
các số hạng đầu bảng khớp JSON. Ảnh chụp chỉ thể hiện phần carousel trong viewport;
JSON thu 45 link trong section đã render, không khẳng định đây là toàn bộ chart.

## Thông tin game lấy được

- Tên, package, URL, icon và hạng từ bảng đã render.
- JSON-LD trang chi tiết: tên, mô tả ngắn, category, icon, author/developer,
  rating, rating count, giá app và tiền tệ.
- Developer xác minh trên mẫu: ZINGPLAY VIETNAM, Agile Lion Games, VOODOO.
- Lưu cả nội dung text của trang để xem thêm thông tin; chưa chuẩn hóa đầy đủ
  mô tả dài hoặc trạng thái ads/IAP.
- Không tìm thấy số tiền doanh thu trong dữ liệu thu ở thử nghiệm này.
  Top Grossing là thứ hạng; giá trong `offers` là giá tải ứng dụng, không phải doanh thu.
- Developer là thông tin niêm yết của cửa hàng; chưa chứng minh là studio phát triển trực tiếp.

## Cách chạy lại

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-google-play-probe.txt
.\.venv\Scripts\python.exe scripts/probe_google_play_browser.py
```

Mặc định mở cửa sổ Chrome riêng và kiểm tra 3 trang metadata. Có thể dùng
`--headless`, `--metadata-limit 0` (chỉ chart), hoặc `--driver <path>` khi driver
khớp phiên bản Chrome. Headless chưa được xác minh trong lần thử này.

ChromeDriver người dùng cung cấp là 130.0.6723.69, Chrome đã cài là 153.0.8010.53.
Selenium Manager đã tìm driver tương thích 153.0.8010.52 và lưu cache dưới
`data/selenium-cache`; không ghi đè driver người dùng ở `D:\tool`.

Mỗi lần chạy lưu `report.json`, HTML sau render và PNG cho hai chart và các game
mẫu vào thư mục timestamp riêng dưới `data/google-play-browser-probe`.
Nếu không tải được chart hoặc rank không liên tiếp, ghi lỗi thay vì công bố chart.
Không đăng nhập hoặc bypass CAPTCHA; không dùng hồ sơ Chrome cá nhân.

## Bẫy đã phát hiện

Tab có thể đổi `aria-pressed` trước khi nội dung cập nhật. Bản thử đầu
`20260924T051823892753Z` đã bắt nhầm danh sách cũ khi đổi sang Grossing;
**không dùng phần Top Grossing của bản đó**. Script hiện chờ danh sách thay đổi
khi chuyển tab, rồi ổn định tối thiểu 2 giây trước khi thu.
Nếu hai bảng thực sự giống nhau hoàn toàn, script thận trọng báo timeout;
chưa có bằng chứng network để phân biệt trường hợp đó với nội dung chưa cập nhật.

## Giới hạn

Một lần chạy hoàn chỉnh sau sửa chưa chứng minh độ ổn định dài hạn. Thời gian
26 giây không phải thời gian crawl metadata toàn bộ 45–90 game. Chưa thử pagination,
chưa cam kết Top 100, chưa đối chiếu với Play Store trên điện thoại hoặc tài khoản khác.
Tham số thị trường là VN, dữ liệu ghi nhận là kết quả trang web công khai của request này.
Các vấn đề queue, migration, cache và lịch vẫn để giai đoạn sau như yêu cầu.
