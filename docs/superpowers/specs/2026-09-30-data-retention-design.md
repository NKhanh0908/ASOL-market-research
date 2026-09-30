# Tự dọn dữ liệu Casual Scout sau 15 ngày

Ngày: 2026-09-30. Trạng thái: **Chờ người dùng review spec bằng văn bản; chưa triển khai hoặc xóa dữ liệu.**

## 1. Mục tiêu, thẩm quyền và ranh giới

Người dùng yêu cầu chỉ giữ bản ghi khoảng 10–15 ngày, tự xóa dữ liệu thu thập, phân tích, log và raw cũ trong kho Casual Scout; giữ shortlist. Quyết định sau cùng là gỡ hẳn AI nội bộ, nên không giữ đánh giá AI hoặc nguồn chỉ để phục vụ đánh giá AI.

Chọn **15 ngày lịch UTC, gồm hôm nay**, làm cấu hình v1 để đủ bối cảnh bản tin/lịch sử 7 ngày và có khoảng đệm. Đây là lựa chọn thiết kế trong khoảng người dùng yêu cầu, không phải con số người dùng đã xác nhận riêng trước khi viết spec. Không cung cấp tùy chỉnh 10/15 trong v1.

Liên quan: [MCP](2026-09-30-mcp-market-brief-design.md), [gỡ AI](2026-09-30-remove-internal-ai-design.md), [PRD](../../prd/2026-09-10-casual-game-market-research-PRD.md). Spec này hoàn thiện retention còn thiếu trong PRD và giới hạn thời gian lưu lịch sử/bằng chứng; tính bất biến vẫn áp dụng trong cửa sổ được giữ.

Phạm vi là database hoạt động, raw và log do ứng dụng quản lý trong data_dir. Không duyệt/xóa file ngoài data_dir, backup ngoài data_dir, tài liệu nghiên cứu trong repo, cấu hình/khóa cá nhân hoặc file không rõ ownership. Đây là chính sách dọn kho hoạt động, không phải cơ chế bảo đảm mọi bản sao dữ liệu trên máy đều bị xóa.

## 2. Phương án và phụ thuộc

Chọn dọn có nhận biết quan hệ DB và file raw, bằng dịch vụ maintenance riêng. Dùng SQLite transaction, manifest công việc dọn và bộ điều phối hiện có; không cần một nền tảng lưu trữ trả phí hoặc MCP bên ngoài. Xóa file theo mtime đơn thuần không biết raw còn được tham chiếu. Chỉ xóa rows DB để lại raw/log chiếm dung lượng. Không chọn hai phương án này.

**Điều kiện bắt buộc:** migration [gỡ AI](2026-09-30-remove-internal-ai-design.md) đã hoàn thành. Nếu phát hiện AI tables/evidence refs còn tồn tại, từ chối retention bằng lỗi hướng dẫn nâng cấp; không âm thầm bỏ qua dữ liệu AI hoặc tắt FK.

Dịch vụ dự kiến `operations/retention.py` lập tập ứng viên, áp dụng xóa DB và xử lý file; `storage/migrations_retention.py` quản lý schema/guard. MCP chỉ đọc dữ liệu; không cung cấp tool purge và không thực thi retention khi client gọi.

## 3. Cửa sổ và phạm vi xóa

Với ngày UTC hiện tại D: cutoff là 00:00 UTC ngày D-14. Giữ D-14..D; bản ghi có ngày/thời điểm trước cutoff là quá hạn. Ví dụ chạy 2026-09-30: giữ 2026-09-16..2026-09-30; xóa dữ liệu ngày 2026-09-15 trở về trước nếu không còn phụ thuộc hợp lệ.

| Loại dữ liệu | Căn cứ tuổi | Chính sách |
|---|---|---|
| Snapshots, entries, snapshot_metadata | `snapshots.observed_at` | Xóa snapshot quá hạn và con của nó |
| Daily analytics, canonical snapshot links | Ngày phân tích/canonical | Xóa trước cutoff; không để canonical trỏ snapshot đã xóa |
| Run/market run và request observations | Thời gian quan sát/kết thúc đã lưu | Chỉ xóa run đã đóng, quá hạn và không còn con được giữ |
| Android archive jobs/charts/entries | Thời gian chart/job đã lưu | Dọn theo phụ thuộc, chỉ job đã đóng; giữ lịch Android |
| Survey slots đã kết thúc | `slot_utc` | Xóa slot quá hạn; không xóa lịch/slot tương lai |
| Metadata versions | `fetched_at` | Xóa quá hạn khi không còn binding hoặc tham chiếu còn giữ |
| Raw responses và file content-addressed | `received_at`, tham chiếu DB | Xóa quá hạn chỉ khi không còn tham chiếu được giữ |
| App identity | Tham chiếu còn sống | Thu gom orphan quá hạn nếu không cần cho dữ liệu còn giữ hoặc shortlist |
| Log worker `run-<id>.log` | Run tương ứng đã đóng | Dọn log quá hạn; orphan log hợp lệ dùng mtime UTC nếu không có run |
| Shortlist | Không áp dụng | Giữ toàn bộ thông tin đã bookmark, notes, tags, trạng thái |
| Markets/charts definitions, schedules, settings, migration state | Không áp dụng | Giữ cấu hình; chỉ clear liên kết run đã hết hạn của lịch đã kết thúc nếu cần |

