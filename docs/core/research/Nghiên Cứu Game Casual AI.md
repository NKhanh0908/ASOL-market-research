# **Báo Cáo Nghiên Cứu Kiến Trúc Kỹ Thuật Và Chiến Lược: Xây Dựng Hệ Thống AI Agent Và n8n Trong Phân Tích Dữ Liệu Thị Trường Game Casual**

## **1\. Tổng Quan Về Sự Dịch Chuyển Của Thị Trường Game Casual (2025-2026)**

Thị trường game di động toàn cầu đang trải qua một giai đoạn tái cấu trúc toàn diện, trong đó phân khúc game Casual tiếp tục khẳng định vị thế là động lực tăng trưởng cốt lõi giữa bối cảnh suy thoái chung. Để thiết kế một công cụ AI Agent có khả năng tư vấn, tìm kiếm và hỗ trợ lựa chọn thể loại game Casual để phát triển, hệ thống trí tuệ nhân tạo trước hết phải được trang bị một cơ sở dữ liệu chuyên sâu về bối cảnh vĩ mô, các chỉ số vi mô và những thay đổi mang tính hệ thống của ngành. Các dữ liệu này sẽ đóng vai trò là "tri thức nền tảng" (ground truth) để Agent có thể đưa ra các khuyến nghị chiến lược chính xác cho nhà phát triển, đặc biệt là các studio độc lập (indie) hoặc các nhóm nhỏ có nguồn ngân sách hạn hẹp.  
Theo các báo cáo nghiên cứu thị trường chi tiết từ Sensor Tower, doanh thu toàn cầu của phân khúc game Casual đã đạt quy mô xấp xỉ 22 tỷ USD vào năm 20251. Trong nửa đầu năm 2025, doanh thu từ mua sắm trong ứng dụng (Net IAP Revenue) của riêng phân khúc này đã cán mốc 12 tỷ USD trên toàn cầu2. Tuy nhiên, sự tăng trưởng này diễn ra trong bối cảnh tổng lượt cài đặt của toàn thị trường game di động giảm 7.2%, xuống còn 50.41 tỷ lượt3. Phân khúc Hyper-Casual, từng là bá chủ về lượt tải, là mảng duy nhất ghi nhận sự gia tăng về số lượt tải xuống, nhưng mô hình kinh doanh cốt lõi của nó lại đang sụp đổ3.  
Chi phí thu hút người dùng (User Acquisition \- CPI) trung bình đã tăng 30% chỉ trong một năm, chạm mức 0.56 USD trên toàn cầu và vọt lên 1.68 USD tại thị trường Bắc Mỹ3. Đối mặt với mức CPI cao nhất trong lịch sử, mô hình kinh doanh dựa hoàn toàn vào việc kiếm vài cent từ quảng cáo hiển thị trên mỗi người chơi (IAA) không còn khả thi3. Sự thắt chặt về biên lợi nhuận này đã buộc các nhà phát hành khổng lồ như Voodoo phải tuyên bố từ bỏ mô hình Hyper-Casual truyền thống, chuyển dịch toàn bộ đội ngũ sang phát triển Hybrid-Casual3. Thể loại Hybrid-Casual kết hợp vòng lặp cốt lõi (core loop) dễ hiểu, nhịp độ nhanh của Hyper-Casual với hệ thống tiến trình (meta-game) phức tạp và cơ chế kiếm tiền IAP (In-App Purchase) sâu sắc hơn của các dòng game Mid-core4. Sự chuyển dịch này là thông tin trọng yếu mà AI Agent cần nắm bắt để không đưa ra những lời khuyên lỗi thời cho người dùng khi họ muốn bắt đầu một dự án mới.  
Sự tập trung hóa doanh thu cũng là một rào cản lớn. Phân tích top 100 tựa game Casual có doanh thu cao nhất cho thấy sự thống trị tuyệt đối của các hệ sinh thái cũ: 73 trên 100 tựa game này thuộc về chỉ hai thể loại là Casino (41 tựa game) và Puzzle (32 tựa game)2. Gần một nửa trong số top 100 này được phát hành từ giai đoạn 2015 đến 2020, trong khi chỉ 11% là các tựa game ra mắt gần đây (2023-2025)2. Điều này minh chứng cho việc các tựa game khổng lồ không chỉ giữ vững vị thế mà còn liên tục phát triển các phương thức mới để gia tăng lợi nhuận, tạo ra một rào cản gia nhập thị trường khổng lồ đối với các studio nhỏ.

### **1.1. Phân Tích Cấu Trúc Các Thể Loại Dẫn Đầu Bảng Xếp Hạng**

Để AI Agent có khả năng đề xuất chính xác, hệ thống cần hiểu rõ đặc tính kỹ thuật và tài chính của từng tiểu thể loại. Gần 80% doanh thu toàn thị trường Casual tập trung vào Puzzle, Casino và Simulation2. Việc bóc tách từng nhánh nhỏ giúp Agent định hình được khoảng trống thị trường (Market Whitespace) và ước tính nguồn lực cần thiết.  
Bảng dữ liệu cấu trúc dưới đây phác thảo chi tiết các phân khúc thể loại, cung cấp cho LLM (Large Language Model) một góc nhìn định lượng để đối chiếu khi tương tác với người dùng:

| Thể Loại & Tiểu Thể Loại | Doanh Thu H1 2025 | Tốc Độ Tăng Trưởng (YoY) | Lượt Tải H1 2025 | Ví Dụ Tiêu Biểu | Nhận Định Dành Cho AI Agent |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Match-3 (Puzzle)** | 2.7 tỷ USD | Tăng 7% | 394 triệu (Giảm 17%) | Royal Match, Candy Crush Saga, Royal Kingdom2 | Rào cản gia nhập cực cao. Sự sụt giảm lượt tải nhưng doanh thu tăng cho thấy thị trường đã bão hòa và chỉ vắt kiệt tệp người dùng cũ. Không khuyến nghị cho studio nhỏ trừ khi có sự đột phá hoàn toàn về meta-game2. |
| **Merge (Đặc biệt là Complex Meta)** | 850 triệu USD | Tăng 62% | 287 triệu (Giảm 3%) | Gossip Harbor, Travel Town, Seaside Escape2 | Doanh thu trên mỗi lượt tải (RpD) tăng mạnh từ 3.2 USD lên 4.7 USD. Đòi hỏi khả năng xây dựng cốt truyện và hệ thống vật phẩm phức tạp2. |
| **Slots (Casino)** | 1.6 tỷ USD | Giảm 7% | 245 triệu (Giảm 8%) | Lightning Link Casino, Jackpot Party2 | Rủi ro pháp lý cao, cạnh tranh khốc liệt bằng ngân sách UA. Mức độ sáng tạo cơ học thấp, phụ thuộc hoàn toàn vào LiveOps và thuật toán xác suất2. |
| **Farming (Simulation)** | 560 triệu USD | Tăng 3% | 151 triệu (Giảm 10.5%) | Township, Hay Day, Family Island2 | Đòi hỏi thời gian phát triển dài (thường trên 1 năm) để tạo ra đủ khối lượng nội dung (content pipeline) giữ chân người chơi lâu dài2. |
| **Life Sim (Simulation)** | 80 triệu USD | Tăng 30% | 148 triệu (Giảm 3%) | BitLife, The Sims FreePlay2 | Đang là một ngách tăng trưởng tốt, đặc biệt ở các tựa game dựa trên văn bản (text-based) hoặc đồ họa tối giản, phù hợp cho ngân sách thấp. |

Bên cạnh các thể loại truyền thống, AI Agent cần được cập nhật về sự trỗi dậy của các dòng "Action Puzzle" hoặc "Sort Puzzle", điển hình là các tựa game như *Pixel Flow\!*, *Color Block Jam*, hoặc *Screw Puzzle*9. Trái ngược với triết lý thiết kế truyền thống của game Casual là loại bỏ hoàn toàn ma sát và áp lực, các studio indie như Loom Games (chỉ với 10 nhân sự) đã viết lại luật chơi bằng cách đưa "áp lực thực thi" (executional challenge) vào cốt lõi9.  
Trong các tựa game này, người chơi thất bại không phải do giới hạn nước đi (moves) ngẫu nhiên, mà do họ tính toán sai quỹ đạo hoặc phản xạ chậm. Sự minh bạch này tạo ra một vòng lặp tâm lý cực mạnh: người chơi nhận lỗi về mình và khát khao chơi lại9. Dữ liệu cho thấy các tựa game kiểu này có thể đạt trung bình 10 phiên chơi (sessions) mỗi ngày, giữ chân người dùng gần 1 giờ đồng hồ9. Quan trọng hơn, sự thất bại có ý nghĩa này giúp các gói "Fail offer" (trả tiền để hồi sinh) chiếm tới 27% tổng lượt mua IAP đầu tiên9. Đây là một "Micro-trend" (xu hướng vi mô) hoàn hảo mà AI Agent có thể đề xuất cho các nhà phát triển độc lập: chi phí sản xuất thấp, thiết kế tập trung vào sự rõ ràng của thị giác (visual clarity), và kiếm tiền tàng hình (invisible monetization) thông qua cảm xúc9.

### **1.2. Phân Tích Hệ Quy Chiếu Chỉ Số Giữ Chân Người Chơi (Retention Metrics)**

Một AI Agent thiết kế chuyên nghiệp không thể chỉ đánh giá thị trường thông qua tổng lượt tải. Tỷ lệ giữ chân (Retention) là hệ số nhân quyết định sự thành bại của chiến dịch User Acquisition (UA), định hình trực tiếp giá trị vòng đời khách hàng (LTV)12. Phân tích diện rộng từ GameAnalytics trên 11,600 tựa game cho thấy các mức chuẩn (benchmarks) thực tế thấp hơn rất nhiều so với những con số thường được thổi phồng trong các báo cáo tiếp thị12.  
Sự hiểu biết sâu sắc về các chỉ số này giúp AI Agent giải thích cho người dùng lý do tại sao một thể loại cụ thể lại rủi ro hoặc tiềm năng.

| Chỉ Số Đo Lường | Trung Vị (Median) Toàn Thị Trường | Top Quartile (25% Xuất Sắc Nhất) | Phân Tích Chuyên Sâu Dành Cho AI Agent |
| :---- | :---- | :---- | :---- |
| **Day-1 Retention (D1)** | 22% | 25-27% (Android) / 31-33% (iOS) | Phản ánh chất lượng hướng dẫn (onboarding) và sự trung thực của quảng cáo. Với trung vị 22%, gần 3/4 người chơi rời bỏ game trong 24 giờ đầu12. |
| **Day-7 Retention (D7)** | 3.4% \- 3.9% | 7% \- 8% | Đo lường khả năng hình thành thói quen (habit formation). Nếu D7 dưới 4%, vòng lặp cốt lõi (core loop) đang thất bại12. |
| **Day-30 Retention (D30)** | Dưới 3% (Trung bình Casual) | 3.5% \- 5% (Casual & Puzzle Android) | Đo lường chiều sâu nội dung (LiveOps, Meta-game). Việc nâng D30 từ 3.5% lên 5% có giá trị tương đương với việc giảm 30% chi phí CPI8. |

