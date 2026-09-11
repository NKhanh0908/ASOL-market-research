# Nghiên cứu: AI Agent/n8n để phát hiện Trend Game Casual

## Mục tiêu
Xây dựng một agent tự động (n8n + AI) chuyên **phát hiện game/trend đang nổi** trong thị trường game casual, ưu tiên sử dụng **nguồn dữ liệu miễn phí**.

---

## 1. Các mục tiêu nghiên cứu thị trường game casual có thể có

| Mục tiêu | Mô tả |
|---|---|
| **Trend spotting** (đã chọn) | Phát hiện game/gameplay mechanic đang nổi qua top chart, viral trên mạng xã hội |
| Competitor tracking | Theo dõi đối thủ cụ thể: update, doanh thu ước tính, review, ads đang chạy |
| Idea validation | Đánh giá tiềm năng của một ý tưởng game mới |
| Keyword/ASO research | Nghiên cứu từ khóa để tối ưu App Store/Google Play |

---

## 2. Nguồn dữ liệu miễn phí

| Nguồn | Cho biết gì | Cách lấy trong n8n | Ghi chú |
|---|---|---|---|
| **App Store RSS Feed** | Top chart theo ngày, theo quốc gia/category | `HTTP Request` gọi endpoint công khai: `https://rss.applemarketingtools.com/api/v2/vn/apps/top-free/100/apps.json` | Ổn định, hợp lệ 100%, không lo bị block. Chỉ có rank, không có download/revenue. |
| **Google Play** | Top chart, chi tiết app | `Code node` chạy npm package `google-play-scraper` | Không có RSS chính thức như Apple → dễ bị rate-limit, nên giới hạn tần suất gọi (1 lần/ngày) |
| **TikTok Creative Center** | Hashtag/âm nhạc/UGC ads đang viral liên quan tới game | `HTTP Request` tới endpoint public (không chính thức) | Endpoint có thể đổi bất kỳ lúc nào → cần xử lý lỗi (error handling) riêng |
| **Reddit** (r/AppBusiness, r/gamedev, r/AndroidGaming...) | Cộng đồng bàn luận về game/mechanic mới | Reddit API (OAuth app, free tier) | Ổn định, chính thức |
| **Google Trends** | So sánh mức độ tăng trưởng "độ hot" của tên game/mechanic theo thời gian | Scrape trực tiếp trends.google.com hoặc community node, hoặc SerpAPI (free tier giới hạn) | Không chính thức, có rủi ro thay đổi |
| **YouTube Data API v3** | Video gameplay/review nào đang viral | API chính thức, free quota 10.000 unit/ngày | Đủ dùng cho tần suất theo dõi hàng ngày |

**Ghi chú quan trọng:** vì không dùng Sensor Tower/data.ai (trả phí), agent sẽ **không có số liệu doanh thu hoặc download thực tế** — chỉ suy luận độ "hot" của game qua thay đổi thứ hạng + mức độ thảo luận trên mạng xã hội. Đây là giới hạn cần chấp nhận khi đi hướng miễn phí.

---

## 3. Thiết kế workflow n8n

```
[Schedule Trigger: chạy 1 lần/ngày, ví dụ 8h sáng]
        │
        ▼
[HTTP Request: lấy top chart từ App Store RSS Feed]
        │
        ▼
[Code node: parse dữ liệu, chuẩn hóa (tên game, rank, category)]
        │
        ▼
[Lưu trữ: Google Sheets / n8n Data Store — lưu snapshot rank mỗi ngày]
        │
        ▼
[Code node: so sánh với snapshot hôm trước → tính delta rank]
        │
        ▼
[Filter node: chỉ giữ game mới vào top 100 hoặc tăng >20 bậc trong 3 ngày]
        │
        ▼
[HTTP Request: lấy thêm mô tả + screenshot của các game "đáng chú ý"]
        │
        ▼
[(Tùy chọn) HTTP Request: search tên game trên Reddit/YouTube xem có đang được bàn tán]
        │
        ▼
[AI Agent node (Claude): phân tích core mechanic, art style,
 monetization (IAP/ads), điểm khác biệt, lý do có thể đang trend]
        │
        ▼
[Code node: tổng hợp kết quả, format thành báo cáo Markdown]
        │
        ▼
[Gửi báo cáo: Slack / Telegram / Notion / Google Sheets]
```

### Vai trò của AI Agent trong workflow
Node **AI Agent** trong n8n (kiểu LangChain) cho phép:
- Gắn nhiều "tool" để AI tự quyết định gọi (vd: tool tra top chart, tool phân tích ASO, tool search web)
- AI tự lên kế hoạch nghiên cứu thay vì workflow tuyến tính cứng
- Trả lời được câu hỏi ad-hoc, không chỉ báo cáo định kỳ (vd: "game X đang hot vì sao?")

---

## 4. Lưu ý thực tế khi triển khai

- **App Store RSS**: nguồn ổn định nhất, nên dùng làm xương sống của hệ thống.
- **Google Play scraping**: cần cache dữ liệu, tránh gọi quá thường xuyên để không bị chặn IP.
- **TikTok/Google Trends scraping**: là endpoint không chính thức, cần có bước try/catch hoặc Error Trigger riêng để một nguồn lỗi không làm gãy toàn bộ workflow.
- **Giới hạn dữ liệu**: không có số liệu doanh thu/download chính xác — chỉ ước lượng độ hot qua rank + mức thảo luận xã hội.
- **Tần suất chạy**: 1 lần/ngày là hợp lý để cân bằng giữa việc bắt kịp trend và tránh bị rate-limit từ các nguồn scraping.

---
