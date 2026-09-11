# Thiết Kế Chi Tiết — Phase 2: Engine Phân Tích & Phát Hiện Game Casual Trend (P2)

- **Mã thiết kế:** `SPEC-P2-ANALYSIS`
- **Ngày lập:** 2026-09-10
- **Trạng thái:** Approved by Stakeholder (Đã duyệt)
- **Kế thừa từ:** `docs/core/requirement.md`, `docs/prd/2026-09-10-casual-game-market-research-PRD.md` (BA-R05, BA-R06, BA-R07, DEC-06, DEC-07).

---

## 1. Mục Tiêu & Phạm Vi (Goals & Scope)

### 1.1 Mục Tiêu Chính
Xây dựng module phân tích thông minh (`casual_scout.analysis`) chạy trên nền tảng dữ liệu iOS Top 100 Free Casual Games đã được thu thập ở Phase 1 nhằm:
1. **Tính toán biến động thứ hạng (Rank Delta):** So sánh thứ hạng của game trên từng thị trường tại các mốc 1 ngày ($\Delta_{1D}$), 3 ngày ($\Delta_{3D}$) và 7 ngày ($\Delta_{7D}$).
2. **Phát hiện game Trend tự động (Rule-based Signals):** Gắn nhãn `NEW_ENTRY` (mới vào Top 100), `FAST_RISER` (tăng $\ge 20$ bậc/1 ngày hoặc $\ge 30$ bậc/3 ngày), `FALLING`, `STEADY`.
3. **Phân loại Thể loại phụ & Cơ chế chơi 2 tầng (Casual Taxonomy & Mechanics v1):** Kết hợp phân loại chính thức từ Apple (`Puzzle`, `Simulation`, `Arcade`, `Action`, `Card`, ...) và bộ từ điển từ khóa xác định cơ chế (`Match-3`, `Merge`, `Physics/Sort`, `Idle`, `Runner`, `Word/Trivia`, `Drawing`) kèm trích dẫn bằng chứng và cấp độ tin cậy.
4. **Độ phủ thị trường (Cross-Market Breadth):** Thống kê số lượng và danh sách các quốc gia trong 11 thị trường ASEAN + US mà game đang đồng thời xuất hiện trong Top 100.
5. **Nâng cấp Web UI & Xuất CSV:** Cung cấp bộ lọc nhanh game trend, hiển thị badge delta/mechanic/độ phủ trên bảng xếp hạng và trang chi tiết game.

### 1.2 Ngoài Phạm Vi (Phase 2 Won't Haves)
- Không suy đoán số lượt tải tuyệt đối (Downloads) từ thứ hạng rank.
- Không tích hợp AI/LLM hoặc Dify trong Phase 2 (dành riêng cho Phase 4 theo lộ trình).
- Không tự động gửi tin nhắn Telegram/Slack (dành cho Backlog).
- Chưa tích hợp Google Play Store (đã lưu vào Backlog Hướng B để triển khai sau).

---

## 2. Mô Hình Dữ Liệu & Schema SQLite (Data Model)

Bổ sung cấu trúc lưu trữ phân tích vào database `casual-scout.sqlite3`:

