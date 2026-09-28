# Đặc Tả Kỹ Thuật 3: Tích Hợp CLI & Giao Diện Web Dashboard (CLI & UI/UX Integration)

- **Mã tài liệu:** `SPEC-AND-03`
- **Ngày tạo:** 2026-09-28
- **Trạng thái:** Approved
- **Tác giả:** NKhanh0908
- **Dự án:** Casual Scout — Multi-Platform Casual Games Market Research

---

## 1. Mục Tiêu & Trải Nghiệm Người Dùng

### 1.1. Mục tiêu
* Cung cấp trải nghiệm đồng nhất cho người dùng khi nghiên cứu thị trường game Casual trên cả 2 hệ điều hành **Apple iOS** và **Google Android**.
* Mở rộng giao diện dòng lệnh (CLI) với cờ `--platform` hỗ trợ thu thập và phân tích dữ liệu linh hoạt, có nhật ký tiến trình thời gian thực (Live Progress Logging).
* Tích hợp thanh chuyển đổi nền tảng **`[🍎 iOS]` | `[🤖 Android]`** trực tiếp trên Web Dashboard (`/dashboard`, `/data`), bổ sung hiển thị trực quan cột **Lượt tải (Installs)**.

---

## 2. Đặc Tả Giao Diện Dòng Lệnh (CLI Extensions)

### 2.1. Cập nhật lệnh `casual_scout collect`
Bổ sung cờ `--platform` (hoặc `-p`):

```powershell
casual_scout collect [--platform {all,ios,android}] [--markets COUNTRIES] [--chart-type {all,free,grossing}] [--data-dir PATH]
```

* `--platform`: Nền tảng cần cào:
  * `ios`: Chỉ cào 9 thị trường iOS qua Apple RSS API.
  * `android`: Chỉ cào 9 thị trường Android qua Google Play HTTP Engine.
  * `all`: Cào tuần tự cả iOS và Android (tổng cộng 18 luồng thị trường). Mặc định là `all` hoặc giữ nguyên `ios` theo ngữ cảnh.
* `--markets`: Danh sách mã quốc gia (mặc định: `vn,th,id,my,ph,sg,la,kh,us`).
* `--chart-type`: `all`, `free`, `grossing` (mặc định: `all`).

#### Trực quan hóa tiến trình (Live Progress Output):
```text
🚀 Bắt đầu thu thập dữ liệu [Platform: ANDROID] (Run ID: run-98234)
   Thị trường (9): VN, TH, ID, MY, PH, SG, LA, KH, US
   Loại chart: ALL (Top Free + Top Grossing)

[1/18] 🤖 VN — Top Free Casual: Đang tải bảng xếp hạng Google Play...
    ✓ Nhận 100 game
    ⏳ Làm giàu metadata & số lượt tải (24 game mới, 76 từ cache)...
    ✓ Hoàn tất VN (Top Free)

[2/18] 🤖 VN — Top Grossing Casual: Đang tải bảng xếp hạng Google Play...
    ✓ Nhận 100 game
    ✓ Toàn bộ metadata đã có trong cache
    ✓ Hoàn tất VN (Top Grossing)
...
✅ Hoàn thành thu thập Android (Run ID: run-98234) với trạng thái: SUCCEEDED
```

### 2.2. Cập nhật lệnh `casual_scout analyze` và `casual_scout stats radar`
* Bổ sung tham số `--platform`:
  ```powershell
  # Phân tích xu hướng Android ngày hôm nay:
  casual_scout analyze --platform android --data-dir .\data

  # Xem top cơ hội Opportunity Radar trên Android tại thị trường VN:
  casual_scout stats radar --platform android --country vn --limit 20 --data-dir .\data
  ```

---

## 3. Đặc Tả Giao Diện Web Dashboard

### 3.1. Thanh Điều Hướng & Bộ Lọc Nền Tảng (Platform Switcher)
Trên thanh điều hướng hoặc khu vực bộ lọc trên `/dashboard` và `/data`:
* Hiển thị nhóm nút chuyển đổi:
  * **`[ 🍎 Apple iOS ]`**
  * **`[ 🤖 Google Android ]`**
* Trạng thái nền tảng được duy trì qua URL query param `?platform=android` hoặc cookie phiên làm việc.

