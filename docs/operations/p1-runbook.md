# Casual Scout — iOS P1 Operational Runbook (Windows)

Tài liệu hướng dẫn vận hành công cụ khảo sát thị trường Casual Game trên iOS (P1) chạy cục bộ trên môi trường Windows.

---

## 1. Môi trường & Cài đặt

### Yêu cầu hệ thống
- Hệ điều hành: **Windows 10 / 11 / Server**
- Python: **Python 3.12+**
- Quyền: User thông thường (không yêu cầu Administrator cho hoạt động hàng ngày)
- Mạng: Kết nối Internet truy cập được iTunes / Apple RSS API (`itunes.apple.com`)

### Cài đặt ban đầu từ Lockfile
Mở PowerShell trong thư mục gốc của dự án (`D:\Working\ASOL\tool\ASOL-market-research`):

```powershell
# 1. Khởi tạo môi trường ảo
python -m venv .venv

# 2. Kích hoạt môi trường ảo
.\.venv\Scripts\Activate.ps1

# 3. Nâng cấp pip và cài đặt từ requirements.lock.txt (hoặc editable package)
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e .

# 4. Kiểm tra cài đặt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m casual_scout --help
```

---

## 2. Khởi tạo Kho Dữ liệu Cục bộ

Khởi tạo cấu trúc bảng SQLite và thư mục lưu trữ raw evidence (`data/casual-scout.sqlite3` và `data/raw/`):

```powershell
# Khởi tạo data directory
.\.venv\Scripts\python.exe -m casual_scout init --data-dir .\data
```

> **Lưu ý:**
> Giữ `data_dir` tách biệt khỏi thư mục evidence khảo sát ban đầu (`docs/core/research/evidence/`). Không tạo dữ liệu backup lồng vào trong thư mục `data_dir`.

---

## 3. Thu thập Dữ liệu (CLI & Background Process)

### Thu thập thử nghiệm một thị trường (Vietnam - vn)
```powershell
.\.venv\Scripts\python.exe -m casual_scout collect --markets vn --data-dir .\data
```

### Thu thập toàn bộ 11 thị trường khả dụng (ASEAN 10 + US)
```powershell
.\.venv\Scripts\python.exe -m casual_scout collect --markets vn,us,sg,th,id,my,ph,kh,la,mm,bn --data-dir .\data
```

### Thu thập bỏ qua bước làm giàu metadata (enrichment=False)
```powershell
.\.venv\Scripts\python.exe -m casual_scout collect --markets vn --no-enrich --data-dir .\data
```

---

## 4. Chạy Giao diện Web Cục bộ (Localhost:8000)

Giao diện web chỉ bind trên `127.0.0.1:8000` phục vụ người dùng nội bộ:

```powershell
# Khởi động trực tiếp
.\.venv\Scripts\python.exe -m casual_scout serve --host 127.0.0.1 --port 8000 --data-dir .\data

# Hoặc khởi động nền bằng PowerShell script
.\scripts\Start-Web.ps1 -Port 8000 -DataDir .\data
```

Truy cập trên trình duyệt:
- **Dữ liệu mới nhất & Tải CSV:** `http://127.0.0.1:8000/`
- **Lịch sử & Kích hoạt lượt chạy:** `http://127.0.0.1:8000/runs`
- **Chi tiết ứng dụng:** `http://127.0.0.1:8000/games/{app_id}?country=vn`

---

## 5. Khảo sát Lịch Chạy (Survey & Task Scheduler)

P1 không chọn cố định một giờ production mà sử dụng cơ chế khảo sát 4 slot UTC (`00:00`, `06:00`, `12:00`, `18:00`) tối thiểu 7 ngày.

### 5.1 Đăng ký Lịch Khảo sát trên Windows Task Scheduler
Script `Register-SurveyTask.ps1` mặc định **chỉ preview XML** để đảm bảo an toàn. Chỉ đăng ký khi truyền tham số `-Apply`.

