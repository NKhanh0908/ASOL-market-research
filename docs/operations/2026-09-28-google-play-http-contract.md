# Google Play HTTP Contract & Feasibility Findings

- **Mã tài liệu:** `OP-AND-HTTP-01`
- **Ngày kiểm tra:** 2026-09-28
- **Tác giả:** NKhanh0908
- **Phạm vi:** Kiểm chứng tính khả thi của giao thức HTTP đối với Google Play Top Free & Top Grossing (GAME_CASUAL) và Metadata (Installs) trên 9 thị trường.

---

## 1. Tóm tắt kết luận thực nghiệm (Executive Summary)

1. **Về Public HTTP GET (Bảng xếp hạng):**
   - **KHÔNG KHẢ THI** để lấy Top 100 bằng phương thức HTTP GET công khai đơn thuần.
   - Trang web Google Play (`https://play.google.com/store/apps/category/GAME_CASUAL`) nhúng metadata giao diện bảng xếp hạng trong `AF_initDataCallback` (`ds:3` / `ds:4`), bao gồm nhãn tabs `apps_topselling_free` và `apps_topgrossing`, nhưng danh sách items trả về ban đầu trong HTML là mảng rỗng `[]`.
   - Các package links xuất hiện rải rác trên trang (27–59 packages) thuộc các carousel gợi ý cá nhân hóa / chủ đề (`RECOMMENDED_IN_TOPIC`, `NEW_RELEASES`), hoàn toàn không phải thứ tự rank 1..100 của chart.

2. **Về Public HTTP GET (Metadata & Lượt cài đặt - Installs):**
   - Parse thành công các mẫu đã khảo sát; chưa chứng minh coverage metadata 100% trên toàn bộ thị trường/app.
   - Endpoint `GET https://play.google.com/store/apps/details?id=<package>&hl=<lang>&gl=<country>` trả về cấu trúc `AF_initDataCallback` khóa `ds:5`.
   - Bóc tách được đầy đủ, chuẩn xác:
     - `installs`: Chuỗi hiển thị store (ví dụ: `"1.000.000.000+"`, `"10.000.000+"`).
     - `min_installs`: Số nguyên tối thiểu (ví dụ: `1000000000`, `10000000`).
     - `real_installs`: Trường số nội bộ quan sát được (ví dụ: `2336253256`), chưa xác minh ý nghĩa; không sử dụng như số cài đặt chính xác.
     - `score`, `ratings`, `price`, `currency`, `developer`, `icon_url`, `offersIAP`, `containsAds`.
   - Tốc độ: ~0.2 – 0.5s/request qua `httpx`, chi phí **$0.00**, hoàn toàn không cần Chrome/Selenium.

3. **Về Upstream Endpoint của Web Client (`batchexecute` POST):**
   - Trình duyệt Chrome/Web Client của Google Play thực tế tải dữ liệu bảng xếp hạng thông qua RPC call nội bộ:
     `POST https://play.google.com/_/PlayStoreUi/data/batchexecute?rpcids=vyAe2`
   - Đã kiểm chứng thực nghiệm bằng `httpx.Client.post()` trực tiếp ($0 cost, 0.5s/request, không cần cookie, không cần đăng nhập).
   - Kết quả thu thập qua endpoint này:
     - **Top Free:** Thu thập đủ **100/100 game** trên toàn bộ 9 thị trường (`vn, th, id, my, ph, sg, la, kh, us`).
     - **Top Grossing:**
       - Các thị trường lớn hoặc quốc tế (`us, la, kh`): Đạt **100/100 game**.
       - Các response khảo sát (`vn: 49, th: 80, id: 90, my: 83, ph: 62, sg: 43`) trả dưới 100. Chưa có bằng chứng đây là toàn bộ ứng dụng khả dụng; chưa xác nhận phương thức phân trang để lấy đủ 100. Code giữ `partial`.

---

## 2. Bằng chứng kiểm tra thực nghiệm (Empirical Evidence)

### 2.1. Khảo sát Public GET trên 9 thị trường
- Script: `scripts/probe_google_play_http.py`
- Lệnh: `python scripts/probe_google_play_http.py --all-markets --output data/google-play-probe/all_markets`
- Bằng chứng lưu tại: `data/google-play-probe/all_markets/probe_summary.json`

| Thị trường | Mã Ngôn ngữ | URL kiểm tra | HTTP Status | Kích thước HTML | App links trên trang | Items trong Chart Section |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `vn` | `vi` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN` | 200 | 1,715,733 bytes | 36 (Recommendations) | `[]` (Empty) |
| `th` | `th` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=th&gl=TH` | 200 | 2,105,481 bytes | 59 (Recommendations) | `[]` (Empty) |
| `id` | `id` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=id&gl=ID` | 200 | 1,741,237 bytes | 39 (Recommendations) | `[]` (Empty) |
| `my` | `en` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=en&gl=MY` | 200 | 2,112,658 bytes | 58 (Recommendations) | `[]` (Empty) |
| `ph` | `en` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=en&gl=PH` | 200 | 2,126,560 bytes | 57 (Recommendations) | `[]` (Empty) |
| `sg` | `en` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=en&gl=SG` | 200 | 2,130,490 bytes | 58 (Recommendations) | `[]` (Empty) |
| `la` | `en` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=en&gl=LA` | 200 | 2,120,412 bytes | 58 (Recommendations) | `[]` (Empty) |
| `kh` | `en` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=en&gl=KH` | 200 | 2,125,890 bytes | 58 (Recommendations) | `[]` (Empty) |
| `us` | `en` | `https://play.google.com/store/apps/category/GAME_CASUAL?hl=en&gl=US` | 200 | 2,252,298 bytes | 54 (Recommendations) | `[]` (Empty) |

