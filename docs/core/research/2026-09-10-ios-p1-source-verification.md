# Kiểm chứng nguồn iOS cho P1

Ngày: 2026-09-10. Phạm vi: kiểm chứng đọc nguồn công khai, không triển khai ứng dụng. Căn cứ: PRD-CASUAL-MKT-001 v2.2, DEC-01–09. Người dùng xác nhận chạy trên máy Windows hiện tại, dùng cá nhân trước.

## Kết luận

Có thể lấy trực tiếp **Top Free Casual**, không cần suy danh sách Casual từ Top Apps. Lượt kiểm tra trả 100 game ở 10 nước ASEAN và US. Timor-Leste nằm trong phạm vi cần theo dõi nhưng endpoint Games đã thử trả HTTP 400; chưa chứng minh có feed khả dụng tại thị trường này.

Khuyến nghị nguồn đầu tiên: RSS Apple theo quốc gia, genre 7003 được phản hồi hiện tại gọi là Casual; Lookup bổ sung metadata. Chưa cần thư viện scraper hoặc crawl HTML cho phần dữ liệu đã kiểm chứng. Đây là khuyến nghị thiết kế, không phải cam kết nguồn luôn hoạt động hay bao phủ mọi casual game.

## Phép thử và bằng chứng

Đọc endpoint bằng HTTP GET từ máy Windows, không API key và không đăng nhập. Lượt trong sandbox gặp lỗi kết nối; chạy ngoài sandbox sau cấp quyền đã nhận payload. Các mẫu giữ ở [thư mục evidence](evidence/2026-09-10-ios-p1/). Đây là các lượt thử một thời điểm, không phải benchmark theo giờ.

| Phép thử | Kết quả | Bằng chứng |
|---|---|---|
| Games, genre=6014, limit=200 | 11 thị trường trả HTTP 200 và 100 ID khác nhau mỗi thị trường; TL trả 400 | [chart-probe-results.json](evidence/2026-09-10-ios-p1/chart-probe-results.json) |
| Casual, genre=7003, limit=100 | 11/11 thị trường trả HTTP 200, title “Top Free Applications in Casual”, 100 ID khác nhau/thị trường, self link đúng quốc gia và genre | [casual-probe-results.json](evidence/2026-09-10-ios-p1/casual-probe-results.json) |
| Lookup hai game từ Games chart mỗi thị trường | 11/11 lượt trả đủ hai ID, có mô tả và rating | [lookup-probe-results.json](evidence/2026-09-10-ios-p1/lookup-probe-results.json) |
| Lookup 20 game đầu Casual tại VN và US | Mỗi lượt đủ 20/20 ID; cả 40 bản ghi có genreId 7003 | [lookup-batch20-results.json](evidence/2026-09-10-ios-p1/lookup-batch20-results.json) |
| Marketing Tools Top Free Apps VN, limit=10 | HTTP 200, title Top Free Apps, 10 kết quả; không là Casual chart | Quan sát thử đầu phiên; không lưu payload của lượt này |

URL mẫu đã kiểm chứng:

```text
https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json
https://itunes.apple.com/us/rss/topfreeapplications/limit=100/genre=7003/json
https://itunes.apple.com/lookup?id=<id1>,<id2>&country=vn
```

RSS không có trường rank số riêng trong các entry đã đọc; vị trí 1-based của entry trong feed được dùng làm thứ hạng nguồn, cần lưu nguyên thứ tự trước khi làm giàu metadata. Không dùng thứ tự trả về của Lookup để xác định rank.

## Bao phủ thị trường