```sql
-- 1. Xác định bản chụp chuẩn (canonical snapshot) cho từng ngày lịch UTC
CREATE TABLE IF NOT EXISTS daily_canonical_snapshots (
    date TEXT NOT NULL,                     -- Định dạng 'YYYY-MM-DD' (UTC)
    country TEXT NOT NULL,                  -- 'vn', 'us', ...
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (date, country)
);

-- 2. Bảng lưu trữ chỉ số phân tích và gắn nhãn theo ngày
CREATE TABLE IF NOT EXISTS daily_rank_analytics (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,                     -- 'YYYY-MM-DD' (UTC)
    country TEXT NOT NULL,                  -- 'vn', 'us', ...
    app_id TEXT NOT NULL,                   -- Apple trackId
    current_rank INTEGER NOT NULL,          -- Thứ hạng ngày D (1-100)
    
    -- Biến động thứ hạng
    rank_1d_ago INTEGER,                   -- NULL nếu D-1 không có data hoặc vắng
    delta_1d INTEGER,                       -- Rank(D-1) - Rank(D) (Dương: tăng, Âm: tụt)
    rank_3d_ago INTEGER,                   -- NULL nếu D-3 không có data
    delta_3d INTEGER,
    rank_7d_ago INTEGER,                   -- NULL nếu D-7 không có data
    delta_7d INTEGER,
    
    -- Gắn nhãn tín hiệu Trend
    signal TEXT NOT NULL,                   -- 'NEW_ENTRY', 'FAST_RISER', 'FALLING', 'STEADY', 'NONE'
    signal_reasons_json TEXT NOT NULL,      -- Danh sách lý do: ["delta_1d >= 20 (+35)", "first_time_in_top100"]
    
    -- Phân loại Thể loại con & Cơ chế chơi (Taxonomy v1)
    subgenre TEXT,                          -- 'Puzzle', 'Simulation', 'Arcade', ... (từ Apple)
    mechanic TEXT NOT NULL,                 -- 'Match-3', 'Merge', 'Sort', 'Idle', 'Runner', 'General'
    mechanic_evidence TEXT,                 -- Trích dẫn từ khóa tìm thấy trong tên/mô tả
    mechanic_confidence TEXT NOT NULL,      -- 'high', 'medium', 'unknown'
    
    -- Độ phủ thị trường trong cùng ngày D
    cross_market_count INTEGER NOT NULL,    -- Số quốc gia game lọt Top 100 trong ngày D (1..11)
    cross_markets_json TEXT NOT NULL,       -- JSON mảng mã nước: ["vn", "th", "sg", "id"]
    
    created_at TEXT NOT NULL,
    UNIQUE(date, country, app_id)
);

CREATE INDEX IF NOT EXISTS idx_analytics_date_country ON daily_rank_analytics(date, country);
CREATE INDEX IF NOT EXISTS idx_analytics_signal ON daily_rank_analytics(date, signal);
CREATE INDEX IF NOT EXISTS idx_analytics_app ON daily_rank_analytics(app_id);
```

---

## 3. Kiến Trúc & Thiết Kế Các Thành Phần (Architecture & Components)

Cấu trúc thư mục mới:
```text
src/casual_scout/analysis/
├── __init__.py
├── taxonomy.py       # Phân loại Thể loại phụ & Cơ chế chơi (Rule-based Dictionary)
├── signals.py        # Logic gán nhãn tín hiệu Trend (NEW_ENTRY, FAST_RISER, ...)
├── delta.py          # Tính toán Rank Delta theo ngày & Thống kê Cross-market presence
└── service.py        # AnalysisService điều phối quy trình phân tích và lưu DB
```

### 3.1 Taxonomy Engine (`taxonomy.py`)
- **Tầng 1 — Trích xuất Subgenre Apple:**
  - Lấy danh sách genres từ metadata hoặc entry.
  - Lọc bỏ `Games` (6014) và `Casual` (7003) để lấy thể loại chuyên biệt nhất: `Puzzle` (7012), `Action` (7001), `Simulation` (7015), `Arcade` (7004), `Card` (7005), `Board` (7002), `Sports` (7016), `Strategy` (7017), `Trivia` (7018), `Word` (7019).
  - Nếu không có genre phụ nào khác, fallback về `Casual`.
- **Tầng 2 — Từ điển nhận diện Cơ chế (Mechanics Dictionary):**
  - Quét chuỗi văn bản chuẩn hóa (lowercase) từ `Title + Subtitle + Description`:
    - `Match-3`: `["match 3", "match-3", "match-three", "match three", "tile match", "swap 3", "blast"]`
    - `Merge`: `["merge", "merging", "combine items", "fusion"]`
    - `Sorting / Physics`: `["water sort", "color sort", "ball sort", "screw", "nuts & bolts", "nuts and bolts", "pin pull", "physics puzzle"]`
    - `Idle / Tycoon`: `["idle", "tycoon", "factory", "mining", "auto farm"]`
    - `Runner`: `["endless runner", "subway", "runner", "dodge obstacles"]`
    - `Card / Board`: `["solitaire", "ludo", "mahjong", "domino", "uno", "card game"]`
    - `Word / Trivia`: `["crossword", "word connect", "word puzzle", "trivia quiz", "wordle"]`
    - `Drawing / Line`: `["draw line", "draw puzzle", "brain out", "draw to save"]`