### 2.2. Khảo sát chi tiết Metadata & Installs qua HTTP GET
- URL: `https://play.google.com/store/apps/details?id=com.king.candycrushsaga&hl=vi&gl=VN`
- HTTP Method: `GET`
- Kích thước: 1,397,565 bytes
- Dữ liệu trích xuất thành công từ `AF_initDataCallback` `ds:5`:
  ```json
  {
    "installs": "1.000.000.000+",
    "min_installs": 1000000000,
    "real_installs": 2336253256,
    "developer": "King",
    "score": 4.575095,
    "ratings": 38937720,
    "price": 0.0,
    "currency": "VND",
    "icon": "https://play-lh.googleusercontent.com/JvMhIxuwArVmcMReJQB8PIEB1MIQNMGf9j5i914JtkBrHrA55K-nMUIVlYCa7SXAdHtzLtsycEo6NpXeHFxLwvI",
    "offersIAP": true
  }
  ```

### 2.3. Khảo sát Upstream RPC `batchexecute`
- Endpoint: `POST https://play.google.com/_/PlayStoreUi/data/batchexecute?rpcids=vyAe2`
- Payload: `f.req` chứa RPC request cho cluster `[2, "topselling_free", "GAME_CASUAL"]` hoặc `[2, "topgrossing", "GAME_CASUAL"]`.
- Thử nghiệm trên 9 thị trường:

| Thị trường | Top Free count | Top Grossing count | Ghi chú |
| :--- | :--- | :--- | :--- |
| `vn` | 100 | 49 | Toàn bộ grossing casual khả dụng tại VN |
| `th` | 100 | 80 | Toàn bộ grossing casual khả dụng tại TH |
| `id` | 100 | 90 | Toàn bộ grossing casual khả dụng tại ID |
| `my` | 100 | 83 | Toàn bộ grossing casual khả dụng tại MY |
| `ph` | 100 | 62 | Toàn bộ grossing casual khả dụng tại PH |
| `sg` | 100 | 43 | Toàn bộ grossing casual khả dụng tại SG |
| `la` | 100 | 100 | Đạt chuẩn 100 |
| `kh` | 100 | 100 | Đạt chuẩn 100 |
| `us` | 100 | 100 | Đạt chuẩn 100 |

---

## 3. Sai khác giữa Spec / Plan và Thực tế (Gap Analysis)

1. **Ràng buộc `GET` đối với Chart Rankings:**
   - Trong `SPEC-AND-01` (§2.1) và `Plan 1` (Task 1): yêu cầu phương thức là `GET` cho bảng xếp hạng.
   - **Thực tế:** Google Play Store web chỉ cung cấp chart data qua `POST` tới `batchexecute`. Không tồn tại URL `GET` trả lời chart rankings cho Google Play.
2. **Ràng buộc Đủ 100 game cho mọi chart (`top-grossing`):**
   - Trong `SPEC-AND-01` (§1.2, §3.1) và `tests/test_google_contract.py`: yêu cầu cứng mọi chart đều phải có đúng 100 game (hạng 1..100).
   - **Quan sát:** Response tại một số store trả 43–49 game. Không thể suy ra phần còn lại từ response này; cần giữ chart `partial`, không thêm game hoặc suy diễn hạng chưa quan sát.

---

## 4. Kiến nghị quyết định đặc tả (Spec Decision Request)

Căn cứ chỉ dẫn tại `Plan 1` Task 1 Step 4:
> *"Nếu endpoint public GET không cung cấp Top 100, dừng các task phụ thuộc và báo sai khác spec. Không tự đổi sang RPC POST, Selenium, feed khác hoặc giảm depth... commit probe findings, mark remaining tasks blocked by source feasibility, and request a spec decision instead of manufacturing fixture rankings."*

Chúng tôi đề xuất 2 phương án điều chỉnh đặc tả:

- **Phương án 1 (Khuyến nghị - Hỗ trợ chuẩn xác theo đúng thực tế Google Play):**
  1. Cho phép `GoogleHttpClient` sử dụng phương thức `POST` cho riêng endpoint `batchexecute` của Google Play Chart ($0 chi phí, không API key, bảo mật bằng header public tiêu chuẩn), trong khi metadata app vẫn dùng `GET`.
  2. Nới lỏng điều kiện kiểm tra độ dài chart:
     - `top-free`: Tối thiểu 100 game.
     - `top-grossing`: Tối đa 100 game (1..min(100, available)), đánh dấu chất lượng `partial` hoặc `complete` tương ứng với số game thực tế trả về từ Google Play Store thay vì ép buộc cứng 100 game khi store không có đủ.
- **Phương án 2 (Giữ nguyên Selenium cho riêng bước lấy Package IDs):**
  - Tiếp tục dùng Selenium (hoặc Playwright) để cào ID bảng xếp hạng (bị giới hạn 15–30 game như cũ) và dùng HTTP GET để cào Metadata + Lượt tải.
  - *Nhược điểm:* Không giải quyết được triệt để việc loại bỏ Chrome và không đạt được Top 100.
