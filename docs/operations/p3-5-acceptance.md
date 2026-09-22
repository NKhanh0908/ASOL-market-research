# Báo cáo nghiệm thu kỹ thuật Phase 3.5

**Dự án:** Casual Scout — Monetization & Grossing Intelligence
**Ngày nghiệm thu:** 2026-09-22
**Trạng thái:** Hoàn thành xác minh tự động

## Phạm vi nghiệm thu

- Thu thập và lưu snapshot `topgrossingapplications` độc lập với Top Free.
- Lưu IAP metadata bất biến; phân loại `PURE_IAP`, `HYBRID`, `PURE_ADS`, và `PAID_PREMIUM`.
- Đối chiếu Free/Grossing, gắn cờ hiệu quả monetization và bổ sung Grossing Power vào Opportunity Radar v1.5.
- Hiển thị Top Grossing, monetization badges, IAP, CLI `collect --chart-type`, `trends --chart-type` và `stats radar --monetization`.
- Cung cấp `GET /api/charts/grossing?country=<code>&date=YYYY-MM-DD`, chỉ trả snapshot Grossing hoàn chỉnh của ngày yêu cầu.

## Bằng chứng kiểm thử

Lệnh chạy bằng Python trong `.venv`, với `--basetemp` cục bộ do thư mục temp mặc định của Windows bị chặn quyền truy cập:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-p35-reviewed-green -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check src\casual_scout\cli.py src\casual_scout\storage\repository.py src\casual_scout\web\app.py tests\test_analysis_service.py tests\test_cli_monetization.py tests\test_monetization_storage.py tests\test_p3_5_acceptance.py
```

Kết quả: **134 passed, 2 warnings** trong 29.72 giây; Ruff: **All checks passed** cho các file P3.5 đã sửa. Hai warning là deprecation warning từ `fastapi/starlette` TestClient, không phải lỗi ứng dụng.

## Acceptance test P3.5

`tests/test_p3_5_acceptance.py` xác nhận collector tạo snapshot Top Grossing hoàn chỉnh với raw evidence theo SHA-256. Test cũng xác nhận trọn luồng một game có mặt ở cả Top Free và Top Grossing: snapshot Grossing được truy xuất bằng API, analytics xác định `HYBRID`, và Radar nhận `grossing_rank` cùng 15 điểm Grossing Power.

## Giới hạn đã biết

Lint toàn repository vẫn có lỗi lịch sử ở các file P3 ngoài phạm vi thay đổi này. Chúng không chặn test suite; chỉ các file thay đổi trong đợt P3.5 được lint sạch trong lần nghiệm thu này.
