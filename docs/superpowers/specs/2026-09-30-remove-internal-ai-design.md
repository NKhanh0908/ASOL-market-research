# Gỡ chức năng đánh giá AI nội bộ

Ngày: 2026-09-30. Trạng thái: **Chờ người dùng review spec bằng văn bản; chưa triển khai.**

## 1. Quyết định sản phẩm

Người dùng đã chốt “Bỏ hẳn” đánh giá AI trong Casual Scout. Sản phẩm giữ việc thu thập, phân tích theo quy tắc, thống kê, shortlist và MCP dữ liệu. AI bên ngoài cùng Zalo/Telegram là giai đoạn sau, không thuộc lần gỡ này.

Quyết định này thay thế phạm vi P4/M5/US-004/DEC-08 và BA-R10/11 về AI nội bộ trong [PRD](../../prd/2026-09-10-casual-game-market-research-PRD.md). Không xóa lịch sử tài liệu đã phê duyệt; bổ sung ghi chú superseded và trạng thái mới khi triển khai. P1–P3 và các nguyên tắc bằng chứng tiếp tục có hiệu lực.

Liên quan: [MCP bản tin](2026-09-30-mcp-market-brief-design.md), [retention 15 ngày](2026-09-30-data-retention-design.md). Gỡ AI phải hoàn tất trước khi bật retention để loại bỏ liên kết AI giữ snapshot/metadata quá hạn.

## 2. Phương án

Chọn gỡ hoàn toàn runtime và schema AI bằng migration có phiên bản. Chỉ ẩn UI vẫn giữ worker, cấu hình và ràng buộc dữ liệu; tắt provider vẫn cần bảo trì phân hệ người dùng đã bỏ. Hai phương án đó không đáp ứng quyết định “Bỏ hẳn”.

Không cần dịch vụ/thư viện mới: dùng migration SQLite và cơ chế khởi động đang có. Đây là thay đổi loại bỏ thành phần, không xây bộ đánh giá thay thế.

## 3. Phạm vi loại bỏ

| Khu vực | Thay đổi |
|---|---|
| `src/casual_scout/ai/` | Gỡ provider Gemini, cấu hình, prompt/output, evidence builder, engine, worker, storage/schema AI |
| `web/ai.py`, templates/static recommendations | Gỡ router/trang/form/progress và các liên kết UI tới đánh giá AI |
| `web/app.py` | Gỡ tham số/dependency AI, khởi tạo engine/store/worker và recover/close worker khỏi lifespan |
| `cli.py` | Gỡ tải runtime AI khi `serve`; giữ lệnh thu thập/phân tích/thống kê/shortlist |
| `Repository.initialize()` | Ngừng đọc/tạo AI schema; áp dụng migration retirement một lần |
| Tests/scripts/config docs | Gỡ kiểm thử và script chỉ phục vụ AI; sửa kiểm thử tích hợp còn dùng AI mock; loại hướng dẫn cấu hình AI khỏi luồng cài đặt hiện hành |

Không đồng nhất “phân tích” với “AI”: `analysis/delta.py`, `signals.py`, taxonomy, thống kê, noteworthy và logic bản tin deterministic vẫn thuộc sản phẩm. Chỉ gỡ dependency thực sự dành riêng AI; kiểm tra usage toàn repo trước khi bỏ dependency hoặc fixture.

Các URL AI cũ trả 404 sau nâng cấp, không còn khả năng submit/rerun. Giao diện không còn nút/tab/đường dẫn đánh giá AI. Khởi động ứng dụng không đọc biến môi trường khóa Gemini hoặc gọi mạng AI. Không tự sửa/xóa khóa trong cấu hình cá nhân ngoài repo.

## 4. Dữ liệu và migration

