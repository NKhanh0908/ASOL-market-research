# PRD — Công cụ nghiên cứu thị trường Casual Game

Ngày: 2026-09-10. Mã: `PRD-CASUAL-MKT-001`. Phiên bản: **2.2 — hợp nhất PRD và BA-CASUAL-001**. Trạng thái: **Đã chốt hướng sản phẩm, GAP-01–10, DEC-01–09 và đánh giá nguồn dữ liệu. DEC-09 chốt phương pháp chọn lịch, chưa chốt giờ khi chưa đo; các thông số triển khai chưa xác định được ghi tại mục 7.**

## 1. Kết luận và thẩm quyền nguồn

Dự án nên được chia thành bốn phần có đầu ra nghiệm thu độc lập: **thu thập dữ liệu → phân tích → thống kê → AI đánh giá**. Giá trị đầu tiên là có dữ liệu thị trường truy nguyên được; giá trị cuối cùng là hỗ trợ người dùng chọn thể loại để phát triển. AI không phải điều kiện để hoàn thành phần thu thập.

Đây là tài liệu yêu cầu sản phẩm duy nhất sau khi hợp nhất PRD ban đầu và bản phân tích BA-CASUAL-001 theo yêu cầu người dùng. Các điều chỉnh đã chốt được áp dụng trực tiếp trong tài liệu này; yêu cầu gốc và ba báo cáo nghiên cứu vẫn là nguồn tham chiếu.

| Mã nguồn | Tài liệu | Vai trò và mức thẩm quyền |
|---|---|---|
| SRC-01 | [requirement.md](../core/requirement.md) | Yêu cầu gốc do người dùng chỉ định: nghiên cứu casual đang trend/hot lượt tải, hỗ trợ chọn thể loại, ưu tiên miễn phí và làm tuần tự |
| SRC-02 | [AI Agent-n8n.md](../core/research/AI%20Agent-n8n.md) | Nghiên cứu workflow; có ghi “Trend spotting (đã chọn)”, nhưng không chứng minh các quyết định khác đã được người dùng duyệt |
| SRC-03 | [Báo cáo API/data source](../core/research/casual_game_api_data_sources_report.md) | Danh mục nguồn, mô hình dữ liệu và scoring đề xuất; không phải cam kết khả năng truy cập |
| SRC-04 | [Nghiên cứu game casual AI](../core/research/Nghi%C3%AAn%20C%E1%BB%A9u%20Game%20Casual%20AI.md) | Tổng hợp thị trường và phương án công nghệ; số liệu và khuyến nghị không mặc nhiên là quy tắc sản phẩm |
| SRC-05 | PRD phiên bản 1 và bản phân tích BA-CASUAL-001, đã hợp nhất vào tài liệu này | Giữ ID M1–M5, US-001–US-004, BA-R01–12, GAP-01–10 và DEC-01–09 để truy vết; nội dung phiên bản này thay thế các quy tắc mâu thuẫn trước đó |

Quy ước: **Yêu cầu gốc** = nêu rõ trong SRC-01; **bằng chứng tài liệu** = nguồn có phát biểu đó; **suy luận** = diễn giải phục vụ phân tích; **đề xuất** = cần quyết định; **chưa biết** = chưa có dữ liệu xác nhận. Bằng chứng tài liệu không đồng nghĩa bằng chứng khách hàng hoặc kiểm chứng thực tế.

- Người dùng trực tiếp được xác nhận: người yêu cầu công cụ. Persona Producer/Indie Developer/Studio Lead là đề xuất của SRC-05; quy mô 1–10 người chưa được xác nhận.
- Vấn đề suy luận: cần giảm công sức tổng hợp tín hiệu thị trường và có căn cứ chọn thể loại. Chưa có baseline thời gian làm thủ công hoặc phỏng vấn khách hàng.
- Ràng buộc đã nêu: ưu tiên thứ miễn phí có sẵn; làm từng phần; iOS trước, Android sau. Ưu tiên miễn phí; giao diện web trước; thị trường VN và US đã chốt, khu vực Đông Nam Á (ASEAN) đã chốt, danh sách storefront khả dụng cần kiểm chứng. Chưa chốt ngân sách cứng, deadline và máy chạy. Theo ghi chú người dùng tại GAP-02, có thể cân nhắc crawl nhưng cần phân tích website mục tiêu và bàn kỹ trước khi chọn cách thu thập.
- Phạm vi đích: tìm game casual đang nổi và hỗ trợ chọn thể loại. **Người dùng đã xác nhận trong phiên ngày 2026-09-10: “iOS trước, Android sau”.** Đây là quyết định nền tảng có thẩm quyền bổ sung SRC-01; không đồng nghĩa toàn bộ PRD được duyệt. VN và US đã được người dùng chốt; Đông Nam Á (ASEAN) đã chốt; danh sách storefront khả dụng và Top N còn cần kiểm chứng.
- Chưa có bằng chứng bất đồng giữa các stakeholder; các xung đột dưới đây là xung đột giữa tài liệu. Người quyết định đề xuất: người yêu cầu/chủ sản phẩm.

## 2. Quyết định sản phẩm đã chốt