Đối với các nền tảng, iOS thường mang lại chỉ số Day-30 ROAS (Lợi tức chi tiêu quảng cáo sau 30 ngày) cao hơn hẳn. Cụ thể, trong phân khúc Casual, D30 ROAS trung bình trên iOS đạt 47%, so với chỉ 15% trên Android6. Tuy nhiên, Android lại có tỷ lệ cài đặt trên mỗi nghìn lượt hiển thị (IPM) cao hơn đáng kể6. AI Agent cần tích hợp các hằng số này vào logic suy luận để đưa ra lời khuyên về việc ưu tiên nền tảng nào khi soft-launch (ra mắt thử nghiệm) dựa trên ngân sách của người dùng.

## **2\. Chiến Lược Khai Thác Dữ Liệu Thị Trường Bằng Các API Và Công Cụ Miễn Phí (Data Ingestion Layer)**

Yêu cầu cốt lõi của dự án là xây dựng một hệ thống tối ưu hóa chi phí, ưu tiên tận dụng các tài nguyên miễn phí hoặc mã nguồn mở. Việc truy xuất dữ liệu từ Apple App Store và Google Play Store đối mặt với nhiều rào cản kỹ thuật khắt khe, bao gồm các cơ chế chống bot (Anti-bot), CAPTCHA, chặn IP (IP Rate Limiting), và sự thay đổi liên tục của cấu trúc HTML14. Để vượt qua, hệ thống cần kết hợp các Feed chính thống, thư viện Scraping nội bộ, và các nền tảng Data as a Service (DaaS) cung cấp gói Freemium.

### **2.1. Khai Thác Dữ Liệu Chính Thống: Apple iTunes RSS Feed Generator**

Đây là phương thức nền tảng hoàn toàn miễn phí, không bị giới hạn bởi bất kỳ cơ chế chống bot nào15. Apple cung cấp RSS Feed Generator trả về các danh sách Top Charts dưới định dạng JSON có cấu trúc sạch, cực kỳ dễ dàng để hệ thống n8n parse (bóc tách) trực tiếp thông qua HTTP Request Node17.  
Mặc dù giao diện web của công cụ này thường chỉ hiển thị 50 kết quả, kiến trúc hệ thống có thể điều chỉnh tham số URL theo cách thủ công để lấy tới 100 kết quả hoặc khai thác các endpoint định tuyến cũ để lấy tối đa 200 ứng dụng15.  
Cấu trúc URL chuẩn để khai thác dữ liệu từ Apple RSS như sau: https://rss.applemarketingtools.com/api/v2/{country}/apps/top-free/{limit}/apps.json15. Để đào sâu vào thể loại Games (Mã Genre ID là 36), hệ thống có thể sử dụng endpoint cổ điển nhưng vẫn hoạt động: https://itunes.apple.com/{country}/rss/topfreeapplications/limit=200/genre=36/json15.  
Phản hồi JSON sẽ cung cấp các siêu dữ liệu (metadata) cơ bản như Tên ứng dụng, ID (adamId), tên nhà phát triển, đường dẫn Icon, và phân loại thể loại15. Tuy nhiên, hạn chế cốt lõi của RSS Feed là nó không cung cấp số lượt tải xuống ước tính, doanh thu, hay các bài đánh giá chi tiết (Reviews) \- những dữ liệu sinh tử để LLM phân tích điểm yếu của đối thủ15. Do đó, Apple RSS chỉ nên đóng vai trò là "Công cụ Khám phá" (Discovery Tool) để lấy danh sách App IDs, trước khi chuyển giao cho các công cụ cào dữ liệu sâu hơn.

### **2.2. Khai Thác Bằng Mã Nguồn Mở: Thư Viện Scraper Dành Cho Google Play Và App Store**

Để lấy chi tiết cài đặt và bình luận từ Google Play mà không tốn chi phí API, hệ thống có thể tự lưu trữ (self-host) các kịch bản mã nguồn mở thông qua Node.js hoặc Python. Các thư viện phổ biến nhất bao gồm google-play-scraper (cho Node.js) và các bản port sang Python như gplay-scraper20.  
Các scraper này hoạt động bằng cách mô phỏng các truy vấn HTTP trực tiếp đến các endpoint nội bộ của Google Play Store, sau đó sử dụng biểu thức chính quy (Regex) để trích xuất các biến JSON được nhúng trong mã nguồn trang web20.  
Hệ thống có thể thiết lập các hàm cơ bản với các tham số cốt lõi:

* lang: Mã ngôn ngữ dựa trên chuẩn ISO 639-1 (ví dụ: en)20.  
* country: Mã quốc gia theo chuẩn ISO 3166 (ví dụ: us)20.  
* category: Bộ lọc danh mục, đối với Game Casual thường là mã GAME\_CASUAL hoặc ID thể loại tương ứng21.  
* collection: Lọc theo danh sách xếp hạng như TOP\_FREE, TOP\_PAID, hoặc TOP\_GROSSING21.