ASEAN hiện có 11 thành viên; Timor-Leste gia nhập ngày 26-10-2025 theo [ASEAN](https://asean.org/member-states/). VN đã nằm trong ASEAN nên không nhân đôi.

| Quốc gia | Mã | Games yêu cầu 200 | Casual yêu cầu 100 | Lookup mẫu |
|---|---|---|---|---|
| Việt Nam | vn | 100 | 100 | 2/2; lô Casual 20/20 |
| Hoa Kỳ | us | 100 | 100 | 2/2; lô Casual 20/20 |
| Brunei | bn | 100 | 100 | 2/2 |
| Campuchia | kh | 100 | 100 | 2/2 |
| Indonesia | id | 100 | 100 | 2/2 |
| Lào | la | 100 | 100 | 2/2 |
| Malaysia | my | 100 | 100 | 2/2 |
| Myanmar | mm | 100 | 100 | 2/2 |
| Philippines | ph | 100 | 100 | 2/2 |
| Singapore | sg | 100 | 100 | 2/2 |
| Thái Lan | th | 100 | 100 | 2/2 |
| Timor-Leste | tl | HTTP 400 | Chưa thử riêng | Chưa thử |

Đây là **11/12 thị trường mục tiêu** có feed đã xác minh (10/11 ASEAN + US). Không được báo “100% ASEAN”. [Apple Media Services](https://support.apple.com/en-us/118205) hiện liệt kê App Store cho Myanmar; tìm Timor trong trang không có kết quả. Điều này cộng với HTTP 400 chỉ đủ kết luận chưa xác nhận được nguồn TL, không chứng minh nguồn sẽ không bao giờ tồn tại.

## Dữ liệu và thư viện

Payload Casual tổng cộng 1.100 dòng theo thị trường, tương ứng 325 App ID khác nhau trong lượt đo. Cùng game ở nhiều quốc gia phải giữ từng bản ghi thị trường. Tổng response body của 11 feed khoảng 4,10 MB; thời gian đo mỗi lượt gồm nhận/parse/lưu mẫu khoảng 1.747–2.105 ms. Không suy thành SLA, giờ tối ưu hay giới hạn tốc độ.

Metadata thử có ID, tên, URL store, mô tả, genreIds/genres, rating. Ví dụ VN: Lookup trả genreId 7003 với nhãn Casual, 7012 với nhãn Puzzle. Đây là taxonomy do nguồn cung cấp, không phải phân loại mechanic do AI xác nhận. Dữ liệu thử không cung cấp số lượt tải.

[app-store-scraper list.js](https://raw.githubusercontent.com/facundoolano/app-store-scraper/master/lib/list.js) gọi RSS và tùy chọn Lookup; [constants.js](https://raw.githubusercontent.com/facundoolano/app-store-scraper/master/lib/constants.js) vẫn đặt 7003 là GAMES_ARCADE. Không nên dùng tên constant cũ để diễn giải genre hiện tại. Chưa cài/chạy thư viện nên không tuyên bố thư viện hỏng; gọi HTTPS nguồn trực tiếp có bằng chứng phù hợp hơn cho P1 hiện tại.

[Apple Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html) ghi xấp xỉ 20 calls/phút, có thể thay đổi, và khuyến nghị caching. Lô 20 ID đã thử VN/US giúp giảm số lượt gọi; chưa benchmark cả 1.100 bản ghi. Không nhân quota theo từng quốc gia khi vẫn gọi cùng nguồn từ một máy.

## Hệ quả cho thiết kế và lịch

- Chọn ứng viên `topfreeapplications + genre7003 + depth100` cho P1; tên hiển thị “Top Free Casual — theo phân loại Apple”. Games tổng thể chỉ là bằng chứng đối chiếu trong khảo sát, không thành chart mặc định bổ sung.
- Giữ cả mã và nhãn genre nguồn. App thiếu metadata vẫn giữ rank; không dùng title trùng để gộp game.
- Top 100 Casual không đại diện toàn bộ Casual hoặc hybrid-casual. Không tự chuyển sang Top Apps/Games nếu feed Casual lỗi.
- Một lượt cold-start 11 thị trường cần 11 chart requests + tối đa 55 lượt Lookup lô 20 cho 1.100 dòng nếu không cache. Đây là phép tính tải dự kiến, không phải pipeline đã chạy.
- Đề xuất giãn request, cache metadata theo app và quốc gia; giữ snapshot chart trước enrichment. Không lựa chọn giờ từ thời gian phản hồi một lần.
- DEC-09 vẫn cần đo nhiều ngày trên máy chạy thật. Máy Windows tắt/ngủ không thu thập được; không hồi tạo snapshot quá khứ từ feed hiện tại khi máy mở lại.

Chưa kiểm chứng: ổn định dài hạn, nhịp thay đổi chart thực, giới hạn toàn bộ endpoint, lô Lookup cho toàn bộ Casual ở mọi nước, khả năng phục hồi sau sleep/restart và giờ chạy tối ưu. Các nội dung đó là tiêu chí kiểm chứng tiếp theo, không làm mất giá trị của nguồn đã thử thành công.