Metadata/raw dùng chung có thể cũ hơn 15 ngày nhưng vẫn được giữ khi snapshot trong cửa sổ còn tham chiếu. Đây là ngoại lệ toàn vẹn bắt buộc, không giữ nguyên snapshot lịch sử quá hạn chỉ vì cùng nội dung raw. Không kéo dài toàn bộ lịch sử của game chỉ vì game có trong shortlist. Khi dữ liệu chi tiết hết hạn, trang shortlist vẫn mở được từ thông tin bookmark và ghi rõ lịch sử nguồn đã hết hạn.

Không xóa job queued/running/pending hoặc file đang mở, dù đồng hồ cho thấy quá hạn. Recovery job chết dùng luồng hiện có trước maintenance; retention không tự kết luận một PID còn sống đã chết. Nếu timestamp hỏng/thiếu hoặc quan hệ không giải thích được, bỏ qua đối tượng đó và ghi mã lỗi để kiểm tra.

## 4. Điều phối và bất biến

Chạy một lượt dọn mỗi ngày UTC khi ứng dụng `serve` đang hoạt động; kiểm tra lượt đến hạn khi khởi động và trong tick điều phối. Chỉ ghi ngày thành công sau khi hoàn thành cả DB và file phase. Lúc bận, hoãn và thử lại ở tick sau. Sau thời gian tắt máy, chạy một lượt theo cutoff hiện tại, không chạy lại từng ngày đã lỡ. Nếu chỉ MCP đang chạy, retention không chạy; runbook nêu rõ điều này.

Có CLI quản trị `retention --dry-run` (đếm ứng viên và ước lượng byte) và `retention --apply` (áp dụng). Dry-run không bảo đảm số lượng khi apply sau đó: apply luôn kiểm tra lại trong vùng khóa. Hoạt động tự động và CLI dùng cùng logic/cùng khóa. Cấu hình bật retention và migration được kích hoạt trong đợt triển khai spec sau review, không trong lượt viết tài liệu.

Khóa maintenance phải phối hợp với **mọi đường ghi liên quan**: submit job, collection/raw put, analysis, legacy Android, backup/restore và migration. Claim maintenance và kiểm tra không có job hoạt động phải nguyên tử; một job mới không thể lọt vào sau kiểm tra idle. Backup giữ quyền đọc bảo vệ file raw suốt quá trình copy, không chỉ lúc snapshot DB. Shortlist mutation được retry/báo busy hữu hạn nếu xung đột.

Implementation plan phải liệt kê toàn bộ writer trước khi chọn/triển khai khóa dùng chung trên các tiến trình. Không coi check trạng thái job rồi xóa file không khóa là đủ. Worker bị chết được thu hồi khóa bằng kiểm tra owner PID + process birth hoặc cơ chế OS tương đương; không phá khóa chỉ vì timeout trong khi owner còn sống.

Schema hiện có trigger cấm xóa snapshots/entries/metadata/bindings. Migration thay đúng các DELETE guards bằng guard chỉ cho phép kết nối maintenance được cấp quyền trong transaction retention; UPDATE guards giữ nguyên. Quyền là theo connection, fail-closed, không là cờ toàn cục để lại sau crash. Có thể dùng hàm SQLite được đăng ký trên connection cho guard; thiếu hàm/không có quyền phải chặn DELETE. Không vô hiệu toàn bộ trigger hoặc FK trong luồng ứng dụng bình thường.

## 5. Xóa DB và file có khả năng tiếp tục sau lỗi

1. Giữ maintenance lock; lấy cutoff một lần từ clock UTC; dựng tập giữ/xóa theo quan hệ, không theo tên bảng độc lập.
2. Trong transaction: xóa con trước cha, clear nullable historical schedule refs khi hợp lệ, giữ các bản ghi đang tham chiếu dữ liệu còn sống. Tạo manifest GC chứa đúng raw hash/path và log ứng viên; xóa raw DB rows sau khi không còn FK/reference cần giữ. Foreign-key check phải đạt trước commit. Tắt quyền DELETE đặc biệt khi kết thúc transaction.
3. Sau commit, vẫn giữ khóa để không có writer/backup tái sử dụng file. Xác minh lại manifest, đường dẫn và trạng thái tham chiếu rồi xóa file đã duyệt. Ghi hoàn thành từng mục để có thể retry. Không xóa file trước commit DB.
4. Nếu crash sau commit: DB không trỏ file đã xóa, nhưng có thể còn file rác. Lượt sau xử lý manifest; nếu file/hash đã được writer mới dùng lại sau restart, hủy mục xóa đó. Nếu file đang bận hoặc xóa lỗi, giữ mục pending và báo số lượng.
5. Chỉ đánh dấu lượt thành công khi mọi mục có kết quả cuối. Manifest pending không bị dọn theo tuổi; log hoàn tất/summary maintenance giữ 15 ngày.