Đặc biệt, thư viện mã nguồn mở Mohammedcha/gplay-scraper trên Python cung cấp tính năng vượt qua bộ lọc HTTP tĩnh bằng cách hỗ trợ các HTTP client nâng cao như curl\_cffi hoặc tls-client, giúp mô phỏng chính xác dấu vân tay (fingerprint) của trình duyệt thật, giảm thiểu rủi ro bị chặn IP khi cào hàng loạt22.  
Chức năng quan trọng nhất của các thư viện này là phương thức trích xuất Reviews (reviews method). Dữ liệu này chứa reviewId, rating, text, version, và lịch sử trả lời của nhà phát triển, hỗ trợ phân trang để lấy hàng ngàn bình luận21. Việc triển khai các thư viện này dưới dạng các micro-services gọi thông qua Command Line (CLI) hoặc HTTP endpoints nội bộ sẽ giúp hệ thống n8n truy xuất dữ liệu liên tục với chi phí bằng không.

### **2.3. Các Nền Tảng Scraping DaaS Hỗ Trợ Gói Freemium Khả Dụng**

Khi hệ thống cần tự động hóa quy mô lớn, việc tự quản lý Proxy và sửa lỗi cấu trúc HTML thay đổi liên tục sẽ tiêu tốn quá nhiều tài nguyên bảo trì. Tích hợp các dịch vụ Data as a Service (DaaS) thông qua các gói Freemium hào phóng là giải pháp bền vững nhất cho kiến trúc n8n.  
Bảng dưới đây đánh giá chi tiết các nền tảng cung cấp API có thể tích hợp trực tiếp:

| Nền Tảng DaaS | Chính Sách Miễn Phí (Freemium) | Tính Năng Nổi Bật & Tích Hợp Vào AI Agent |
| :---- | :---- | :---- |
| **Apify (Google Play Scraper)** | Tặng 5 USD tín dụng sử dụng miễn phí mỗi tháng28. Khả năng trích xuất hàng ngàn kết quả/tháng28. | Cung cấp sẵn các "Actor" (kịch bản cấu hình trước) duy trì bởi cộng đồng. Trả về cấu trúc JSON cực kỳ phẳng, lý tưởng cho Webhook của n8n27. Chứa tới 14 trường dữ liệu đánh giá chi tiết27. |
| **ScrapingBee** | 1,000 API credits ban đầu miễn phí29. Gói Hobby giá 19 USD/tháng nếu mở rộng29. | Tích hợp công nghệ AI Web Scraping. Cho phép trích xuất dữ liệu bằng ngôn ngữ tự nhiên (Prompt-based extraction) thay vì phải bảo trì CSS selectors. Hệ thống tự xử lý JavaScript rendering và xoay vòng Stealth Proxy29. |
| **Scrapeless** | Tích hợp module trực tiếp vào n8n, chi phí siêu rẻ (chỉ 0.1 USD/1,000 requests) sau thời gian dùng thử14. | Chuyên giải quyết các thuật toán chống Scraping phức tạp (CAPTCHA, IP Rate Limiting). Cung cấp sẵn AI scraper Node trong hệ sinh thái n8n, cho phép xây dựng luồng cào dữ liệu nhanh chóng mà không cần code14. |
| **SocialCrawl** | Cấp 100 tín dụng miễn phí không hết hạn. Phí 5 tín dụng/lượt gọi chi tiết32. | Điểm mạnh tuyệt đối là khả năng truy xuất chéo cả Apple App Store và Google Play chung một cấu trúc chuẩn hóa (Shared Schema). Đặc biệt, hệ thống hoàn tiền (refund) tín dụng nếu truy vấn không trả về kết quả32. |
| **SerpApi** | 250 lượt tìm kiếm miễn phí mỗi tháng34. | Tập trung vào dữ liệu kết quả tìm kiếm (SERP). Phù hợp để AI Agent theo dõi thứ hạng từ khóa ASO (App Store Optimization), phân tích mức độ cạnh tranh của các từ khóa Casual Game33. |
| **AppTweak API** | 100,000 tín dụng trong 7 ngày dùng thử35. | Đây là nguồn Intelligence dữ liệu giá trị nhất. Khác với các công cụ trên, AppTweak cung cấp ước tính Doanh thu (Revenue) và Lượt tải (Downloads) theo thời gian thực35. Hoàn hảo cho việc cào dữ liệu quy mô lớn trong tuần đầu tiên để thiết lập cơ sở dữ liệu nền cho AI Agent. |

## **3\. Kiến Trúc Tự Động Hóa Và Trí Tuệ Nhân Tạo: So Sánh n8n, Dify và CrewAI**

Để vận hành một công cụ phân tích thị trường tự động, hệ thống cần một kiến trúc phân tách rõ ràng giữa Lớp Điều Phối Tự Động Hóa (Orchestration Layer) và Lớp Suy Luận Trí Tuệ (Cognitive Layer). Trên thị trường hiện nay, n8n, Dify và CrewAI là ba nền tảng mã nguồn mở mạnh mẽ nhất, nhưng mỗi nền tảng được thiết kế cho những mô thức (paradigms) hoàn toàn khác biệt36. Việc hiểu rõ sự khác biệt này quyết định tính khả thi của dự án.

