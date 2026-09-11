# Báo Cáo Nghiệm Thu Chức Năng P1 & Sẵn Sàng Thử Nghiệm Lịch (Pilot Readiness)

- **Thời điểm nghiệm thu:** 2026-09-10
- **Phiên bản:** Phase 1 (iOS Casual Top 100 Free)
- **Môi trường xác thực:** Windows 10/11, Python 3.12.5, SQLite 3 (WAL mode), FastAPI TestClient

---

## 1. Kết Quả Kiểm Thử Toàn Diện (Verification Summary)

Toàn bộ các bộ kiểm tra tự động và tích hợp end-to-end đã hoàn thành với kết quả 100% đạt:

```text
======================= 63 passed in 4.93s =======================
Ruff: All checks passed! (0 errors, 0 warnings)
Pip:  No broken requirements found.
```

### Chi tiết các nhóm kiểm thử:
1. **Apple RSS Provider & HTTP Engine (`tests/test_apple.py`, `tests/test_http.py`):**
   - Phân tích Top 100 Free Casual Games (genre 7003), giữ nguyên thứ tự nguồn, kiểm tra tính hợp lệ của feed.
   - Thử nghiệm 3 lần retry với exponential backoff, nhận diện mã 429 và header `Retry-After`.
   - Giới hạn tốc độ tuần tự hóa qua `RequestGate` (4.0s request interval).
2. **Lưu trữ Bất biến & Metadata (`tests/test_storage.py`, `tests/test_metadata.py`):**
   - SQLite WAL mode, foreign keys bật, không ghi đè snapshot cũ khi gặp feed partial.
   - Raw response lưu trữ theo cơ chế Content-Addressed Storage (SHA256).
   - Cache metadata Lookup 24 giờ; liên kết metadata version với snapshot bất biến.
3. **Collector, Process Lock & CLI (`tests/test_jobs.py`, `tests/test_collection.py`, `tests/test_cli.py`):**
   - Khóa đơn tiến trình bằng file PID + create_time ngăn chạy đồng thời.
   - Tự động phục hồi trạng thái khi tiến trình cũ bị ngắt (`interrupted`).
   - Xử lý thị trường Timor-Leste (`tl`) là `unverified` một cách an toàn mà không gọi HTTP.
4. **Giao diện Web Localhost (`tests/test_web.py`, `tests/test_web_security.py`):**
   - 3 màn hình: Dữ liệu thị trường (`/`), Lịch sử & kích hoạt (`/runs`), Chi tiết ứng dụng (`/games/{app_id}`).
   - Bảo mật: TrustedHost (localhost/127.0.0.1), LocalOriginMiddleware chống CSRF từ bên ngoài, escaping script XSS.
   - Tải file raw evidence và xuất dữ liệu CSV.
5. **Khảo sát Lịch Chạy (`tests/test_survey.py`):**
   - Phân bổ 4 slot UTC (00:00, 06:00, 12:00, 18:00).
   - Ghi nhận `missed` khi quá cửa sổ khảo sát 30 phút, không backfill dữ liệu giả.
   - Xuất báo cáo khảo sát độ trễ và sự thay đổi dữ liệu nguồn.
6. **Sao lưu & Khôi phục (`tests/test_backup.py`):**
   - SQLite Online Backup API kết hợp kiểm tra SHA256 tất cả file raw responses.
   - Từ chối khôi phục khi phát hiện sai lệch hash hoặc thiếu file raw.
7. **Nghiệm thu Tích hợp End-to-End (`tests/test_p1_acceptance.py`):**
   - Mô phỏng toàn bộ luồng: HTTP Mock -> Collector -> DB/Raw -> Web UI -> CSV Export -> Snapshot History.

---

## 2. Ma Trận Nghiệm Thu Yêu Cầu (Requirements Traceability)

| Mã Yêu Cầu | Nội dung Yêu cầu | Trạng thái Nghiệm thu | Bằng chứng kiểm tra |
|---|---|---|---|
| **BA-R01** | Top 100 Free Casual Games từ Apple RSS cho 11 thị trường ASEAN + US | **ĐẠT (Passed)** | `tests/test_apple.py`, `tests/test_collection.py` |
| **BA-R02** | Metadata chi tiết từ Apple Lookup API (tối đa 20 IDs/request, cache 24h) | **ĐẠT (Passed)** | `tests/test_apple.py`, `tests/test_metadata.py` |
| **BA-R03** | Snapshot bất biến và Content-Addressed Storage cho raw evidence | **ĐẠT (Passed)** | `tests/test_storage.py`, `tests/test_backup.py` |
| **BA-R04** | Single-instance collector với process lock, retry/throttle, phục hồi ngắt quãng | **ĐẠT (Passed)** | `tests/test_jobs.py`, `tests/test_http.py` |
| **BA-R05** | Giao diện web cục bộ 3 màn hình, bind 127.0.0.1, phòng chống CSRF/Host spoofing | **ĐẠT (Passed)** | `tests/test_web.py`, `tests/test_web_security.py` |
| **BA-R06** | Khảo sát 4 slot UTC (00/06/12/18) và xuất báo cáo khảo sát 7 ngày | **ĐẠT (Passed)** | `tests/test_survey.py`, `casual_scout survey-report` |
| **BA-R07** | Backup & restore toàn vẹn có manifest và kiểm tra mã hash | **ĐẠT (Passed)** | `tests/test_backup.py` |
| **BA-R12** | Chi phí vận hành $0 (free-first, không dùng API trả phí) | **ĐẠT (Passed)** | Hoàn toàn sử dụng Apple RSS & Lookup công khai |

---

## 3. Kế Hoạch Thử Nghiệm Lịch Chạy (Survey Pilot Readiness)

1. **Trạng thái:** Toàn bộ code chức năng và công cụ đo đạc đã sẵn sàng.
2. **Quy trình kích hoạt khảo sát trên máy thật:**
   - Bước 1: Xem trước cấu hình Windows Task Scheduler:
     ```powershell
     .\scripts\Register-SurveyTask.ps1 -DataDir D:\Working\ASOL\tool\ASOL-market-research\data
     ```
   - Bước 2: Áp dụng đăng ký task:
     ```powershell
     .\scripts\Register-SurveyTask.ps1 -DataDir D:\Working\ASOL\tool\ASOL-market-research\data -Apply
     ```
   - Bước 3: Duy trì máy hoạt động trong tối thiểu 7 ngày để thu thập dữ liệu về độ ổn định và thời điểm cập nhật thực tế của Apple feed.
   - Bước 4: Xuất báo cáo khảo sát:
     ```powershell
     casual_scout survey-report --days 7 --data-dir .\data
     ```
3. **Quyết định chọn giờ Production (DEC-09):** Sẽ được đánh giá và chốt sau khi có đầy đủ dữ liệu thực tế từ báo cáo khảo sát 7 ngày.