```powershell
# 1. Preview cấu hình XML của Scheduled Task
.\scripts\Register-SurveyTask.ps1 -DataDir D:\Working\ASOL\tool\ASOL-market-research\data

# 2. Đăng ký Scheduled Task vào hệ thống
.\scripts\Register-SurveyTask.ps1 -DataDir D:\Working\ASOL\tool\ASOL-market-research\data -Apply
```

Đặc điểm của task `ASOL-Casual-P1-Survey`:
- Chạy dưới tài khoản hiện tại, không nâng quyền Administrator, không lưu mật khẩu.
- Lặp mỗi 6 giờ (`PT6H`), `StartWhenAvailable = true` (chạy bù khi mở máy lại), `MultipleInstances = IgnoreNew`, `WakeToRun = false`.
- Chạy nền ẩn (`WindowStyle Hidden`).

### 5.2 Gỡ bỏ Task Khảo sát (Unregister)
Chỉ gỡ bỏ task có tên cố định `ASOL-Casual-P1-Survey`, **tuyệt đối không xóa dữ liệu** trong thư mục data:
```powershell
Unregister-ScheduledTask -TaskName 'ASOL-Casual-P1-Survey' -Confirm:$false
```

### 5.3 Xuất Báo cáo Khảo sát (Survey Report)
```powershell
# Báo cáo 7 ngày gần nhất dạng JSON & Markdown
.\.venv\Scripts\python.exe -m casual_scout survey-report --days 7 --data-dir .\data
```

---

## 6. Sao lưu và Khôi phục (Backup & Restore)

### 6.1 Sao lưu dữ liệu (Backup)
Quy trình backup sử dụng SQLite Online Backup API kết hợp kiểm tra SHA256 tất cả file raw responses được tham chiếu:

```powershell
# Tạo bản sao lưu vào thư mục bên ngoài data_dir
.\.venv\Scripts\python.exe -m casual_scout backup --data-dir .\data --destination D:\Backups\casual-scout-20260910
```

Cấu trúc bản sao lưu:
```text
D:\Backups\casual-scout-20260910\
├── casual-scout.sqlite3
├── manifest.json
└── raw/
    └── 53/
        └── 53e81e17c879fc864ab31105295e38d35fa97181335274816692fd84c29b1bda
```

### 6.2 Khôi phục dữ liệu (Restore)
Quy trình restore xác thực mã hash của từng file raw theo `manifest.json` trước khi khôi phục:

```powershell
# Khôi phục từ bản sao lưu sang thư mục đích
.\.venv\Scripts\python.exe -m casual_scout restore --manifest D:\Backups\casual-scout-20260910\manifest.json --data-dir .\data-restored
```

---

## 7. Xử lý Sự cố & Giới hạn P1

### 1. Máy tính sleep hoặc tắt nguồn trong slot khảo sát
- Hệ thống ghi nhận trạng thái `missed` cho slot đó trong bảng `survey_slots`.
- Khi máy bật lại, hệ thống chỉ chạy một lượt catch-up duy nhất với `observed_at` là thời gian thực, **không backfill dữ liệu giả** cho slot cũ.

### 2. Xử lý khi collector bị gián đoạn (Crash / Kill)
- Lượt chạy bị ngắt sẽ có trạng thái `interrupted`.
- File snapshot cũ và raw files đã commit trước đó được bảo toàn nguyên vẹn (bất biến).
- Khi chạy lại với cùng `request_key`, hệ thống sẽ bắt đầu lượt chạy mới an toàn mà không làm hỏng khóa tiến trình.

### 3. Thị trường Timor-Leste (TL)
- Nguồn RSS Apple cho Timor-Leste (`tl`) chưa được Apple hỗ trợ chính thức feed Casual 7003 và được đánh dấu `unverified` trong danh mục thị trường. Hệ thống ghi nhận rõ ràng lý do và không gây gián đoạn các thị trường khác.

### 4. Kiểm tra dung lượng đĩa (Disk Usage)
Mỗi snapshot Top 100 chiếm khoảng 150 KB raw JSON. Để kiểm tra dung lượng thư mục dữ liệu:
```powershell
Get-ChildItem -Path .\data -Recurse | Measure-Object -Property Length -Sum
```