* **CrewAI (Code-First, Multi-Agent):** CrewAI là một framework được viết bằng Python, thiết kế chuyên biệt để mô phỏng một "tổ chức" gồm nhiều AI Agent làm việc song song (ví dụ: một Agent chuyên thu thập dữ liệu, một Agent viết báo cáo, một Agent duyệt lại)36. Nó xuất sắc trong việc phân chia phân cấp (hierarchical delegation) và phối hợp nhóm38. Tuy nhiên, CrewAI yêu cầu kỹ năng lập trình Python sâu sắc, thiếu giao diện trực quan cho luồng công việc, và việc kết nối các API bên ngoài như Google Sheets hay Database đòi hỏi tự viết code thủ công38. Hơn nữa, kiến trúc nhiều Agent giao tiếp liên tục dễ dẫn đến bùng nổ chi phí token LLM38.  
* **n8n (Automation-First):** Xuất phát điểm là nền tảng tự động hóa thay thế Zapier, n8n xem Workflow (Luồng công việc) là trung tâm, AI chỉ là một Node công cụ (step) bên trong luồng đó36. Điểm mạnh vô song của n8n là khả năng tích hợp sẵn hơn 400 dịch vụ (Slack, Google Sheets, Postgres, API HTTP) thông qua giao diện kéo thả trực quan38. Nó lý tưởng cho việc thiết lập các tác vụ định kỳ (Cron), xử lý phân tách dữ liệu (Data Parsing), và gửi yêu cầu hàng loạt (Spidering) đến các công cụ Scraping40.  
* **Dify (AI-First, RAG & LLMOps):** Dify sinh ra để phục vụ việc phát triển các ứng dụng AI tương tác. Nó cung cấp giao diện quản lý Prompt xuất sắc, hệ thống cơ sở dữ liệu Vector tích hợp sẵn cho RAG (Retrieval-Augmented Generation), và đặc biệt là giao diện Chatbot UI hoàn thiện để người dùng cuối tương tác ngay lập tức mà không cần tự code Front-end37. Dify cho phép Agent chủ động gọi các công cụ (Function Calling / Skills) dựa trên ý định của người dùng39.

**Đề Xuất Kiến Trúc Kết Hợp (Hybrid Architecture): n8n \+ Dify** Để tối ưu hóa chi phí và hiệu năng, chiến lược tốt nhất là sử dụng kết hợp n8n và Dify thông qua các giao thức kết nối tiêu chuẩn như REST API hoặc Model Context Protocol (MCP)37.  
Trong mô hình này:

> 1. **n8n đóng vai trò là "Hệ thần kinh ngoại biên":** Chịu trách nhiệm chạy các lịch trình tự động để gọi các API Scraping (như Apify, Apple RSS), nhận dữ liệu JSON thô, làm sạch, và đẩy vào một kho dữ liệu trung tâm (Data Warehouse) hoặc Google Sheets38.  
> 2. **Dify đóng vai trò là "Bộ não trung tâm" và Giao diện:** Cung cấp Chatbot cho người dùng cuối. Khi người dùng đặt câu hỏi, AI Agent bên trong Dify sẽ suy luận, gọi các API kích hoạt n8n để lấy dữ liệu thời gian thực, hoặc truy xuất kho kiến thức RAG để tổng hợp báo cáo39. Sự phân chia này giúp hệ thống vận hành cực kỳ ổn định, dễ dàng gỡ lỗi, và quan trọng nhất là có thể triển khai cục bộ (Self-hosted) hoàn toàn miễn phí trên Docker39.

## **4\. Thiết Kế Chi Tiết Luồng Tự Động Hóa Dữ Liệu Trên n8n (Data Pipeline)**

Việc thiết lập một luồng Scraping hoàn chỉnh trên n8n không yêu cầu viết mã backend, mà sử dụng tư duy định tuyến dữ liệu. Một quy trình trích xuất dữ liệu thị trường Game Casual tiêu chuẩn sẽ vận hành qua các Node sau:

> 1. **Schedule Trigger Node:** Thiết lập chạy hệ thống hàng tuần vào rạng sáng để quét các bảng xếp hạng mới nhất, đảm bảo tính cập nhật của xu hướng40.  
> 2. **HTTP Request Node (Discovery):** Gọi đến endpoint RSS của Apple App Store hoặc API của SerpApi để yêu cầu danh sách Top 100 tựa game Casual tải nhiều nhất. Cấu hình Node yêu cầu xác thực bằng Header (nếu dùng API bên thứ ba) và xử lý phân trang tự động nếu cần15. Phản hồi nhận được là một cục JSON lớn chứa metadata15.  
> 3. **Code Node / Item Lists Node (Data Extraction):** Chạy một đoạn mã JavaScript siêu nhỏ hoặc dùng Item Lists Node để bóc tách mảng JSON, trích xuất ra một danh sách thuần túy các App IDs (ví dụ: com.rovio.baba, com.dreamgames.royalmatch). Node này sẽ phân tách luồng dữ liệu (Split In Batches) để hệ thống xử lý từng game một cách tuần tự, tránh tình trạng Rate Limit27.  
> 4. **HTTP Request Node (Deep Scrape / Spidering):** Đối với mỗi App ID, n8n tiếp tục gửi một POST Request kèm theo Payload chứa appId đến các nền tảng như Apify (Google Play Reviews Scraper) hoặc Scrapeless14. Node này được cấu hình trích xuất khoảng 100-200 bài đánh giá mới nhất, kèm theo chỉ số đánh giá sao, và số lượt cài đặt.  
> 5. **Data Warehouse Integration Node (Google Sheets/PostgreSQL):** Sau khi nhận lại dữ liệu đánh giá chi tiết (bao gồm 14 trường định dạng sạch như reviewId, rating, text, userName, version) từ Apify, n8n sử dụng Google Sheets Node (với lệnh Append Row) để lưu trữ cấu trúc thành một cơ sở dữ liệu bảng tính27. Dữ liệu này sẽ trở thành mỏ vàng để AI Agent phân tích.