```
+-----------------------------------------------------------------------------------+
|  Casual Scout  |  Dashboard   Data   Shortlist   Runs   [🍎 iOS] [🤖 Android]     |
+-----------------------------------------------------------------------------------+
|  Thị trường: [ Việt Nam (VN) v ]   Bảng xếp hạng: [ 🆓 Top Free ] [ 💰 Top Grossing ]|
+-----------------------------------------------------------------------------------+
```

### 3.2. Cột Lượt Tải Cài Đặt (Installs) trên Bảng Dữ Liệu (`/data`)
Khi xem dữ liệu Android, bảng dữ liệu mở rộng thêm cột **Lượt tải (Installs)** với các huy hiệu phân cấp trực quan:

| Lượt cài đặt | Huy hiệu hiển thị | Ý nghĩa thị trường |
| :--- | :--- | :--- |
| $\ge 50,000,000+$ | `💎 50M+` *(Xanh dương/Tím neon)* | Siêu phẩm toàn cầu (Global Hit) |
| $10,000,000+ - 49,000,000+$ | `🔥 10M+` *(Cam/Đỏ)* | Game cực kỳ phổ biến |
| $1,000,000+ - 9,999,999+$ | `⚡ 1M+` *(Xanh lá cây)* | Game đang tăng trưởng mạnh |
| $100,000+ - 999,999+$ | `🌱 100K+` *(Xám bạc)* | Game mới nổi / Tiềm năng ngách |
| $< 100,000+$ | `👀 <100K` *(Mờ)* | Game mới ra mắt |

### 3.3. Nút "Crawl Ngay" thông minh trên Web
* Nút **"Crawl ngay"** tại Dashboard và Data tự động nhận diện tab nền tảng đang chọn để kích hoạt tác vụ cào tương ứng:
  * Đang ở tab iOS -> Kích hoạt cào 9 thị trường iOS.
  * Đang ở tab Android -> Kích hoạt cào 9 thị trường Android qua Google Play HTTP Engine.

### 3.4. Trang Chi Tiết Game (`/games/{app_id}`)
* Hỗ trợ định dạng `app_id` là mã số Apple (iOS) hoặc chuỗi package Java (Android, ví dụ `com.king.candycrushsaga`).
* Hiển thị biểu tượng nhận diện nền tảng (`Google Play Store` kèm link ngoài mở store chính thức).
* Hiển thị khối thống kê: **Tổng lượt tải (Installs)**, Số sao đánh giá (★ 4.5 / 85,000 votes).
* Biểu đồ biến động thứ hạng (Top Free & Top Grossing) 14 ngày qua.
* Nhãn nhận diện Cơ chế Gameplay (Mechanic) và Thể loại phụ (Subgenre) bóc tách tự động bởi Taxonomy Engine.

---

## 4. API Endpoints Đặc Tả

Hệ thống API RESTful hỗ trợ bổ sung tham số `platform`:

1. `GET /api/data?platform=android&country=vn&feed_type=top-free&date=2026-09-28`
   - Trả về danh sách Top 100 game Android kèm trường `installs`, `min_installs`, `free_rank`, `grossing_rank`.
2. `GET /api/stats/radar?platform=android&country=vn`
   - Trả về danh sách xếp hạng Opportunity Radar v1.5 cho các game Android.
3. `POST /api/crawl`
   - Body: `{"platform": "android", "markets": ["vn", "th", "us"], "chart_type": "all"}`
   - Kích hoạt tiến trình cào dữ liệu ngầm cho Android.

---

## 5. Tiêu Chí Nghiệm Thu (Acceptance Criteria)

- [ ] Lệnh CLI `casual_scout collect --platform android` thực thi trơn tru, hiển thị đầy đủ tiến trình từng thị trường.
- [ ] Giao diện Web `/dashboard` và `/data` chuyển đổi mượt mà giữa `[🍎 iOS]` và `[🤖 Android]`.
- [ ] Bảng xếp hạng Android hiển thị chuẩn xác huy hiệu Lượt tải (`Installs`) và phân loại kiếm tiền (`Monetization Model`).
- [ ] Trang chi tiết game `/games/{package}` hiển thị đúng thông tin package, biểu đồ thứ hạng và link store Google Play.
- [ ] Tất cả các API RESTful phản hồi đúng mã HTTP 200 và dữ liệu JSON theo từng `platform`.