- **Quy tắc xác định Confidence:**
  - `high`: Subgenre của Apple khớp với nhóm cơ chế (ví dụ: Apple báo `Puzzle` và tìm thấy từ khóa `match 3` trong mô tả).
  - `medium`: Tìm thấy từ khóa cơ chế rõ ràng trong tên/mô tả nhưng thể loại Apple là nhóm chung (`Casual`).
  - `unknown`: Không tìm thấy từ khóa đặc trưng -> Gán `mechanic = 'General'`, `mechanic_evidence = None`.

### 3.2 Signal Labelling Engine (`signals.py`)
Áp dụng theo đúng quyết định sản phẩm đã duyệt (DEC-06 & BA-R06):
- **`FAST_RISER`**: Khi $\Delta_{1D} \ge 20$ **hoặc** $\Delta_{3D} \ge 30$. Lý do lưu vào `signal_reasons_json` ghi rõ mốc tăng (ví dụ: `["delta_1d=+25", "jumped from rank 65 to 40"]`).
- **`NEW_ENTRY`**: Khi game có mặt trong Top 100 ngày $D$, nhưng **không** có trong Top 100 của ngày $D-1$ (yêu cầu ngày $D-1$ phải có bản chụp hoàn chỉnh hợp lệ).
- **`FALLING`**: Khi $\Delta_{1D} \le -20$ **hoặc** $\Delta_{3D} \le -30$.
- **`STEADY`**: Khi $-5 \le \Delta_{1D} \le +5$.
- **`NONE`**: Các trường hợp thay đổi nhẹ khác (ví dụ $+8, -12$).
- *Lưu ý về dữ liệu thiếu:* Nếu ngày $D-1$ bị thiếu snapshot, không suy diễn gán nhãn `NEW_ENTRY` hoặc `FAST_RISER` từ $\Delta_{1D}$.

### 3.3 Delta Engine & Cross-Market (`delta.py`)
- **Chọn Bản chụp Chuẩn (`canonical snapshot`):**
  - Với mỗi ngày UTC $D$ và thị trường $C$, chọn bản chụp mới nhất trong ngày có `quality = 'complete'`.
- **Tính Rank Delta:**
  - $\Delta_{1D} = Rank(D-1) - Rank(D)$. Nếu vắng ở $D-1$, `rank_1d_ago = NULL`, `delta_1d = NULL`.
  - $\Delta_{3D} = Rank(D-3) - Rank(D)$.
  - $\Delta_{7D} = Rank(D-7) - Rank(D)$.
- **Độ phủ thị trường (Cross-Market Presence):**
  - Quét toàn bộ 11 thị trường (`vn, us, sg, th, id, my, ph, kh, la, mm, bn`) trong cùng ngày $D$.
  - Tính `cross_market_count = len(markets_in_top100)` và lưu mảng `cross_markets_json`.

### 3.4 Analysis Service (`service.py`)
- `AnalysisService.analyze_date(target_date: str) -> dict`:
  1. Xác định canonical snapshot của 11 thị trường cho ngày `target_date`.
  2. Truy xuất các mốc quá khứ $D-1, D-3, D-7$.
  3. Tính toán rank delta, phân loại taxonomy, gán nhãn trend và thống kê cross-market.
  4. Thực hiện transaction ghi đồng thời vào bảng `daily_rank_analytics` và `daily_canonical_snapshots`.
  5. Đảm bảo tính **Idempotent**: Chạy lại phân tích cho ngày đó sẽ thay thế bản ghi cũ mà không gây trùng lặp.

---

## 4. Giao Diện Người Dùng & Tương Tác (Web UI & CLI)

### 4.1 Giao diện Web (`http://127.0.0.1:8000`)
- **Dashboard chính (`/`):**
  - **Tabs lọc nhanh:**
    - `📋 Tất cả Top 100`
    - `⚡ Game Tăng Nhanh (Fast Risers)`
    - `🟢 Game Mới Lọt Top (New Entries)`
  - **Bảng dữ liệu:** Bổ sung các cột:
    - *Biến động 24h:* Hiển thị `+35 ⚡` (xanh), `-20 🔻` (đỏ), `NEW 🟢` (xanh ngọc), `—` (xám).
    - *Thể loại & Cơ chế:* Huy hiệu Subgenre (`Puzzle`) + Mechanic (`Match-3`).
    - *Độ phủ:* Huy hiệu `8/11 🌏` kèm danh sách nước khi rê chuột.