**Ghi nhận phê duyệt ngày 2026-09-10:** người dùng chốt iOS trước, Android sau; chốt các điều chỉnh GAP-01–10 và đồng ý đánh giá nguồn dữ liệu tại mục 3. GAP-05 áp dụng ngưỡng ban đầu tăng ít nhất 20 bậc trong 1 ngày HOẶC tổng cộng ít nhất 30 bậc trong 3 ngày. Việc chốt GAP không tự điền các thông tin còn thiếu như quốc gia, Top N, ngân sách hoặc máy chạy. Các con số mục tiêu pilot vẫn là đề xuất theo GAP-09.

| ID | Quyết định đã chốt | Áp dụng |
|---|---|---|
| GAP-01 | Chia P1–P4; P1 chỉ thu thập và lưu bằng chứng tối thiểu | Mục 4; M1 và phần lưu trữ M2 |
| GAP-02 | Ưu tiên miễn phí trước; có thể cân nhắc crawl nhưng cần phân tích website mục tiêu và bàn kỹ cách thu thập trước | Mục 3; BA-R12; chưa có trần ngân sách cụ thể |
| GAP-03 | Ghi rõ đang đo thứ hạng; nhu cầu số lượt tải cần nguồn riêng, không coi rank là downloads | BA-R09; phạm vi downloads cụ thể còn ở DEC-03 |
| GAP-04 | Xác minh loại chart, quốc gia, độ sâu; gọi đúng tên tập quan sát; không hứa ≥100 game trước kiểm chứng | BA-R01; DEC-02 |
| GAP-05 | FAST_RISER v1: delta_1D≥20 HOẶC delta_3D≥30; lưu phiên bản quy tắc | BA-R05/06; DEC-06 đã chốt |
| GAP-06 | Thiếu dữ liệu thì ghi chưa đủ dữ liệu; NEW_ENTRY cần snapshot so sánh hợp lệ | BA-R05/06 |
| GAP-07 | Tách genre nguồn với nhãn casual/mechanic; cho phép chưa xác định | BA-R07 |
| GAP-08 | Tách quan sát/suy luận; thiếu chứng cứ thì unknown; không cấm thể loại chỉ từ ví dụ nghiên cứu | BA-R10/11 |
| GAP-09 | KPI trở thành mục tiêu pilot có cách đo, baseline và điều kiện; không hứa SLA chưa kiểm chứng | Mục 6 |
| GAP-10 | Một nguồn được kiểm chứng trước; chọn công nghệ theo nhu cầu vận hành | Mục 3/4; DEC-05 |

### Quy tắc tăng hạng nhanh v1

Thứ hạng càng nhỏ càng cao. Gắn FAST_RISER khi tăng **ít nhất 20 bậc so với hôm qua HOẶC tổng cộng ít nhất 30 bậc so với 3 ngày trước**. Chỉ cần một điều kiện đúng; nhánh 3 ngày không yêu cầu ngày nào cũng tăng.

| Ví dụ giả định | Kết quả |
|---|---|
| Hôm qua hạng 80, hôm nay 60 | +20 bậc trong 1 ngày → có nhãn |
| Hạng qua bốn mốc ngày: 90 → 70 → 75 → 60 | +30 bậc trong 3 ngày → có nhãn dù có một ngày tụt hạng |
| Ba ngày trước 80, hôm qua 70, hôm nay 60 | +10 bậc trong 1 ngày, +20 trong 3 ngày → chưa đạt |

Đây là luật sàng lọc ban đầu đã được duyệt, chưa phải bằng chứng dự báo thành công. Mốc so sánh phải cùng store/quốc gia/chart và đủ dữ liệu. Lưu phiên bản luật cùng kết quả để khi điều chỉnh ngưỡng vẫn giải thích được báo cáo cũ.

## 3. Đánh giá nghiên cứu và khả năng dùng dữ liệu

**Trạng thái: người dùng đã đồng ý với đánh giá và giới hạn tại mục này ngày 2026-09-10.** Sự đồng ý không thay thế kiểm chứng API/website thực tế còn thiếu.

SRC-02 phù hợp nhất với vòng phát hiện trend qua lịch sử rank. SRC-03 hữu ích như danh mục lựa chọn, nhưng “8 nguồn MVP” vượt nhu cầu đầu tiên. SRC-04 cung cấp giả thuyết phân tích mechanic, monetization và nguồn lực; không dùng các benchmark hoặc ví dụ game trong đó làm hằng số quyết định.

Kiểm tra tài liệu chính thức ngày 2026-09-10, giới hạn ở những phụ thuộc ảnh hưởng trực tiếp đến yêu cầu:

| Nguồn | Điều đã kiểm tra | Hệ quả cho yêu cầu |
|---|---|---|
| [Apple RSS Builder](https://rss.marketingtools.apple.com/) | Có cấu hình storefront, feed, result limit; nội dung trang đọc được không xác nhận cụ thể Top 100/200 Games US/VN | Chỉ là ứng viên P1. Cần lấy payload thực tế và chứng minh đúng loại chart trước cam kết bao phủ |
| [Apple Search API — tài liệu lưu trữ](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html) | Có country; tài liệu ghi xấp xỉ 20 calls/phút, có thể thay đổi, và khuyến nghị caching | Không coi API là không giới hạn. `limit=200` của Search không chứng minh chart RSS có 200 game |
| [Google Play reviews.list](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/list) | Yêu cầu OAuth scope androidpublisher | Không coi đây là public API lấy review đối thủ chỉ bằng package name |
| [Google Trends API](https://developers.google.com/search/apis/trends) | Tài liệu công bố API Alpha | Chưa có bằng chứng tài khoản dự án được truy cập; không đặt làm phụ thuộc bắt buộc của P1 |

Chưa chạy thử API nguồn, chưa xác minh SLA/độ sâu chart, chưa kiểm chứng toàn bộ số liệu thị trường, giá, quota hay điều khoản của các dịch vụ trong ba báo cáo. Các phát biểu “100% ổn định”, “không bị block”, “chi phí bằng không” trong nghiên cứu không đủ làm acceptance criteria. Chưa chọn nhà cung cấp hay gói trả phí.

Giới hạn suy luận cần hiển thị: rank là vị trí tương đối trong một chart tại một thị trường; không phải số lượt tải, tăng trưởng downloads hay doanh thu. Top chart cũng có thể bỏ sót game ngách ngoài phạm vi quan sát. Chỉ có dữ liệu iOS thì kết luận phải ghi phạm vi iOS, không đại diện toàn bộ thị trường casual.

### 3.1. Cách lấy dữ liệu và cơ sở chọn giờ chạy

Cập nhật theo yêu cầu người dùng; đây là phân tích tài liệu và phương án kiểm chứng, chưa phải kết quả vận hành.

| Phương thức | Vai trò | Hệ quả về ổn định/lịch chạy |
|---|---|---|
| Feed/RSS Apple | Lấy danh sách xếp hạng theo storefront | Chứng minh đúng Games/chart và độ sâu trước. Một lượt lấy danh sách tránh phải mở từng trang để khám phá app |
| Search/Lookup Apple | Bổ sung metadata theo ID và quốc gia | Cache metadata; chỉ cập nhật phần cần thiết; kiểm soát tốc độ gọi độc lập với lịch lấy chart |
| Thư viện mã nguồn mở | Đóng gói gọi nguồn và parse kết quả | Không là một nguồn dữ liệu độc lập, không tự cung cấp downloads bị thiếu hoặc bỏ được giới hạn nguồn |
| Crawl website | Phương án bổ sung khi nguồn cấu trúc không đáp ứng | Phải phân tích website cụ thể, dữ liệu trả về, số request, giới hạn truy cập và công bảo trì trước khi chọn lịch |

Đã đọc [README app-store-scraper](https://github.com/facundoolano/app-store-scraper), [mã list.js](https://raw.githubusercontent.com/facundoolano/app-store-scraper/master/lib/list.js) và [app.js](https://raw.githubusercontent.com/facundoolano/app-store-scraper/master/lib/app.js): `list` gọi RSS Apple, còn lấy chi tiết app dùng lookup; tùy chọn fullDetail cũng gọi lookup. Mã thư viện cho phép num tối đa 200 không chứng minh endpoint hiện còn đáp ứng 200 game. Đây là ứng viên cần thử, chưa chọn làm phụ thuộc triển khai.

[Tài liệu Search API của Apple](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html) ghi khoảng 20 calls/phút, có thể thay đổi, và khuyến nghị cache. Giới hạn này không được tự áp làm quota cho mọi endpoint RSS/crawl. Phân tích suy ra: giảm số request, giới hạn tốc độ và xử lý retry có căn cứ trực tiếp hơn việc chọn giờ theo lượng người chơi.

**Chưa thể chọn 01:00 VN là lịch tối ưu:** tài liệu đã đọc không công bố đường cong tải hoặc cửa sổ ít tải cho các endpoint. Storefront VN/US không chứng minh request được xử lý tại server riêng trong quốc gia đó. Châu Á có nhiều múi giờ; US cũng không có một giờ địa phương duy nhất. Vì vậy không chia lịch “VN ban đêm, US ngược lại” chỉ từ giả định traffic người dùng.

Đã thử mở hai feed mẫu VN/US bằng công cụ web: VN bị công cụ từ chối mở, US gặp timeout. Chưa nhận được payload hợp lệ; không xem hai lỗi này là phép đo hiệu năng nguồn hoặc bằng chứng endpoint đã ngừng hoạt động. Chưa có phép đo trực tiếp từ máy sẽ chạy pipeline.

**Phương án khảo sát để chốt lịch, chưa phải lịch production:**

1. Xác nhận endpoint thực tế đúng loại chart tại VN/US và các quốc gia đã chọn; ghi header/thời gian cập nhật nếu có, độ sâu, số request và metadata thiếu. Chọn nguồn và phương thức sau bước này.
2. Trên máy dự kiến vận hành, thử lượng request nhỏ trong ít nhất 7 ngày ở các cửa sổ cách đều theo UTC (ví dụ 00:00, 06:00, 12:00, 18:00 UTC, tương ứng 07:00, 13:00, 19:00, 01:00 hôm sau giờ VN). Đây là các điểm lấy mẫu so sánh, không phải khẳng định giờ ít tải. Không crawl toàn bộ metadata ở mỗi cửa sổ.
3. Ghi số request, tỷ lệ thành công, timeout/429/5xx, latency trung vị/p95, kích thước payload, dấu cập nhật hoặc thời điểm quan sát thay đổi chart, cùng tải máy chạy. Không coi chart không thay đổi là dữ liệu cũ nếu không có chứng cứ thời điểm cập nhật.
4. Ưu tiên cửa sổ có ít lỗi/rate-limit, sau đó xét latency và độ tươi cho người dùng. Nếu mẫu ít hoặc không có khác biệt rõ, kéo dài khảo sát hoặc chọn giờ thuận vận hành và ghi đúng lý do; không gọi đó là giờ ít traffic đã được chứng minh.
5. Lấy chart trước, enrichment sau bằng hàng đợi/cache. Giãn các request theo giới hạn nguồn, retry có backoff và tôn trọng Retry-After khi có; tránh nhiều job cùng gọi dồn lúc đúng giờ. Đề xuất ban đầu dùng một cửa sổ chung cho các storefront để dễ so sánh, chỉ tách khi bằng chứng đo cho thấy cần.

Khi chốt lịch: lưu thời điểm UTC, múi giờ hiển thị và ngày snapshot nhất quán. Nếu dùng lịch địa phương US phải chỉ định vùng múi giờ và xử lý daylight saving; không hardcode “US = VN trừ 12 giờ”. Chưa có kết quả đo nên chưa xác nhận giờ production. Phép khảo sát kéo dài này là công việc tiếp theo, chưa được chạy trong đợt cập nhật PRD.

## 4. Phân kỳ theo giá trị và điều kiện nghiệm thu

Thứ tự bốn phần và giới hạn P1 chỉ thu thập/lưu bằng chứng tối thiểu đã được chốt qua GAP-01; ưu tiên một nguồn được kiểm chứng đã chốt qua GAP-10. Các chi tiết khác trong bảng vẫn là **đề xuất** nếu chưa có quyết định riêng.

| Phần | Giá trị và đầu ra | Điều kiện chuyển tiếp | Chi phí của việc hoãn |
|---|---|---|---|
| P1 — Thu thập, MVP đầu tiên | iOS trước theo xác nhận người dùng; một nguồn được kiểm chứng, phục vụ VN/US và các thị trường ASEAN có storefront khả dụng; VN chỉ tính một lần; dữ liệu gốc, bản ghi chuẩn hóa, lịch sử và báo cáo tình trạng lần lấy | Xem được nguồn, thời điểm, loại chart, số bản ghi; kiểm tra trường hợp thành công/lỗi/chạy lại | Chưa có kết luận trend hoặc khuyến nghị; Android được làm sau |
| P2 — Phân tích | Delta theo ngày, nhãn mới vào/tăng nhanh, phân loại có căn cứ | Có lịch sử đủ cho từng cửa sổ và thống nhất công thức; dữ liệu thiếu không tạo trend giả | Chưa có trải nghiệm tổng hợp tiện dụng |
| P3 — Thống kê | Bảng tổng hợp đọc được, lọc thị trường/genre/ngày, mở được bằng chứng | Phân biệt dữ liệu mới/cũ/thiếu; số đếm và danh sách đối chiếu được | Web tối thiểu có từ P1; hoãn biểu đồ/phân tích nâng cao đến P3 |
| P4 — AI đánh giá | AI chủ động gợi ý game/thể loại từ dữ liệu P2/P3, ước lượng nhân sự/vai trò, thời gian và độ khả thi | P1–P3 hoàn thành; có chứng cứ, giả định về phạm vi game, tiêu chí đánh giá và giới hạn chi phí AI; không bắt buộc hồ sơ team | Hoãn tư vấn tự động đến P4; người dùng trước đó đọc bảng số liệu |

Mức lưu trữ tối thiểu ở P1 phục vụ kiểm tra và tích lũy lịch sử, không kéo engine phân tích P2 vào P1. Theo DEC-05, P1 có web tối thiểu để xem dữ liệu đã lấy và trạng thái lần chạy; phần biểu đồ, bộ lọc phân tích và thống kê đầy đủ vẫn ở P3. Web không yêu cầu AI/chat và không thay đổi thứ tự thu thập → phân tích → thống kê → AI.

Ngoài phạm vi P1 được đề xuất: AI/LLM, chat, Dify, multi-agent, social/review enrichment, nhiều store, dữ liệu trả phí, tự gửi Slack/Telegram/email. Không cần xây các phần này để chứng minh đã thu thập đúng dữ liệu. Các yêu cầu bổ sung này chưa được duyệt.

Non-goals đề xuất cho cả sản phẩm: sinh game/assets, vận hành quảng cáo, bảo đảm doanh thu hoặc chọn “game chắc thắng”. PC/console chưa bị loại bởi SRC-01; chỉ hoãn nếu chốt mobile-first. Phân tích lượt tải vẫn thuộc nhu cầu gốc, chưa được coi là đã đáp ứng bằng proxy.

### Ánh xạ chức năng và user stories

Giữ ID của PRD ban đầu; mức ưu tiên áp dụng theo từng phần, không gom tất cả vào P1.

| ID | Nội dung cuối cùng | Phần / nghiệm thu |
|---|---|---|
| M1 / US-001 | Người dùng lấy được chart iOS và metadata có nguồn để giảm việc kiểm tra store thủ công | P1; BA-R01/02/04 |
| M2 / US-002 | Lưu lịch sử ở P1; tính delta ở P2 để so sánh thứ hạng đúng mốc | P1–P2; BA-R03/05 |
| M3 / US-002 | Phát hiện NEW_ENTRY, FAST_RISER và phân loại có căn cứ | P2; BA-R06/07 |
| M4 / US-003 | Người dùng xem danh sách đáng chú ý, lọc và thống kê để lập shortlist | P3; BA-R08; Top 10 tăng hạng/Top 5 mới vào là bố cục đề xuất, hiển thị ít hơn nếu thiếu ứng viên |
| M5 / US-004 | Người dùng nhận gợi ý game/thể loại kèm ước lượng nguồn lực cần thiết và đánh giá khả thi | Chỉ P4; BA-R10/11; không yêu cầu cung cấp team trước, không bắt buộc điểm 1–10 khi chưa có rubric |

Backlog giữ lại từ PRD gốc, ngoài P1:

| ID | Hạng mục | Trạng thái và điều kiện |
|---|---|---|
| S1 | Tín hiệu YouTube/Reddit và social | Tùy chọn sau nguồn chính; cần xác minh quyền truy cập, quota và giá trị bổ sung |
| S2 | Báo cáo Markdown và gửi Telegram/Slack/email | Kênh gửi/lịch gửi chưa chọn; chỉ gửi khi có yêu cầu rõ ràng |
| S3 | Dữ liệu Google Play | Android làm sau đã chốt; thời điểm và phương thức thu thập chưa chốt |
| C1 | Chat/Dify hoặc giao diện hội thoại | Chưa chọn; web thông thường đã chốt ở P1, chat không là phụ thuộc |
| C2 | Theo dõi đối thủ, update/ASO, phân tích review | Chưa duyệt phạm vi; có thể bổ sung khi nguồn dữ liệu chính ổn định |
| W1 | Downloads/revenue chính xác | Chưa có nguồn được xác nhận; không cam kết số chính xác, không thay bằng số suy ra từ rank |
| W2–W3 | Sinh game/assets và quản lý chiến dịch quảng cáo | Ngoài mục tiêu công cụ nghiên cứu đề xuất |
| W4 | PC/console/Web3 | Ngoài bản iOS đầu tiên; không tự mở rộng phạm vi |

### Yêu cầu vận hành kế thừa

Các yêu cầu sau là chi tiết bàn giao từ PRD gốc, chưa phải kiểm chứng đã đạt:

- **NFR-01 — Tính toàn vẹn:** giữ dữ liệu nguồn, dấu thời gian và lịch sử; ghi rõ kết quả thiếu/cũ/lỗi. Không dùng snapshot lỗi làm dữ liệu hiện tại.
- **NFR-02 — Khả năng phục hồi:** lỗi metadata hoặc nguồn bổ sung không làm mất dữ liệu chart hợp lệ. Retry có giới hạn theo khả năng nguồn; timeout 10 giây/3 lần thử từ PRD cũ là cấu hình đề xuất cần kiểm chứng.
- **NFR-03 — Bí mật và dữ liệu:** khóa API không hardcode hoặc đưa vào báo cáo/log; dùng cấu hình bí mật ngoài mã nguồn. Không thu thập thông tin cá nhân không cần thiết cho mục tiêu nghiên cứu.
- **NFR-04 — Chi phí:** theo dõi riêng dữ liệu, AI và hạ tầng; không tự chuyển sang dịch vụ trả phí khi hết quota. Không coi self-host hoặc free trial là bằng chứng tổng chi phí bằng 0.
- **NFR-05 — Hiệu năng:** đo thời gian theo quy mô thực tế; mốc dưới 15 phút chỉ là mục tiêu đề xuất, không là cam kết khi chưa kiểm chứng nguồn.
- **NFR-06 — Nguồn crawl:** trước khi chọn crawl, phân tích website mục tiêu về dữ liệu có thể lấy, ý nghĩa chart, cách truy cập, giới hạn sử dụng/tần suất và chi phí bảo trì; bàn phương án dựa trên kết quả phân tích. Chưa có website crawl được chọn.

## 5. Yêu cầu truy vết và kiểm tra nghiệm thu

Các ID BA-Rxx ổn định cho tài liệu này, ánh xạ về ID gốc khi có. **Các quy tắc đã chốt tại mục 2 là baseline; chi tiết kiểm tra bổ sung dưới đây phục vụ nghiệm thu, chưa phải test đã chạy.** “YG/ĐX” nghĩa là mục tiêu có trong yêu cầu gốc và có chi tiết nghiệm thu đề xuất; “ĐX” chỉ các chi tiết bổ sung chưa được duyệt riêng. Các nhãn này không mở lại quy tắc GAP đã chốt tại mục 2.

| ID / nguồn / phần / trạng thái | Tác nhân và quy tắc | Kết quả thành công quan sát được | Kết quả lỗi/biên quan sát được |
|---|---|---|---|
| BA-R01 / SRC-01; M1, US-001 / P1 / YG/ĐX | Người vận hành lấy chart theo cấu hình nguồn, store, quốc gia, loại chart, độ sâu | Bản ghi có ID nguồn, tên, rank nguồn, URL, thời điểm lấy; báo số trả về và số lưu | Timeout/response lỗi không được báo là chart rỗng thành công; giữ lần hợp lệ trước và ghi trạng thái lần lỗi |
| BA-R02 / M1, US-001 / P1 / ĐX | Người phân tích xem metadata bổ sung | Metadata có nguồn/thời điểm; nối đúng ID app và quốc gia | Lookup thiếu rating/description vẫn giữ bản ghi chart, trường thiếu là unknown; không loại game hoặc điền số 0 giả |
| BA-R03 / M2, US-002 / P1 / ĐX | Người vận hành lưu lịch sử để đối chiếu | Có thể mở snapshot và bằng chứng gốc; chạy lại cùng phiên không nhân đôi bản ghi báo cáo | Dữ liệu mới không xóa lịch sử; lần lấy không hoàn chỉnh không thay snapshot hoàn chỉnh đang dùng |
| BA-R04 / SRC-01; SRC-02 §3 / P1 / YG/ĐX | Người vận hành biết dữ liệu được lấy khi nào, có đủ không | Mỗi lần có trạng thái, thời gian, số nhận/hợp lệ/bị loại và lý do; lịch chạy nêu múi giờ | Máy không chạy/nguồn lỗi làm hiện dữ liệu cũ và lần thành công gần nhất; không đổi ngày cũ thành hôm nay |
| BA-R05 / M2, US-002 / P2 / ĐX | Người phân tích so cùng store/quốc gia/chart/độ sâu giữa T và T-k | Delta_k=rank(T-k)-rank(T); ví dụ 60→35 cho +25, 35→60 cho -25 | Thiếu một đầu mốc hoặc thay chart thì delta=null/chưa đủ dữ liệu, không bằng 0; không lấy T-2 giả làm T-1 |
| BA-R06 / M3, US-002 / P2 / Luật v1 đã chốt; chi tiết bổ sung ĐX | Người dùng phát hiện NEW_ENTRY và FAST_RISER theo quy tắc có phiên bản | NEW_ENTRY: có trong Top N ngày T, vắng trong snapshot Top N đầy đủ T-1; FAST_RISER v1 đã chốt: delta_1D≥20 hoặc delta_3D≥30 | Ngày đầu/thiếu T-1 không suy ra NEW_ENTRY; vắng khỏi Top N không gán rank=N+1. NEW_ENTRY có thể là trở lại chart, không có nghĩa mới phát hành |
| BA-R07 / M3, US-003; SRC-03 §6 / P2 / ĐX | Người phân tích xem genre nguồn và nhãn casual/mechanic riêng | Nhãn có căn cứ, phương pháp/phiên bản; lọc Puzzle khớp quy tắc được chốt | Thiếu căn cứ để UNKNOWN; không gắn High Potential chỉ do có genre Puzzle/Simulation; không coi tên game là chứng cứ đủ cho mechanic |
| BA-R08 / SRC-01; M4, US-003 / P3 / YG/ĐX | Người dùng xem bảng game đáng chú ý | Thấy rank, delta, ngày, quốc gia/chart, genre, nhãn, URL; Top tăng hạng được sắp đúng trong tập đã lọc | Chỉ có 3 game hợp lệ thì hiện 3; không bù thành Top 10 bằng dữ liệu cũ; biểu đồ nêu mẫu số và nhóm unknown |
| BA-R09 / SRC-01; W1 / P1–P4 / YG/ĐX | Người dùng hiểu đúng “hot lượt tải” | Mỗi metric nêu loại rank/observed/estimate, nguồn và thời kỳ; nếu có downloads thì nêu đơn vị/phạm vi | Không có downloads thì hiển thị không có dữ liệu; không đổi rank hoặc rating_count thành downloads |
| BA-R10 / SRC-01; M5, US-004 / P4 / YG/ĐX | Người phát triển nhận phân tích AI dựa trên chứng cứ | Báo cáo tách quan sát/suy luận, có nguồn và ngày cho mechanic/art/monetization, giả thuyết trend và thiếu hụt | Không có ảnh/review thì không tuyên bố đã xem; thiếu chứng cứ không khẳng định IAA/IAP, CPI, retention hay nguyên nhân tăng hạng |
| BA-R11 / SRC-01; US-004; DEC-08 / P4 / Hướng đã chốt | Người dùng nhận gợi ý chủ động và biết nguồn lực dự kiến để làm game | Với dữ liệu thị trường và không có hồ sơ team, AI vẫn đề xuất ứng viên có căn cứ; nêu phạm vi game giả định, khoảng nhân sự/vai trò, thời gian dự kiến, độ khả thi, rủi ro và lý do. Các số là ước lượng, không là dữ liệu đã đo | Không bắt người dùng nhập team để bắt đầu; thiếu chứng cứ thì nêu chưa đủ cơ sở hoặc đưa kịch bản có giả định thay vì bịa số chắc chắn. Không đủ ứng viên thì trả ít hơn; lỗi LLM vẫn xem được bảng P3 |
| BA-R12 / SRC-01; NFR / P1–P4 / YG/ĐX | Người vận hành kiểm soát chi phí | Cấu hình nêu dịch vụ và giới hạn đã chọn; có thống kê usage/chi phí biết được | Hết quota không tự chuyển sang provider trả phí; báo bước bị dừng và chi phí chưa biết, không gán bằng 0 |

Ngưỡng BA-R06 là quy tắc v1 đã được người dùng chốt theo US-002; chưa có bằng chứng dự báo chất lượng cơ hội. Delta_7D chỉ tính khi đủ mốc, không làm chậm P1. Độ sâu chart thay đổi làm mất tính so sánh; cần tạo phạm vi/phiên bản mới hoặc chứng minh tập Top N chung đầy đủ trước tính nhãn.

## 6. Kết quả mong đợi và cách đo

Tất cả baseline hiện **chưa biết**; chưa có pipeline hoặc nghiên cứu người dùng được kiểm tra trong đợt phân tích này. Các con số dưới đây là **mục tiêu pilot đề xuất**, không phải cam kết đã đạt.

| ID | Chỉ số và cách đo | Mục tiêu đề xuất / lý do |
|---|---|---|
| OUT-01 | Số bản ghi chart hợp lệ đã lưu / số bản ghi hợp lệ nguồn trả về, theo từng lần chạy | 100% trong lần thành công; đánh giá tính toàn vẹn, không đánh đồng với bao phủ toàn thị trường |
| OUT-02 | Số lần chạy lịch thành công / số lần dự kiến, đo pilot 7 ngày; báo riêng ngày máy tắt | 7/7 lần để kiểm tra vòng vận hành ban đầu; chưa phải SLA dài hạn |
| OUT-03 | Số kết quả rank/nhãn đúng / bộ trường hợp có kết quả kỳ vọng | 100% các ca ở BA-R05/06, gồm thiếu dữ liệu, đổi chart và trở lại Top N; đo tính đúng của luật, không đo “trend thật” |
| OUT-04 | Thời gian người dùng tạo shortlist từ cùng tập dữ liệu, so với làm thủ công | Đo baseline trước; đề xuất giảm ≥50% ở P3 để chứng minh tiết kiệm công sức |
| OUT-05 | Người dùng đánh dấu ứng viên “đáng nghiên cứu thêm” / tổng ứng viên đã xem | Pilot 20 ứng viên, mục tiêu đề xuất ≥50%; đo hữu ích ban đầu, không dự báo thành công thương mại |
| OUT-06 | Tỷ lệ nhận định AI được dẫn chứng hoặc ghi rõ suy luận/unknown | 100% trên bộ 10 báo cáo pilot; ngăn đánh đồng suy luận với dữ liệu |
| OUT-07 | Phí nguồn + AI + hạ tầng mỗi tháng; phần chưa đo ghi riêng | Trần tiền chưa chốt; ưu tiên phí API bắt buộc bằng 0 ở P1 nếu nguồn đáp ứng. Không tính free trial là bền vững |

Thời gian <15 phút và lịch 08:00 trong SRC-05 giữ trạng thái đề xuất. Độ tươi nên đo từ lần lấy thành công gần nhất; chưa thể hứa phát hiện ≤24h kể từ sự kiện thực nếu không biết khi nào nguồn cập nhật.

## 7. Quyết định đã chốt và thông số cần xác minh

Người yêu cầu xác nhận chốt tất cả DEC trong phiên ngày 2026-09-10, đồng thời điều chỉnh DEC-08: AI chủ động gợi ý game/thể loại và ước lượng nguồn lực, độ khả thi; không bắt buộc người dùng cung cấp hồ sơ team trước. Phần này chỉ triển khai ở P4 sau P1 → P2 → P3. Chốt DEC-09 là chốt cách phân tích và đo để chọn lịch, không biến 01:00 VN thành lịch đã duyệt. Các thông số nguồn/Top N/host/giờ chạy còn cần kiểm chứng; không mở lại các quyết định sản phẩm đã chốt.

| ID / yêu cầu chịu ảnh hưởng | Câu hỏi và lựa chọn | Khuyến nghị / tradeoff | Owner đề xuất / bằng chứng cần có |
|---|---|---|---|
| DEC-01 / BA-R01,09 — Đã chốt thứ tự nền tảng | Ưu tiên iOS hay Android? | **iOS trước, Android sau**. Bản đầu không đại diện Android; nguồn chart iOS vẫn cần kiểm chứng. Chưa chốt thời điểm bổ sung Android; PC không nằm trong bản đầu đề xuất | Người yêu cầu / trả lời trực tiếp ngày 2026-09-10: “iOS trước, Android sau” |
| DEC-02 / BA-R01,05,06 — Chốt phạm vi địa lý | Việt Nam, Đông Nam Á (ASEAN) và US | Xác minh storefront khả dụng của các quốc gia trong phạm vi; VN thuộc nhóm ASEAN nhưng được ưu tiên xem riêng, không thu thập/đếm hai lần. Quốc gia không có nguồn phải báo rõ không được bao phủ; không gộp rank thành một chart ASEAN. Loại chart và Top N còn cần kiểm chứng | Người yêu cầu / đã xác nhận Đông Nam Á (ASEAN) trong phiên này |
| DEC-03 / BA-R09 — Đã chốt | Bản đầu dùng rank làm tín hiệu, ghi rõ chưa có số lượt tải | Tiếp tục tìm nguồn miễn phí cho downloads; không suy số lượt tải từ rank và không coi nhu cầu downloads đã được đáp ứng | Người yêu cầu / xác nhận chốt tất cả sau giải thích |
| DEC-04 / BA-R12 — Chốt ưu tiên miễn phí | Lấy những gì free trước; khảo sát API, thư viện hỗ trợ và crawl | Thư viện có thể gọi cùng API/website, vẫn phải kiểm chứng nguồn. Chưa chọn dịch vụ trả phí; máy chạy và trần tiền về sau chưa biết | Người yêu cầu / xác nhận trực tiếp; phân tích nguồn tại mục 3.1 |
| DEC-05 / BA-R04,08 — Chốt web trước | Người dùng xem dữ liệu qua web | P1 có web tối thiểu cho dữ liệu/trạng thái; thống kê đầy đủ ở P3. Chưa chọn framework, nơi host hoặc cơ chế truy cập | Người yêu cầu / “nên web trước” |
| DEC-06 / BA-R05,06 — Đã chốt | FAST_RISER v1: delta_1D≥20 hoặc delta_3D≥30; nhánh 3 ngày tính tổng thay đổi, không yêu cầu tăng liên tiếp | Áp dụng ban đầu và lưu phiên bản; chỉ điều chỉnh sau khi đánh giá dữ liệu thực tế | Người yêu cầu / xác nhận dùng phương án đã giải thích và chốt các GAP ngày 2026-09-10 |
| DEC-07 / BA-R07,08 — Chốt hướng phân loại | Phân loại các nhóm nhỏ nhưng vẫn trong Casual | Tách xác định thuộc Casual và nhãn mechanic/subgenre. Chưa chắc thuộc Casual thì để chờ phân loại, không đưa vào thống kê Casual đã xác nhận; taxonomy cụ thể cần ví dụ | Người yêu cầu / xác nhận trực tiếp |
| DEC-08 / BA-R10,11 — Đã chốt, dành cho P4 | AI chủ động đề xuất game/thể loại, ước lượng cần bao nhiêu người, vai trò, thời gian và độ khả thi | Không yêu cầu hồ sơ team làm đầu vào bắt buộc. Kết quả nêu phạm vi game, giả định và khoảng ước lượng; tiêu chí chi tiết xây dựng khi đến P4. Không kéo AI vào P1–P3 | Người yêu cầu / điều chỉnh trực tiếp và yêu cầu làm tuần tự theo requirement |
| DEC-09 / BA-R03,04 — Chốt cách ra quyết định; chưa chốt giờ | Chọn lịch theo phương thức lấy dữ liệu và đo ổn định; 01:00 VN là giả thuyết cần đánh giá | Không mặc định giờ ngủ của người dùng là giờ ít tải API. Thử nguồn và so các cửa sổ trước; lịch cuối phải có dữ liệu latency/lỗi/độ tươi, xem mục 3.1 | Người yêu cầu / yêu cầu phân tích, không chọn giờ tùy ý; retention và deadline còn thiếu |

### 7.1. Cách áp dụng DEC-03 và DEC-08

**DEC-03 — rank trước, downloads bổ sung sau:** game từ hạng 80 lên 40 cho biết tăng 40 bậc, chưa biết số lượt tải. Bản đầu đã được chốt sử dụng tín hiệu này với nhãn rõ ràng; downloads để chưa có dữ liệu và tiếp tục khảo sát nguồn miễn phí.

**DEC-08 — AI đề xuất nguồn lực, chỉ ở P4:** đầu ra mong muốn là “Đề xuất game/thể loại này vì các tín hiệu thị trường …; với phạm vi tính năng giả định …, dự kiến cần khoảng … người, các vai trò …, khoảng thời gian …; mức khả thi … vì …; rủi ro …”. Đây là mẫu cấu trúc, chưa có con số thực tế được kiểm chứng. AI không bắt buộc biết team hiện tại của người dùng. Ước lượng phải gắn với phạm vi prototype/MVP/sản phẩm đầy đủ, giả định kỹ năng và chứng cứ; không coi ước lượng là cam kết. Chi tiết rubric và cách hiệu chỉnh ước lượng được làm khi đến P4, không là điều kiện để bắt đầu thu thập dữ liệu.

## 8. Mức sẵn sàng bàn giao

**Có thể tiếp tục ngay:** rà soát mẫu dữ liệu nguồn, xác minh chart games/apps và quốc gia, lập mẫu đầu ra P1, làm rõ taxonomy bằng ví dụ, xác định bộ trường hợp nghiệm thu dữ liệu. Những việc này không phụ thuộc chọn AI, Dify hay web.

**Thứ tự thực hiện đã chốt:** P1 thu thập iOS cho phạm vi VN/ASEAN/US và hiển thị web tối thiểu; tiếp theo P2 phân tích; P3 thống kê; cuối cùng P4 AI gợi ý chủ động theo DEC-08. Công việc còn cần kiểm chứng ở P1 là endpoint/độ sâu chart/storefront khả dụng, môi trường chạy và phép đo chọn lịch DEC-09. P2 cần đủ lịch sử và taxonomy cụ thể. P4 mới xác định chi tiết cách ước lượng nguồn lực, rubric và ngân sách AI; không lấy hồ sơ team hoặc thiết kế AI làm điều kiện chặn P1–P3.

**Bàn giao hiện tại:** PRD hợp nhất này cùng yêu cầu gốc và ba báo cáo nghiên cứu. GAP-01–10 đã được giải quyết bằng quyết định sản phẩm; mục 7 phân biệt thông số còn thiếu với quyết định đã chốt. Chưa triển khai pipeline, chưa chạy acceptance tests và chưa xác nhận chất lượng trend thực tế.