## **5\. Phát Triển Khung Suy Luận Cho AI Agent Trên Dify**

Giai đoạn cuối cùng là trang bị khả năng suy luận logic cho AI Agent trên nền tảng Dify, biến nó từ một bộ máy tìm kiếm đơn thuần thành một "Nhà phân tích thị trường kỹ thuật số" có khả năng đưa ra khuyến nghị thực chiến.

### **5.1. Xử Lý Ngôn Ngữ Tự Nhiên Và Phân Tích Đánh Giá (Review Analytics)**

Hàng ngàn bài đánh giá trên Google Play chứa thông tin sống còn về lý do tại sao người chơi từ bỏ game (liên quan đến Day-1, Day-7 retention) hoặc điều gì làm họ bực bội (pain-points)2. Tuy nhiên, dữ liệu thô chứa đầy các bình luận vô nghĩa (ví dụ: "Game hay", "Lag quá", các biểu tượng cảm xúc). Nếu nhồi nhét toàn bộ vào LLM, hệ thống sẽ cạn kiệt Token và gặp ảo giác (Hallucination).  
Kiến trúc hệ thống giải quyết vấn đề này bằng một khung sàng lọc thông minh thông qua các LLM chi phí thấp nhưng tốc độ cao (như GPT-4o-mini). Dựa trên các nghiên cứu khoa học máy tính về phân tích cảm xúc (Sentiment Analysis) ứng dụng trên App Store, quy trình lọc diễn ra qua cấu trúc Prompt thiết kế đặc biệt (Prompt Engineering)47:  
Agent sử dụng kỹ thuật Few-Shot Prompting, đưa vào khoảng 10 ví dụ (5 informative, 5 non-informative) để huấn luyện LLM phân loại47. Một đánh giá được giữ lại (Informative) khi nó chứa các yếu tố:

* Vấn đề về cân bằng game (Game Balance): "Sau level 50, độ khó tăng phi lý, bắt buộc phải mua gói hỗ trợ".  
* Vấn đề về luồng trải nghiệm (UX/Ads): "Quảng cáo xen kẽ xuất hiện quá dày, mỗi 30 giây làm gián đoạn nhịp chơi".  
* Yêu cầu tính năng (Feature Requests): "Cần thêm bảng xếp hạng bạn bè để cạnh tranh".

Những đánh giá chất lượng này sau đó được tổng hợp lại để Agent lập bản đồ các khiếm khuyết của đối thủ, cung cấp nguyên liệu thô để nhà phát triển tạo ra cơ chế game tốt hơn47.

### **5.2. Khung Đánh Giá Khả Thi Và Ra Quyết Định Của Agent**

Khi người dùng nhập yêu cầu vào giao diện Web/Chatbot của Dify (ví dụ: *"Đội ngũ của tôi có 3 người, ngân sách UA dưới 1,000 USD/tháng, tôi nên làm thể loại Casual nào để tối ưu doanh thu?"*), Agent sẽ kích hoạt các Tools (gọi đến n8n để lấy dữ liệu) và thực hiện quá trình suy luận đa chiều dựa trên các nguyên tắc thiết lập sẵn39:

> 1. **Đánh Giá Rào Cản Gia Nhập (Barrier to Entry):** Agent nhận diện rằng các thể loại Match-3 hay Slots có doanh thu khổng lồ, nhưng CPI cực đắt đỏ và thị trường bị thâu tóm bởi vài ông lớn2. Nó sẽ cảnh báo người dùng tránh xa các thể loại này nếu ngân sách thấp, bất chấp tỷ lệ giữ chân (Retention) có vẻ hấp dẫn6.  
> 2. **Khai Thác Khoảng Trống Micro-Trend:** Dựa trên dữ liệu cập nhật về các tựa game đột phá như *Pixel Flow* hay *Color Block Jam*, Agent sẽ đề xuất thể loại "Action Puzzle" hoặc "Sort Puzzle"9. Agent lập luận rằng các thể loại này có chi phí sản xuất thấp, cơ chế minh bạch giúp giảm sự ức chế phi lý, và tạo ra chu kỳ chơi ngắn nhưng lặp lại liên tục (10 sessions/day)9.  
> 3. **Tối Ưu Hóa Chiến Lược Kiếm Tiền (Monetization Overlay):** Agent định hướng người dùng tích hợp vòng lặp kinh tế phù hợp với từng thể loại. Ví dụ, nếu phát triển Hybrid-Casual, thay vì lạm dụng quảng cáo xen kẽ (Interstitial Ads) gây sụt giảm mạnh Retention Day-1, Agent sẽ đề xuất tập trung thiết kế các "Fail states" (trạng thái thất bại) có ý nghĩa để thúc đẩy người chơi xem quảng cáo tặng thưởng (Rewarded Video) hoặc mua các gói "Fail offer" giá rẻ (chiếm 27% tỷ lệ mua lần đầu)6.

Để luồng giao tiếp giữa Dify và n8n diễn ra liền mạch, dữ liệu trao đổi được định dạng bằng cấu trúc JSON thống nhất38. Dify gửi Payload yêu cầu (bao gồm Action, Category, Limit) đến Webhook của n8n, sau đó nhận lại mảng dữ liệu đã làm sạch. LLM trong Dify sẽ biên dịch các dữ liệu máy móc này thành một bản phân tích chiến lược hoàn chỉnh bằng ngôn ngữ tự nhiên, đáp ứng chính xác nhu cầu nghiên cứu thị trường phức tạp của người dùng với chi phí vận hành gần như bằng không.