- **Trang Chi tiết Game (`/games/{app_id}`):**
  - Bảng biến động lịch sử: Thứ hạng hôm nay, 1 ngày trước, 3 ngày trước, 7 ngày trước.
  - Hộp thông tin căn cứ phân loại: Hiển thị từ khóa tìm thấy và trích dẫn trong mô tả.
  - Danh sách các nước trong khu vực mà game đang có mặt trong bảng xếp hạng.
- **Tải dữ liệu CSV (`/data/download`):**
  - Bổ sung các trường phân tích: `rank_1d_ago, delta_1d, delta_3d, delta_7d, signal, subgenre, mechanic, mechanic_confidence, cross_market_count, cross_markets`.

### 4.2 Lệnh CLI Mới
- `casual_scout analyze [--date YYYY-MM-DD] [--data-dir .\data]`: Chạy phân tích cho ngày chỉ định (mặc định hôm nay).
- `casual_scout trends [--country vn] [--signal fast_riser|new_entry] [--data-dir .\data]`: Hiển thị bảng tóm tắt game trend trên terminal.

---

## 5. Chiến Lược Kiểm Thử (Testing & Quality Assurance)

Áp dụng phương pháp Test-Driven Development (TDD) với các bộ kiểm tra:
1. `tests/test_taxonomy.py`:
   - Kiểm tra nhận diện chính xác các nhóm từ khóa Match-3, Merge, Sort, Idle, Runner, v.v.
   - Kiểm tra trích xuất bằng chứng từ ngữ và gán đúng mức độ `high`, `medium`, `unknown`.
2. `tests/test_delta.py`:
   - Kiểm tra tính toán chính xác $\Delta_{1D}, \Delta_{3D}, \Delta_{7D}$.
   - Kiểm tra trường hợp ngày cũ thiếu dữ liệu thì delta phải là `NULL`, không được gán 0.
   - Kiểm tra tính toán độ phủ thị trường cross-market.
3. `tests/test_signals.py`:
   - Kiểm tra gán nhãn `FAST_RISER` khi $\Delta_{1D} \ge 20$ hoặc $\Delta_{3D} \ge 30$.
   - Kiểm tra gán nhãn `NEW_ENTRY` chỉ khi ngày $D-1$ có snapshot hoàn chỉnh.
   - Kiểm tra gán nhãn `FALLING` và `STEADY`.
4. `tests/test_analysis_service.py`:
   - Kiểm tra luồng phân tích toàn diện và ghi vào SQLite.
   - Kiểm tra tính idempotent khi chạy lại phân tích trên cùng 1 ngày.
5. `tests/test_web_analysis.py`:
   - Kiểm tra giao diện web hiển thị đúng huy hiệu delta, bộ lọc nhanh game trend và xuất CSV phân tích.

---

## 6. Tiêu Chuẩn Nghiệm Thu Phase 2 (Acceptance Criteria)

- [ ] **AC-01:** Tất cả các bản ghi phân tích ngày $D$ tính đúng $\Delta_{1D}, \Delta_{3D}, \Delta_{7D}$ dựa trên canonical snapshot thực tế.
- [ ] **AC-02:** Nhãn `FAST_RISER` và `NEW_ENTRY` được gắn hoàn toàn tự động theo đúng ngưỡng định lượng và lưu rõ lý do căn cứ.
- [ ] **AC-03:** Phân loại thể loại phụ và cơ chế chơi phân tầng minh bạch, lưu dẫn chứng từ khóa tìm thấy.
- [ ] **AC-04:** Độ phủ thị trường cross-market đếm chính xác số nước lọt Top 100 trong cùng ngày.
- [ ] **AC-05:** Giao diện Web lọc mượt mà danh sách Fast Risers và New Entries, hiển thị đầy đủ huy hiệu biến động.
- [ ] **AC-06:** Toàn bộ test suite chạy đạt 100%, linter Ruff sạch 0 lỗi, dependencies hợp lệ.
