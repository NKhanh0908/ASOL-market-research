# MCP bản tin thị trường Casual Scout

Ngày: 2026-09-30. Trạng thái: **Chờ người dùng review spec bằng văn bản; chưa triển khai.**

## 1. Mục tiêu và quyết định

Casual Scout cung cấp dữ liệu để một AI bên ngoài phân tích thị trường rồi, ở giai đoạn sau, gửi bản tin qua Zalo/Telegram. Đợt này xây MCP server chỉ đọc. Không kết nối AI client, không gọi mô hình, không gửi thông báo.

Các quyết định người dùng đã chốt trong phiên:

- MCP chạy thành tiến trình HTTP riêng trên localhost.
- Một lần gọi bản tin chọn một thị trường và trả hai mục iOS/Android.
- Chỉ Top Free Casual; thị trường được phép: `vn, th, id, my, ph, sg, la, kh, us`.
- Top 10 luôn được đưa vào bản tin, gồm tăng, giữ nguyên và giảm hạng.
- Hạng 11–100 chỉ vào bản tin khi tăng hoặc giảm ít nhất 20 bậc/1 ngày hoặc 30 bậc/3 ngày.
- Game mới vào chart ngoài Top 10 không được coi là biến động mạnh khi không có delta chứng minh.
- Bản tin và truy vấn lịch sử dùng tối đa 7 ngày lịch liên tiếp, tính cả ngày đích.
- Ngày phân tích là UTC; thiếu dữ liệu ngày đích không thay bằng ngày cũ.

Spec này thay thế các mock sơ bộ `list_signals`/`list_noteworthy_games` trong hội thoại. Bộ công cụ cuối cùng ở mục 4 đáp ứng bản tin đã chốt. Không xuất gợi ý, điểm tiềm năng hoặc đánh giá AI nội bộ.

Liên quan: [gỡ AI nội bộ](2026-09-30-remove-internal-ai-design.md), [lưu dữ liệu 15 ngày](2026-09-30-data-retention-design.md), [PRD](../../prd/2026-09-10-casual-game-market-research-PRD.md). Yêu cầu nguồn, ngày, phân biệt rank/downloads, và thiếu dữ liệu của PRD tiếp tục áp dụng.

## 2. Phương án và kiến trúc

Đã cân nhắc: ghép MCP vào FastAPI web, server stdio, hoặc HTTP riêng. Chọn HTTP riêng theo phê duyệt của người dùng: kiểm thử độc lập, không khởi chạy scheduler/crawler/AI của web. Ghép vào web giảm số tiến trình nhưng kéo theo vòng đời và middleware hiện tại; stdio phù hợp client cục bộ nhưng không phải giao diện API được chọn.

