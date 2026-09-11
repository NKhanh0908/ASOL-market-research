# Thiết Kế Chi Tiết — Phase 3: Module Thống Kê & Dashboard Cơ Hội Nghiên Cứu Thị Trường (P3)

- **Mã thiết kế:** SPEC-P3-STATS-RADAR
- **Ngày lập:** 2026-09-11
- **Trạng thái:** Approved by Stakeholder (Đã duyệt)
- **Kế thừa từ:** docs/core/requirement.md, docs/prd/2026-09-10-casual-game-market-research-PRD.md (M4, US-003, BA-R08, BA-R09, OUT-03, OUT-04).

---

## 1. Mục Tiêu & Phạm Vi (Goals & Scope)

### 1.1 Mục Tiêu Chính
Xây dựng module thống kê tổng hợp và giao diện Dashboard phân tích thị trường chuyên sâu (casual_scout.stats) hoạt động trên nền tảng dữ liệu phân tích Phase 2 (daily_rank_analytics) nhằm:
1. **Tổng hợp Phân bố Thể loại & Cơ chế (Genre & Mechanic Breakdown):** Tính toán tỷ trọng % số lượng game theo subgenre (Apple taxonomy) và mechanic (Taxonomy v1) trên từng thị trường riêng lẻ (VN, US, TH...) và toàn bộ khu vực ASEAN + US.
2. **Ma trận Nhiệt Thị Trường (Cross-Market Heatmap Matrix):** Xây dựng ma trận 2 chiều Country x Subgenre để trực quan hóa khẩu vị thị trường và phát hiện khoảng trống thị trường (Market Gaps).
3. **Thuật toán Chấm Điểm Cơ Hội v1 (Opportunity Radar Algorithm):** Tính toán Opportunity Score (0–100 điểm) kết hợp 3 thành phần có thể giải trình: Động lượng tăng trưởng (*Momentum*), Độ phủ khu vực (*Cross-Market Breadth*), và Vị thế thứ hạng (*Rank Tier*).
4. **Quản lý Danh Sách Ứng Viên Tiềm Năng (Shortlist Management):** Lưu trữ, phân loại trạng thái (CONSIDERING, PROTOTYPE, PASSED), quản lý độ ưu tiên (HIGH, MEDIUM, LOW) và ghi chú trực tiếp vào SQLite database.
5. **Giao Diện Trực Quan & Xuất Dữ Liệu:** Cung cấp 2 trang giao diện /dashboard và /shortlist tích hợp Chart.js, bộ lọc linh hoạt, Date Selector, cùng tính năng xuất dữ liệu ra định dạng CSV (chuẩn UTF-8 with BOM) và JSON.

### 1.2 Ngoài Phạm Vi (Phase 3 Won't Haves)
- Không tích hợp AI/LLM hoặc Dify trong Phase 3 (dành riêng cho Phase 4 theo lộ trình PRD).
- Không suy đoán số lượt tải tuyệt đối (Downloads) từ thứ hạng rank.
- Không tự động gửi tin nhắn Telegram/Slack (dành cho Backlog).
- Chưa tích hợp Google Play Store (dành cho Backlog Hướng B).

---

## 2. Mô Hình Dữ Liệu & Schema SQLite (Data Model)

Bổ sung bảng lưu trữ Shortlist vào database casual-scout.sqlite3:

`sql
-- 1. Bảng lưu trữ danh sách game tiềm năng (Shortlist)
CREATE TABLE IF NOT EXISTS shortlists (
    id TEXT PRIMARY KEY,                    -- UUID v4
    app_id TEXT NOT NULL,                   -- Apple trackId
    title TEXT NOT NULL,                    -- Tên game tại thời điểm bookmark
    icon_url TEXT,                          -- Link icon game
    developer TEXT,                         -- Tên nhà phát triển
    subgenre TEXT,                          -- Subgenre (Puzzle, Simulation...)
    mechanic TEXT,                          -- Cơ chế chính (Match-3, Merge, Sort...)
    primary_country TEXT NOT NULL,          -- Mã quốc gia nguồn khi bookmark (vn, us...)
    rank_at_bookmark INTEGER NOT NULL,      -- Thứ hạng lúc bookmark (1-100)
    opportunity_score REAL,                 -- Điểm tiềm năng tại thời điểm bookmark (0-100)
    
    status TEXT NOT NULL DEFAULT 'CONSIDERING', -- 'CONSIDERING', 'PROTOTYPE', 'PASSED', 'ARCHIVED'
    priority TEXT NOT NULL DEFAULT 'MEDIUM',    -- 'HIGH', 'MEDIUM', 'LOW'
    notes TEXT,                             -- Ghi chú của Game Designer / Producer
    tags TEXT,                              -- JSON array: [ trending_vn, innovative_mechanic]
    
    created_at TEXT NOT NULL,               -- ISO 8601 UTC
    updated_at TEXT NOT NULL,
    UNIQUE(app_id)                          -- Mỗi game chỉ có 1 bản ghi shortlist (update trạng thái)
);

CREATE INDEX IF NOT EXISTS idx_shortlist_status ON shortlists(status);
CREATE INDEX IF NOT EXISTS idx_shortlist_priority ON shortlists(priority);
CREATE INDEX IF NOT EXISTS idx_shortlist_app ON shortlists(app_id);
`

---

## 3. Kiến Trúc & Thiết Kế Các Thành Phần (Architecture & Components)

Cấu trúc thư mục mới của module casual_scout.stats:
`	ext
src/casual_scout/stats/
├── __init__.py
├── aggregator.py     # Thống kê phân bố Genre, Mechanic, ma trận Heatmap & 7-day Trends
├── radar.py          # Thuật toán tính Opportunity Score v1 & phân tầng tiềm năng (Hot Wave, Promising, Emerging)
├── shortlist.py      # CRUD service quản lý Shortlist trong SQLite
└── exporter.py       # Xuất dữ liệu Shortlist & Radar ra file CSV (UTF-8-sig) và JSON
`

### 3.1 Thuật Toán Điểm Cơ Hội v1 (adar.py)

\text{Opportunity Score} = \text{Momentum (max 40)} + \text{Breadth (max 35)} + \text{RankTier (max 25)}

* **1. Động lượng tăng trưởng — Momentum ( = 40\%$):**
  - Nhãn FAST_RISER:
    - Nếu $\Delta_{1D} \ge 20 \rightarrow 20 + \min(20, \Delta_{1D} \times 0.5)$ điểm.
    - Hoặc $\Delta_{3D} \ge 30 \rightarrow 15 + \min(25, \Delta_{3D} \times 0.4)$ điểm.
  - Nhãn NEW_ENTRY: 25 điểm nếu rank hiện tại $\le 50$; 15 điểm nếu rank $> 50$.
  - Nhãn STEADY / khác: 5 điểm nếu rank $\le 20$; 0 điểm nếu rank $> 20$.
  - Nhãn FALLING: 0 điểm.

* **2. Độ phủ đa thị trường — Breadth ( = 35\%$):**
  - $\text{Breadth} = \min(35, \text{cross\_market\_count} \times 3.5)$
  - Phủ 10–11 nước $\rightarrow 35$ điểm; 5 nước $\rightarrow 17.5$ điểm; 1 nước $\rightarrow 3.5$ điểm.

* **3. Vị thế thứ hạng — Rank Tier ( = 25\%$):**
  - Rank 1–10: 25 điểm.
  - Rank 11–30: 20 điểm.
  - Rank 31–50: 15 điểm.
  - Rank 51–100: $\max(0, (100 - \text{rank}) \times 0.2)$ điểm.