Gỡ toàn bộ dữ liệu đánh giá AI trong database hoạt động khi chạy migration retirement; không lưu ngoại lệ tham chiếu AI cho retention. Bao gồm kết quả, đầu vào, usage/cost, evidence refs và seals. Shortlist được giữ nguyên kể cả notes/tags/rank_at_bookmark. Điểm AI hoặc score lịch sử nằm trong bảng khác không là lý do xóa dữ liệu người dùng; chỉ xóa bảng/cột khi có ownership rõ là AI và nằm trong danh sách migration.

Schema hiện tại có trigger cấm DELETE/UPDATE AI và foreign key từ `ai_run_evidence` tới snapshots/metadata. Migration phải:

1. Chỉ chạy lúc ứng dụng cũ/worker đã dừng; nếu còn AI run queued/running thì từ chối nâng cấp và chỉ rõ run cần xử lý. Không giết tiến trình hoặc đổi trạng thái âm thầm.
2. Trong transaction có FK enforcement: gỡ đúng các trigger/index AI thuộc schema cũ; bỏ bảng phụ thuộc `ai_run_evidence_seals`, `ai_run_evidence`, rồi `ai_evaluation_runs`. Không tắt FK để che lỗi.
3. Ghi migration version trong cùng transaction. Nếu lỗi, rollback toàn bộ. Chạy lại không lỗi và không tạo lại bảng AI.
4. Xác minh foreign_key_check và khả năng đọc dữ liệu iOS/Android, shortlist sau migration.

Nâng cấp làm mất dữ liệu AI trong kho hoạt động. Runbook hướng dẫn dùng backup hiện có trước nâng cấp nếu cần khả năng quay lại; migration không tự tạo vô hạn bản sao AI hoặc bí mật. Backup do người vận hành giữ ở ngoài data_dir không bị sửa. Muốn rollback bản ứng dụng cũ cần restore backup tương ứng, không tự tái tạo dữ liệu AI đã xóa.

Bản fresh install không tạo AI tables. Backup cũ có AI tables khi restore phải qua migration retirement trước khi serve với phiên bản mới. Quyền chạy migration ở bước triển khai tách khỏi việc viết spec; lượt viết spec này không chạm DB thật.

## 5. Bảo toàn thay đổi đang làm

Tại thời điểm viết spec, working tree có thay đổi chưa commit ở `ai/gemini.py`, `ai/output.py`, `ai/settings.py`, `tests/test_ai_gemini.py`, `tests/test_ai_output.py`. Trước triển khai, ghi lại diff và bảo toàn trong checkpoint/worktree/patch nội bộ có thể khôi phục; không reset hoặc xóa các thay đổi đó trong lúc gỡ tính năng. Không gộp chúng vào commit tài liệu. Khi diff có dữ liệu nhạy cảm, không xuất ra báo cáo hoặc đẩy ra remote.

## 6. Lỗi, xác minh và bàn giao

- Migration chạy trên fixture có evaluations/evidence refs: AI tables/triggers biến mất; số liệu chart, metadata, analytics và shortlist giữ nguyên.
- Fixture fresh install, upgrade, chạy migration hai lần và rollback khi lỗi giữa transaction đều đạt.
- Run active chặn migration với lỗi rõ; không tạo schema nửa cũ nửa mới.
- `serve`, collection, analysis, dashboard, game detail, shortlist và API dữ liệu hoạt động sau gỡ. Các đường dẫn AI trả 404 và không còn UI gọi chúng.
- Không còn import runtime tới package đã xóa hoặc đọc AI schema từ initialization.
- Kiểm tra giữ nguyên nội dung shortlist và tính toàn vẹn FK; regression tập trung lifecycle web/CLI/storage và các nghiệp vụ còn lại.
- README/runbook/PRD ghi phạm vi sản phẩm mới, link tới quyết định này. Spec/plan AI cũ là tài liệu lịch sử, được đánh dấu superseded thay vì xóa mất truy vết.

Tiêu chí hoàn tất: ứng dụng chạy không cần subsystem AI, dữ liệu AI đã được loại bằng migration có kiểm chứng và retention không còn bị AI foreign keys chặn. Chưa bao gồm triển khai AI bên ngoài hoặc kênh gửi.
