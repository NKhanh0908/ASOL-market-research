# Android live batches — đánh giá triển khai 24/09/2026

## Kết quả thực tế

Web thử: `http://127.0.0.1:8002/android`. Cho phép thêm host LAN `192.168.1.4`;
HTTP request tới `http://192.168.1.4:8002/android` trả 200 từ máy phát triển.
Chưa xác minh kết nối thực sự từ điện thoại hoặc cấu hình firewall của cổng 8002.

| Chỉ số | Lượt đầu, không cache | Lượt hai, có cache |
|---|---:|---:|
| Run ID | `63a9380f-bbfa-41b7-811b-0b35b57f1ad0` | `c501183c-076e-4adf-b59a-901a417f3e42` |
| Top Free | 45 game | 45 game |
| Top Grossing | 45 game | 45 game |
| Game khác nhau | 82 | 82 |
| Metadata hoàn tất | 82 mới | 82 cached |
| Batch đã lưu | 17 | 17 |
| Thời gian cả run | 333.13 giây | 21.70 giây |
| Trạng thái | succeeded | succeeded |

Mốc tính từ dispatch của lượt đầu: Top Free commit sau 10.62 giây, Top Grossing
sau 21.07 giây, phân tích batch đầu sau 40.32 giây. Trang polling mỗi 2 giây nên
độ trễ hiển thị thêm khoảng 0–2 giây cộng thời gian HTTP/render; đây không phải SSE.
Đã quan sát API ở mốc 5/82, 60/82 và giao diện Chrome ở 35/82 trong khi run
còn running. Không phải chờ 333 giây mới xem được kết quả. 82 game đều có developer.

Đây là đo trên máy hiện tại và hai lượt chạy, không phải cam kết độ trễ/uptime dài hạn.
Lịch Android vẫn tắt. Không có dữ liệu doanh thu bằng tiền hoặc lịch sử Android
ngày trước, nên delta hiện là chưa có mốc so sánh; không dùng mock iOS làm baseline.

## Phạm vi đã làm

- Worker Chrome headless riêng, lấy bảng xếp hạng và lưu kết quả từng bảng sớm.
- Batch 5 package: metadata + phân loại cơ chế/độ tin cậy + tín hiệu kiếm tiền;
  delta 1 ngày cho mỗi chart dùng đúng ngày quan sát Việt Nam khi có baseline.
- Các trạng thái pending/complete/cached/failed theo game; processed tính cả game
  đã thử nhưng lỗi. Lỗi một chart vẫn giữ chart kia. Raw HTML, PNG và manifest SHA-256.
- Cache metadata 48h, giữ timestamp nguồn; rank luôn lấy mới.
- Queue Android persistent, chung core runs và collector lock với iOS; manual
  duplicate khi đang chờ/chạy trả lại cùng job, có thể chạy nhiều lần trong ngày.
- Daily 07:00 mặc định tắt; iOS được scheduler xét trước, rồi Android chờ core run
  terminal; pending đã tạo có thể tiếp tục sau restart, không tạo bù slot daily đã lỡ.
- Giao diện riêng `/android`: 2 bảng, lịch sử run, counters, progress, lỗi, mô tả,
  developer, rating, delta, cơ chế, model. Nội dung crawl được render bằng textContent.
- 390px mobile: scrollWidth = viewport = 390, không tràn ngang. Chuyển Top Grossing
  hiển thị Coin Master đầu bảng. Browser console không có lỗi nghiêm trọng.

## Kiểm chứng

- `tests/test_android_batches.py`: transactions, queue, cache TTL, không copy rank từ
  cache, quan sát qua nửa đêm, worker chết, launcher lỗi và scheduler race.
- `tests/test_android_worker_live.py`: fake chỉ ở biên provider; thực sự đọc database
  từ kết nối khác khi metadata game thứ 6 chưa xong, xác nhận batch 1 đã hiện;
  lỗi metadata và lỗi một chart không làm mất dữ liệu.
- `tests/test_android_web_live.py`: API đang run, CSRF, cấu hình lịch, LAN host cụ thể,
  giữ lịch một lần iOS. Hồi quy toàn dự án chạy trước bàn giao.
- `scripts/check_android_live_ui.py`: browser QA với trang thật; artifacts tại
  `data/android-ui-check/` (các lần chạy ghi đè ảnh gần nhất).
- Review độc lập tìm được hai lỗi quan trọng: tranh chấp schedule nhận nhầm run
  Android và dùng ngày enqueue làm baseline. Đã thêm regression đỏ, sửa và chạy xanh;
  lượt review lại không còn vấn đề quan trọng được báo.
- Kiểm chứng cuối: **161 passed**, hai cảnh báo deprecation từ dependency
  FastAPI/Starlette; Ruff sạch trên các module Android và điểm tích hợp đã sửa;
  `git diff --check` không báo lỗi whitespace.

## Quyết định thiết kế và đánh giá

Skill kiến trúc dẫn tới storage Android dạng bảng bổ sung trong cùng SQLite, thay
vì sửa toàn bộ khóa analytics iOS trong lượt triển khai live này. Vì vậy Android
chưa đi vào Opportunity Radar, shortlist hay biểu đồ lịch sử của dashboard iOS.
Trang Android không gắn nhãn NEW_ENTRY/STEADY khi không đủ baseline hoặc độ sâu
chart khác nhau. Taxonomy là suy luận từ tên/mô tả ngắn, không phải kiểm chứng gameplay.

Đánh giá: đủ dùng để thử thủ công và quan sát tiến độ batch. Cần theo dõi nhiều
ngày trước khi coi cron là ổn định lâu dài. Driver phụ thuộc Chrome/khả năng tải
driver tương thích. Trang Google thay đổi markup vẫn có thể làm crawl lỗi.
Chuyển tab hiện chờ danh sách thay đổi và ổn định; nếu hai bảng thực sự giống nhau
hoàn toàn thì báo timeout thận trọng, chưa phân biệt bằng response network.

Run có ngân sách 15 phút kiểm tra giữa từng app; request đang thực hiện có timeout
riêng, nên đây không phải hard-kill đúng giây thứ 900. Khi gián đoạn, giữ batch đã
commit; lượt mới tận dụng cache, không tự tiếp tục một nửa batch chưa commit.
Mỗi run lưu HTML/PNG khá lớn; chưa có chính sách tự xóa evidence.

## Vận hành

Cài `.[android]`, mở web rồi dùng nút và checkbox. Các worker entry point là chi tiết
nội bộ; người vận hành không cần CLI crawl. Đường dẫn file code:
`src/casual_scout/android/`, `src/casual_scout/web/android.py`,
`src/casual_scout/web/templates/android.html`, `src/casual_scout/web/static/android.*`.
Script probe trước đó vẫn giữ trong `scripts/`. Chưa commit các thay đổi.