* **Phân Tầng Tiềm Năng (Opportunity Badges):**
  - 🥇 **HOT WAVE ($\ge 75$ điểm):** Game tăng trưởng vũ bão và lan tỏa diện rộng khu vực.
  - 🥈 **PROMISING ( - 74$ điểm):** Game có động lực tăng trưởng tốt hoặc độ phủ ổn định.
  - 🥉 **EMERGING ( - 49$ điểm):** Tân binh mới vào chart hoặc bứt phá đơn lẻ nội địa.
  - ⚪ **WATCHLIST ($< 30$ điểm):** Nhóm theo dõi thêm.

---

## 4. Giao Diện Người Dùng & REST API Endpoints

### 4.1 Các Trang Web Mới

1. **Trang /dashboard:**
   - Header Bar: Date Selector, Market Filter (All ASEAN+US hoặc lọc từng quốc gia).
   - Card KPIs: Tổng số game, Số lượng Hot Waves, Fast Risers, Top Subgenre & Mechanic.
   - Charts Container (Chart.js): Subgenre Share Donut Chart, Mechanic Breakdown Bar Chart, 7-Day Trend Line Chart.
   - Heatmap Matrix: Bảng tương quan quốc gia và thể loại với gradient màu.
   - Opportunity Radar Grid: Danh sách Top 30 Hot Games kèm Opportunity Badge, Rank Delta, Cờ quốc gia, Nút Quick Bookmark modal.
2. **Trang /shortlist:**
   - Bảng quản lý Shortlist trực quan, chỉnh sửa inline Notes / Priority / Status.
   - Nút Export CSV và Export JSON.
3. **Nâng cấp Navigation (ase.html):**
   - Bổ sung menu điều hướng: 📊 Dashboard, ⭐ Shortlist, 🗂️ Data Explorer, ⚙️ Pipeline Runs.

### 4.2 Danh Mục REST API

| Method | Endpoint | Query / Payload | Mô tả |
|---|---|---|---|
| GET | /api/stats/summary | date, country | Trả về KPI tổng quan, phân bố Subgenre & Mechanic |
| GET | /api/stats/heatmap | date | Trả về dữ liệu ma trận nhiệt Country x Subgenre |
| GET | /api/stats/trends | days=7 | Trả về chuỗi dữ liệu biến động 7 ngày của các Subgenre |
| GET | /api/stats/radar | date, country, limit=50 | Trả về danh sách game chấm điểm theo Opportunity Score |
| GET | /api/shortlist | status, priority, limit | Lấy danh sách game trong Shortlist |
| POST | /api/shortlist | { app_id, notes, priority, tags } | Thêm game vào Shortlist (hoặc cập nhật nếu đã có) |
| PATCH| /api/shortlist/{app_id} | { notes, priority, status, tags } | Cập nhật thông tin bản ghi Shortlist |
| DELETE| /api/shortlist/{app_id} | | Xóa game khỏi Shortlist |
| GET | /api/export/shortlist | ormat=csv|json | Tải xuống toàn bộ Shortlist |
| GET | /api/export/radar | ormat=csv|json, date | Tải xuống bảng Opportunity Radar |

---

## 5. Chiến Lược Kiểm Thử (Testing Strategy)

- **Unit Tests:**
  - 	ests/test_stats_aggregator.py: Kiểm thử tính toán Distribution, Heatmap matrix và 7-day trend với mock data nhiều thị trường.
  - 	ests/test_opportunity_radar.py: Kiểm định tính đúng đắn của công thức Opportunity Score (Hot Wave, Fast Riser, Cross-market 11 nước, Falling game).
  - 	ests/test_shortlist_service.py: Kiểm thử toàn diện các thao tác CRUD và tính idempotent khi bookmark trùng lặp.
  - 	ests/test_export_service.py: Kiểm tra nội dung xuất CSV (mã hóa UTF-8 BOM) và JSON.
- **Integration Tests:**
  - 	ests/test_web_dashboard.py: Kiểm thử HTTP status 200, render template /dashboard và /shortlist, cùng tất cả API endpoints /api/stats/*, /api/shortlist/*, /api/export/*.