Dùng [MCP Python SDK chính thức](https://py.sdk.modelcontextprotocol.io/) và Streamable HTTP, không tự viết giao thức MCP. [SDK hỗ trợ ứng dụng ASGI độc lập](https://py.sdk.modelcontextprotocol.io/run/asgi/). Chốt phiên bản SDK tương thích Python/dependencies khi lập kế hoạch, pin trong lockfile; không cài bản không giới hạn phiên bản.

Các đơn vị thiết kế, tên file dự kiến:

| Đơn vị | Trách nhiệm | Phụ thuộc |
|---|---|---|
| `mcp/server.py` | Đăng ký tools, output schema và lỗi MCP | SDK, dịch vụ đọc |
| `mcp/contracts.py` | Kiểu đầu vào/đầu ra có phiên bản | Pydantic |
| `market_brief/reader.py` | Đọc SQLite trong transaction nhất quán; chọn snapshot | Schema core hiện có |
| `market_brief/service.py` | Chọn game, tính delta, ghép lịch sử và provenance | Reader; hàm thuần |
| CLI `mcp-serve` | Khởi chạy server và đọc cấu hình đường dẫn/cổng | Server |

Luồng: tool → kiểm tra tham số → mở read transaction → chọn snapshot → tính dữ liệu bản tin → đóng transaction → trả structured JSON. Đọc cùng database core cho iOS/Android; không đọc Android archive như thể đó là chart core hiện tại.

MCP không gọi `Repository.initialize()` hoặc `web.create_app()`. Hiện các hàm này chạy migration, tạo AI schema hoặc khởi tạo worker. Database phải được chuẩn bị qua luồng quản trị của ứng dụng; MCP báo lỗi rõ nếu thiếu hoặc sai schema. Dùng SQLite read-only connection, không cho SQL/path tùy ý từ tool arguments. Toàn bộ bản tin của một call phải dùng cùng read transaction.

## 3. Chọn dữ liệu và tính biến động

### 3.1 Snapshot và thời gian

Phạm vi chart: Apple/iOS/`topfreeapplications`/genre `7003`, Google/Android/`top-free`/genre `GAME_CASUAL`, depth 100. Chỉ dùng snapshot `complete`; snapshot partial/invalid được báo trong coverage nhưng không thay snapshot hợp lệ.

Với mỗi ngày và mỗi nền tảng/thị trường: ưu tiên canonical snapshot khi nó khớp toàn bộ identity và ngày; nếu không có canonical hợp lệ, chọn snapshot complete mới nhất trong ngày, hòa thì theo ID ổn định. Tính so sánh chỉ giữa cùng provider/platform/country/collection/genre/depth/chart version. Nếu version hoặc phạm vi khác nhau, comparison là `incompatible_chart`.

Lịch sử 7 ngày là `T-6 ... T`, không phải 7 lần crawl. Delta 1 ngày so chính xác `T-1`, delta 3 ngày so chính xác `T-3`. Không thêm delta 7 ngày vì cần điểm T-7 nằm ngoài chuỗi 7 điểm đã chốt.

Lựa chọn thiết kế cho v1: `date` được chọn trong 7 ngày UTC gần nhất, gồm hôm nay; bỏ trống là hôm nay UTC. Điều này giữ toàn bộ lịch sử cần đọc trong cửa sổ lưu 15 ngày. Ngày tương lai hoặc cũ hơn phạm vi trả lỗi tham số. `generated_at` khác với `observed_at`; không dùng thời điểm gọi để đổi tuổi dữ liệu.

### 3.2 Quy tắc đưa game vào bản tin

`delta_kd = rank(T-k) - rank(T)`: số dương là tăng hạng, số âm là giảm.

- `top_10`: mọi game rank 1–10 trong snapshot đích, theo rank tăng dần.
- `strong_movers_outside_top_10`: game rank 11–100 có `abs(delta_1d) >= 20` hoặc `abs(delta_3d) >= 30`.
- Hai nhóm không trùng game; không gộp cùng tên giữa iOS và Android.
- Nhóm ngoài Top 10 sắp theo mức vượt ngưỡng lớn nhất `max(abs(delta_1d)/20, abs(delta_3d)/30)`, rồi rank hiện tại, rồi app ID. Bỏ nhánh delta null khi tính khóa sắp.
- Nếu hai mốc cho hướng ngược nhau, xuất cả hai delta và các điều kiện thỏa; không rút thành một nhãn tăng/giảm gây sai nghĩa.
- Game vắng khỏi chart hiện tại không có rank mới; không giả rank 101, không tính delta và không đưa vào nhóm game đang có hạng 11–100. `get_game_rank_history` vẫn giải thích được việc vắng khỏi tập quan sát.

`movement_1d` là `up`, `down`, `unchanged`, `new_entry` hoặc `unknown`. `unchanged` chỉ khi có hai rank hợp lệ và delta=0. `new_entry` cần snapshot T-1 complete, cùng identity và game vắng tại T-1. Nhãn này không có nghĩa mới phát hành. Các điều kiện tăng/giảm mạnh được xuất riêng trong `strong_moves`, không dùng một nhãn ưu tiên để mất thông tin.

Tính các delta và tiêu chí chọn bằng hàm thuần trên snapshot đã lưu, không chạy lại pipeline phân tích hoặc ghi kết quả vào DB. Không sao chép fallback của `web/views.py`, nơi thiếu phân tích có thể hiển thị `STEADY`. Không dùng điểm radar cũ để chọn game.

### 3.3 Thiếu dữ liệu

Mỗi điểm lịch sử có `rank` nullable và `status`: `observed`, `not_in_observed_chart`, `no_complete_snapshot`, `incompatible_chart`, `expired`.

- `not_in_observed_chart`: có chart complete nhưng không thấy game; không chứng minh game ngừng hoạt động.
- Thiếu mốc so sánh trả delta null với lý do; không trả 0.
- Thiếu T: nền tảng đó `unavailable`, hai danh sách rỗng, kèm nguyên nhân và thông tin ngày complete gần nhất nếu còn lưu. Nền tảng còn lại vẫn trả bình thường.
- Có T nhưng thiếu baseline: `data_status=available`, `comparison_status=partial` hoặc `unavailable`; vẫn trả Top 10.
- Không có game vượt ngưỡng: danh sách movers rỗng là kết quả hợp lệ, khác thiếu dữ liệu.

## 4. Hợp đồng MCP v1

Ba tools đều `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`, `openWorldHint=false`. Không cung cấp prompts, sampling, ghi shortlist, crawl, SQL tùy ý hoặc gọi AI. Tính idempotent xét cùng trạng thái kho dữ liệu; dữ liệu có thể đổi sau crawl/retention.

### `get_daily_market_brief(country, date?)`

`country` bắt buộc; chuẩn hóa chữ thường rồi kiểm tra danh sách chín thị trường. `date` ISO `YYYY-MM-DD` theo mục 3.1. Trả một response có `schema_version="market-brief.v1"`, `generated_at`, `country`, `date`, `date_timezone="UTC"`, `feed_type="top-free-casual"`, `history_days=7`, `rules_version="market-brief-selection.v1"`, và `platforms.ios`/`platforms.android`.

Mỗi mục nền tảng có:

- `data_status`, `comparison_status`, `warnings` với mã và thông điệp.
- `snapshots`: bản đồ ngày → provenance (snapshot ID, observed_at, source_updated nullable, provider, collection, genre, depth, chart version, quality, raw hash). Ngày thiếu có trạng thái tương ứng; không lộ đường dẫn máy chủ.
- `top_10`, `strong_movers_outside_top_10`, số lượng mỗi nhóm. Không phân trang vì tối đa 100 game/nền tảng, đã giới hạn theo chart.
- Mỗi game: `app_id`, `name`, `store_url`, `rank`, `rank_1d_ago`, `rank_3d_ago`, `delta_1d`, `delta_3d`, `movement_1d`, `comparison_1d`, `comparison_3d`, `strong_moves`, `rank_history` đủ 7 ngày. `strong_moves` gồm window, delta, direction, threshold; chỉ chứa điều kiện thỏa.
- Metadata gọn: developer và genre nguồn nếu có, metadata fetched_at; thiếu là null. Không đưa description dài, hình ảnh nhị phân, suy luận monetization, downloads ước đoán hoặc gợi ý phát triển.

Ví dụ mock của một game; ID/tên/số liệu chỉ minh họa:

```json
{
  "app_id": "com.example.puzzle",
  "name": "Sample Puzzle",
  "rank": 38,
  "rank_1d_ago": 70,
  "rank_3d_ago": 18,
  "delta_1d": 32,
  "delta_3d": -20,
  "movement_1d": "up",
  "comparison_1d": "available",
  "comparison_3d": "available",
  "strong_moves": [
    {"window_days": 1, "delta": 32, "direction": "up", "threshold": 20}
  ]
}
```

### `get_game_rank_history(country, platform, app_id, date?)`

`platform` là `ios`/`android`, app ID là chuỗi theo nền tảng, không suy nền tảng từ tên. Cùng cửa sổ ngày và cách chọn snapshot như bản tin. Luôn trả 7 điểm T-6..T, identity chart và provenance. Game vắng suốt cửa sổ trả `game_status="not_observed_in_window"`; không khẳng định ID không tồn tại trên store. Không mở rộng thành lịch sử 30 ngày.

### `get_coverage(country)`

Trả hai nền tảng và trạng thái chart cho 7 ngày UTC gần nhất; số dòng, quality, ngày complete gần nhất, phạm vi chart và trạng thái thiếu/expired nếu biết. Chỉ công bố các chart trong phạm vi MCP. Tool giúp phân biệt nguồn chưa có dữ liệu với một ngày không có biến động mạnh.

## 5. Vận hành, lỗi và biên truy cập

Lệnh dự kiến: `casual_scout mcp-serve --data-dir <path> --port 8003`. Bind cố định `127.0.0.1` ở v1, endpoint `/mcp`. Port có thể đổi; không hỗ trợ bind public/LAN trong spec này. Áp dụng kiểm tra Host/Origin cho loopback theo SDK; không bật CORS wildcard. Không tạo tài khoản/OAuth ở bản loopback; chỉ cho request từ máy cục bộ. Tích hợp từ cloud là spec sau.

Khởi động chỉ đọc cấu hình và DB, không tạo thư mục DB, không chạy migration/crawler/scheduler/retention. Thiếu DB hoặc thiếu schema bắt buộc: dừng với thông điệp quản trị cụ thể. Lỗi SQL, đường dẫn hoặc stack trace không được trả cho client.

Lỗi tham số/schema là lỗi MCP có cấu trúc (`INVALID_ARGUMENT`); kho bận sau timeout hữu hạn là `DATA_STORE_BUSY`; lỗi đọc là `DATA_STORE_ERROR`. Thiếu dữ liệu thị trường là kết quả nghiệp vụ bình thường, không phải lỗi giao thức. Logging server đi qua stderr, giới hạn/luân chuyển khi lưu file, không log toàn bộ response mặc định.

## 6. Nghiệm thu

1. MCP initialize/list_tools/call_tool hoạt động qua HTTP trên loopback với SDK test client; không cần cấu hình client cá nhân.
2. Một call VN trả iOS/Android riêng; cùng ID/tên không trộn nền tảng hoặc quốc gia. Grossing/genre khác/version khác không lọt vào phép so sánh.
3. Top 10 gồm delta dương/âm/0/null; rank 11 chỉ vào khi đạt ngưỡng. Biên ±19/±20 và ±29/±30 có kết quả đúng; không trùng giữa hai nhóm.
4. Hai cửa sổ trái chiều vẫn giữ cả delta; nhánh 3 ngày không cần 1 ngày có dữ liệu. NEW_ENTRY ngoài Top 10 không bị coi là delta mạnh.
5. Lịch sử có đúng 7 ngày UTC, bao gồm ngày thiếu. Không dùng T-2 thay T-1; không gán rank 101 hoặc STEADY giả.
6. Chọn canonical/mới nhất ổn định, xử lý partial-only, không có T và không có baseline đúng hợp đồng. Không tự lấy ngày cũ làm hôm nay.
7. Gọi tool không đổi bản ghi DB, không tạo DB mới, không khởi chạy worker và không gọi mạng ngoài. Kiểm tra Host/Origin và bind loopback.
8. Đọc đồng thời với crawl hoặc retention cho kết quả nhất quán trong một transaction, hoặc lỗi bận có kiểm soát; không trả bản tin ghép nửa trước/nửa sau xóa.
9. Mock integration fixture phủ cả hai nền tảng và chín mã quốc gia; kiểm thử schema/version, ngày ngoài phạm vi và JSON unicode.

## 7. Bàn giao và phụ thuộc

MCP có thể triển khai độc lập trước hai spec còn lại. Retention không chạy bên trong MCP; source reader phải chịu được dữ liệu đã hết hạn. Các file AI đang có thay đổi chưa commit không được gộp vào commit spec hoặc MCP. Sau khi review spec, lập implementation plan riêng; chưa có cam kết test nào đã chạy cho tính năng này.