Raw orphan do crash trước khi ghi raw_responses: chỉ sweep trong thư mục raw content-addressed, tên hợp lệ, không có reference/manifest đang giữ và file mtime trước cutoff; cùng maintenance lock. File lạ bị bỏ qua. Raw chia sẻ với dữ liệu còn giữ không bao giờ bị xóa theo mtime.

Trước thao tác filesystem: resolve đường dẫn tuyệt đối, xác nhận bên trong đúng thư mục raw/log do ứng dụng quản lý, loại symlink/junction hoặc đường dẫn thoát root; không dựa riêng vào path đọc từ database. Không dùng recursive delete cho cả data_dir. Xóa tự động là xóa vĩnh viễn từng file quá hạn; không tạo thùng rác vô hạn làm mất mục tiêu kiểm soát dung lượng.

SQLite có thể giữ kích thước file sau DELETE và tái sử dụng trang trống. Không hứa giảm ngay kích thước DB, không chạy VACUUM hằng ngày. Runbook tách thao tác compact khi cần và khi idle. Retention đảm bảo xóa logic rows và thu hồi file raw/log được phép; không phải secure erase trên thiết bị lưu trữ.

## 6. Tác động đến MCP và lịch sử

MCP chỉ cho ngày đích trong 7 ngày gần nhất; chuỗi 7 ngày của ngày đích cũ nhất cần tối đa 13 ngày tính cả hôm nay, nằm trong cửa sổ 15 ngày. Nếu kho thiếu ngày do chưa thu thập/partial/lỗi, vẫn trả thiếu, không dùng retention làm lý do giả định dữ liệu đầy đủ.

Giữ read transaction của MCP nhất quán khi retention commit. Tool không trực tiếp stream file raw nên không phụ thuộc file đã được GC sau transaction; provenance là ID/hash đã quan sát. Lịch sử đã xóa không được bảo đảm mở lại lâu dài từ bản tin cũ. Bản tin AI ngoài ứng dụng muốn lưu lâu hơn sẽ thuộc chính sách của hệ thống ngoài ở đợt sau.

## 7. Nghiệm thu

1. Fixture tại 2026-09-30: ngày 16 được giữ, ngày 15 bị xóa đúng UTC; chạy lại cùng ngày không xóa thêm dữ liệu hợp lệ.
2. iOS, Android core, legacy archive, analytics, raw và log quá hạn đều được xử lý; shortlist/config/schedules còn nguyên nội dung.
3. Raw/metadata cũ nhưng còn được snapshot trong cửa sổ dùng vẫn tồn tại. Orphan hợp lệ quá hạn được dọn; file lạ/outside root/symlink không bị xóa.
4. Job active chặn dọn; race submit-vs-maintenance, raw put-vs-GC và backup-vs-GC không tạo dangling references/mất file backup.
5. Ordinary connection vẫn không DELETE/UPDATE snapshot bất biến; maintenance được phép xóa đúng tập; crash không để quyền xóa mở cho process sau.
6. Rollback DB, crash trước/sau commit, file đang bị giữ mở, retry manifest và hash được tái sử dụng đều có kết quả an toàn, đo được số pending/skipped.
7. FK/integrity checks đạt; sample snapshot/metadata/raw còn giữ đọc được và hash đúng; backup/restore sau dọn vẫn dùng được.
8. Dry-run không đổi DB/files; apply báo cutoff, counts theo nhóm, byte thực thu hồi, ngoại lệ shared references và các lỗi. Không báo thành công hoàn toàn khi còn pending file.
9. Tắt server vài ngày rồi bật lại dọn một lượt đúng cutoff; chỉ chạy MCP không kích hoạt dọn. Lịch collection hiện có không bị tự bật/tắt hoặc đổi giờ.
10. Kho chưa gỡ AI bị chặn với lỗi rõ. Fresh install và upgrade migration chạy lặp an toàn. Trang shortlist vẫn hiển thị bookmark khi lịch sử nguồn đã hết hạn.

## 8. Thứ tự bàn giao

Mỗi spec có implementation plan riêng. Có thể hoàn thành MCP trước; tiếp theo gỡ AI và cuối cùng retention. Trong đợt retention, báo cáo dry-run trên kho đích là bằng chứng review trước lần apply đầu tiên; chỉ chạy apply khi có quyền triển khai/xóa dữ liệu trên kho đó. Việc review tài liệu hiện tại không đồng nghĩa đã chạy purge trên dữ liệu thật.