#### **Nguồn trích dẫn**

> 1. Securing a Leading Edge in the Booming AI Casual Games Market, [https://eu.36kr.com/en/p/3940348556180608](https://eu.36kr.com/en/p/3940348556180608)  
> 2. Casual Games Report H1 2025: Three Genres Generating 80% of, [https://appmagic.rocks/research/casual-report-h1-2025](https://appmagic.rocks/research/casual-report-h1-2025)  
> 3. Hyper-Casual Games in 2026: What They Are & How to Profit, [https://www.innovecsgames.com/blog/hyper-casual-games/](https://www.innovecsgames.com/blog/hyper-casual-games/)  
> 4. Complete Guide to Making Profitable Hyper-Casual Games, [https://kevurugames.com/blog/the-complete-guide-to-making-profitable-hyper-casual-games-design-tips-rates-and-upcoming-trends/](https://kevurugames.com/blog/the-complete-guide-to-making-profitable-hyper-casual-games-design-tips-rates-and-upcoming-trends/)  
> 5. Finding Genre Success: the Case of Gossip Harbor, [https://www.deconstructoroffun.com/blog/2024/8/19/finding-genre-success-the-case-of-gossip-harbor](https://www.deconstructoroffun.com/blog/2024/8/19/finding-genre-success-the-case-of-gossip-harbor)  
> 6. 2025 Casual Gaming Apps Report \- Liftoff, [https://liftoff.ai/2025-casual-gaming-apps-report/](https://liftoff.ai/2025-casual-gaming-apps-report/)  
> 7. Royal Match: Dream Games' Regal Performance \- Naavik, [https://naavik.co/deep-dives/royal-match/](https://naavik.co/deep-dives/royal-match/)  
> 8. Gamification Benchmarks 2026: What's a Good Retention Rate, [https://www.xtremepush.com/blog/gamification-benchmarks-2026-whats-a-good-retention-rate-engagement-score-and-tier-progression](https://www.xtremepush.com/blog/gamification-benchmarks-2026-whats-a-good-retention-rate-engagement-score-and-tier-progression)  
> 9. Pixel Flow và Sự Trỗi Dậy Của Sort Puzzle: Khi Một Studio 10 Người, [https://naocavang.org/2026/04/13/pixel-flow-va-su-troi-day-cua-sort-puzzle-khi-mot-studio-10-nguoi-viet-lai-luat-choi/](https://naocavang.org/2026/04/13/pixel-flow-va-su-troi-day-cua-sort-puzzle-khi-mot-studio-10-nguoi-viet-lai-luat-choi/)  
> 10. 25gamers.com: NO BS Content from two & a half gamers, [https://25gamers.com/](https://25gamers.com/)  
> 11. Top 5 Hybrid-Casual Games on iOS in Portugal: Q2 2025, [https://sensortower.com/blog/2025-q2-ios-top-5-hybridcasual%20games-units-pt-642f199ae1714cfff12984cb](https://sensortower.com/blog/2025-q2-ios-top-5-hybridcasual%20games-units-pt-642f199ae1714cfff12984cb)  
> 12. Mobile Game Retention 2026: What the Benchmarks Really Say | GGA, [https://gamegrowthadvisor.com/blog/2026-03-17-mobile-game-retention-strategies-2026/](https://gamegrowthadvisor.com/blog/2026-03-17-mobile-game-retention-strategies-2026/)  
> 13. Mobile Game Retention Strategies: The Complete 2026 Guide, [https://hubapps.team/blog/mobile-game-retention-strategies](https://hubapps.team/blog/mobile-game-retention-strategies)  
> 14. How to Scrape Google Play Store App in Python \- Scrapeless, [https://www.scrapeless.com/en/blog/scrape-google-play-store](https://www.scrapeless.com/en/blog/scrape-google-play-store)  
> 15. App Store top chart data \#2 \- tweaselORG/parse-tunes \- GitHub, [https://github.com/tweaselORG/parse-tunes/issues/2](https://github.com/tweaselORG/parse-tunes/issues/2)  
> 16. Marketing Resources & Tools \- Apple Services Performance Partners, [https://performance-partners.apple.com/tools](https://performance-partners.apple.com/tools)  
> 17. Convert Any RSS Feed into JSON \- RSS.app, [https://rss.app/tools/rss-to-json](https://rss.app/tools/rss-to-json)  
> 18. RSS Information \- Apple (CA), [https://www.apple.com/ca/rss/](https://www.apple.com/ca/rss/)  
> 19. Search Apple App store by genre with iOS/Obj-c \- Stack Overflow, [https://stackoverflow.com/questions/13833521/search-apple-app-store-by-genre-with-ios-obj-c](https://stackoverflow.com/questions/13833521/search-apple-app-store-by-genre-with-ios-obj-c)  
> 20. GitHub \- JoMingyu/google-play-scraper, [https://github.com/jomingyu/google-play-scraper](https://github.com/jomingyu/google-play-scraper)  
> 21. blues-lab/google-play-scraper-py \- GitHub, [https://github.com/blues-lab/google-play-scraper-py](https://github.com/blues-lab/google-play-scraper-py)  
> 22. GPlay Scraper is a powerful Python Google Play scraper library for, [https://github.com/Mohammedcha/gplay-scraper](https://github.com/Mohammedcha/gplay-scraper)  
> 23. MrAdex77/google-play-scraper \- GitHub, [https://github.com/MrAdex77/google-play-scraper](https://github.com/MrAdex77/google-play-scraper)  
> 24. Simple Google Play Store scraper \- GitHub, [https://github.com/digitalmethodsinitiative/google-play-scraper](https://github.com/digitalmethodsinitiative/google-play-scraper)  
> 25. README.md \- digitalmethodsinitiative/google-play-scraper \- GitHub, [https://github.com/digitalmethodsinitiative/google-play-scraper/blob/master/README.md](https://github.com/digitalmethodsinitiative/google-play-scraper/blob/master/README.md)  
> 26. App Stores Scraper \- Apify, [https://apify.com/scraped\_org/app-stores-scraper](https://apify.com/scraped_org/app-stores-scraper)  
> 27. Google Play Reviews Scraper – App Ratings Data API \- Apify, [https://apify.com/webdatalabs/google-play-reviews-scraper](https://apify.com/webdatalabs/google-play-reviews-scraper)  
> 28. Google Play Scraper \- Apify, [https://apify.com/curious\_coder/google-play-scraper](https://apify.com/curious_coder/google-play-scraper)  
> 29. Google Play Scraper API | ScrapingBee, [https://www.scrapingbee.com/scrapers/google-play-scraper-api/](https://www.scrapingbee.com/scrapers/google-play-scraper-api/)  
> 30. AI Web Scraper API for Structured Data \- ScrapingBee, [https://www.scrapingbee.com/features/ai-web-scraping-api/](https://www.scrapingbee.com/features/ai-web-scraping-api/)  
> 31. Golang Guide | Build Your Google Play Store Scraper \- 2025 Detailed, [https://www.scrapeless.com/en/blog/google-play-store-scrape](https://www.scrapeless.com/en/blog/google-play-store-scrape)  
> 32. App Store API: iOS App, Review & Chart Data \- SocialCrawl, [https://www.socialcrawl.dev/platforms/app\_store](https://www.socialcrawl.dev/platforms/app_store)  
> 33. Best App Store & Google Play Review APIs (2026): Pricing Compared, [https://www.socialcrawl.dev/blog/best-app-review-apis-2026](https://www.socialcrawl.dev/blog/best-app-review-apis-2026)  
> 34. Google Play Store Scraper \- GitHub, [https://github.com/serpapi/google-play-scraper](https://github.com/serpapi/google-play-scraper)  
> 35. App Store & Google Play API: Access console & ASO data \- AppTweak, [https://www.apptweak.com/en/app-store-api](https://www.apptweak.com/en/app-store-api)  
> 36. CrewAI vs n8n: Key Differences and Which Platform Wins for AI Agents, [https://www.zenml.io/blog/crewai-vs-n8n](https://www.zenml.io/blog/crewai-vs-n8n)  
> 37. n8n vs. Dify: Choosing a Production AI Automation Platform, [https://n8n.io/vs/dify/](https://n8n.io/vs/dify/)  
> 38. n8n vs CrewAI: AI Agent Framework Comparison \- Peliqan, [https://peliqan.io/blog/n8n-vs-crewai/](https://peliqan.io/blog/n8n-vs-crewai/)  
> 39. n8n vs Dify: Which AI Agent Platform (2026) | SandBase Blog, [https://blog.sandbase.ai/n8n-vs-dify-2026/](https://blog.sandbase.ai/n8n-vs-dify-2026/)  
> 40. How To Build An Automated AI Web Scraper With n8n In 2026, [https://www.scrapingbee.com/blog/n8n-no-code-web-scraping/](https://www.scrapingbee.com/blog/n8n-no-code-web-scraping/)  
> 41. China Unicom's Yuanjing Wanwu Agent Platform is an ... \- GitHub, [https://github.com/UnicomAI/wanwu](https://github.com/UnicomAI/wanwu)  
> 42. How to set up Bright Data with Dify, [https://docs.brightdata.com/integrations/dify](https://docs.brightdata.com/integrations/dify)  
> 43. n8n vs Dify 2026: Which AI Workflow Tool Wins? \- AY Automate, [https://www.ayautomate.com/blog/n8n-vs-dify](https://www.ayautomate.com/blog/n8n-vs-dify)  
> 44. Web Scraping in Dify \- Decodo, [https://decodo.com/blog/web-scraping-in-dify](https://decodo.com/blog/web-scraping-in-dify)  
> 45. Dify \- open source AI workflow and agent building platform, 143K+, [https://www.aistarmap.com/en-US/aitool/dify](https://www.aistarmap.com/en-US/aitool/dify)  
> 46. Export Twitter Data to Google Sheets Automatically: Four Methods, [https://scrapebadger.com/blog/how-to-export-twitter-data-to-google-sheets-automatically](https://scrapebadger.com/blog/how-to-export-twitter-data-to-google-sheets-automatically)  
> 47. Understanding the Challenges and Promises of Developing ... \- arXiv, [https://arxiv.org/html/2506.16453v2](https://arxiv.org/html/2506.16453v2)  
> 48. Accessibility issues in Android apps: state of affairs, sentiments, and, [https://www.researchgate.net/publication/346040071\_Accessibility\_issues\_in\_Android\_apps\_state\_of\_affairs\_sentiments\_and\_ways\_forward](https://www.researchgate.net/publication/346040071_Accessibility_issues_in_Android_apps_state_of_affairs_sentiments_and_ways_forward)  
> 49. Mobile Game Monetization (2026): Models, Strategies & What, [https://hubapps.team/blog/mobile-game-monetization](https://hubapps.team/blog/mobile-game-monetization)