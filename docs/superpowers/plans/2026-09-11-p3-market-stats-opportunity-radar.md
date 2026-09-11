# Phase 3 (P3): Module Thống Kê & Dashboard Cơ Hội Nghiên Cứu Thị Trường — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng module thống kê đa thị trường (`casual_scout.stats`), thuật toán chấm điểm cơ hội v1 (`Opportunity Score`), quản lý danh sách tiềm năng (`Shortlist`), cùng giao diện Dashboard trực quan (`/dashboard` & `/shortlist`) tích hợp biểu đồ Chart.js và tính năng xuất dữ liệu CSV (chuẩn UTF-8 with BOM) / JSON.

**Architecture:** Bổ sung bảng `shortlists` vào SQLite. Tạo package `src/casual_scout/stats/` gồm `aggregator.py`, `radar.py`, `shortlist.py`, `exporter.py`. Tích hợp REST API và render giao diện trong `casual_scout.web` (FastAPI + Jinja2 + Chart.js CDN), mở rộng CLI điều phối.

**Tech Stack:** Python 3.12+, SQLite 3 (WAL mode), FastAPI, Jinja2, Chart.js (CDN), Pytest.

**Spec:** [`docs/superpowers/specs/2026-09-11-p3-market-stats-opportunity-radar-design.md`](file:///D:/Working/ASOL/tool/ASOL-market-research/docs/superpowers/specs/2026-09-11-p3-market-stats-opportunity-radar-design.md)

## Global Constraints

- **Tính Minh Bạch & Giải Trình (Explainable Stats):** Điểm cơ hội $Opportunity\ Score = \text{Momentum (40)} + \text{Breadth (35)} + \text{RankTier (25)}$ phải có thể truy vết từng thành phần; không dùng số ngẫu nhiên hoặc "hộp đen".
- **Không Giả Lập Lượt Tải:** Tuyệt đối không quy đổi rank thành lượt tải (Downloads) hoặc doanh thu; tuân thủ nghiêm ngặt BA-R09.
- **An Toàn Dữ Liệu Khi Thiếu Ngày:** Khi hệ thống có ít hơn 7 ngày dữ liệu, thống kê xu hướng 7 ngày hiển thị theo các ngày thực tế có sẵn kèm ghi chú rõ ràng, không sinh số ảo.
- **Xuất Dữ Liệu Tương Thích Windows:** File CSV xuất ra phải sử dụng mã hóa `utf-8-sig` (UTF-8 with BOM) để mở trực tiếp trên Microsoft Excel trên Windows không bị lỗi font Tiếng Việt / ký tự Châu Á.

---

### Task 1: Mở Rộng Schema SQLite & Repository Cho Shortlist & Thống Kê

**Files:**
- Modify: `src/casual_scout/storage/schema.sql`
- Modify: `src/casual_scout/storage/repository.py`
- Test: `tests/test_shortlist_storage.py`

**Interfaces:**
- Consumes: `Repository._connect()`, `Repository._write_connection()`
- Produces:
  - `repo.save_shortlist_item(item: dict) -> None`
  - `repo.get_shortlist_items(status: str | None = None, priority: str | None = None) -> list[dict]`
  - `repo.get_shortlist_item_by_app_id(app_id: str) -> dict | None`
  - `repo.update_shortlist_item(app_id: str, updates: dict) -> bool`
  - `repo.delete_shortlist_item(app_id: str) -> bool`
  - `repo.get_available_analytics_dates() -> list[str]`

- [ ] **Step 1: Viết test thất bại (Failing Test) cho Shortlist Storage**

Tạo file `tests/test_shortlist_storage.py`:
```python
from pathlib import Path
import pytest
from casual_scout.storage import Repository

@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "data")
    r.initialize()
    return r

def test_shortlist_crud(repo: Repository):
    assert repo.get_shortlist_items() == []
    
    item = {
        "id": "sl-1",
        "app_id": "123456",
        "title": "Block Blast!",
        "icon_url": "https://example.com/icon.png",
        "developer": "Hungry Studio",
        "subgenre": "Puzzle",
        "mechanic": "Block Puzzle",
        "primary_country": "vn",
        "rank_at_bookmark": 3,
        "opportunity_score": 88.5,
        "status": "CONSIDERING",
        "priority": "HIGH",
        "notes": "Very strong retention mechanic",
        "tags": ["trending_vn", "block_puzzle"],
        "created_at": "2026-09-11T00:00:00Z",
        "updated_at": "2026-09-11T00:00:00Z",
    }
    repo.save_shortlist_item(item)
    
    items = repo.get_shortlist_items()
    assert len(items) == 1
    assert items[0]["app_id"] == "123456"
    assert items[0]["status"] == "CONSIDERING"
    assert items[0]["tags"] == ["trending_vn", "block_puzzle"]
    
    # Update item
    updated = repo.update_shortlist_item("123456", {
        "status": "PROTOTYPE",
        "notes": "Started prototyping core loop",
        "updated_at": "2026-09-11T01:00:00Z"
    })
    assert updated is True
    
    single = repo.get_shortlist_item_by_app_id("123456")
    assert single is not None
    assert single["status"] == "PROTOTYPE"
    assert single["notes"] == "Started prototyping core loop"
    
    # Delete item
    deleted = repo.delete_shortlist_item("123456")
    assert deleted is True
    assert repo.get_shortlist_items() == []
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `pytest tests/test_shortlist_storage.py -v`
Expected: FAIL (phương thức chưa tồn tại).

- [ ] **Step 3: Cập nhật `schema.sql` và phương thức trong `repository.py`**

Thêm bảng `shortlists` vào `src/casual_scout/storage/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS shortlists (
    id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    title TEXT NOT NULL,
    icon_url TEXT,
    developer TEXT,
    subgenre TEXT,
    mechanic TEXT,
    primary_country TEXT NOT NULL,
    rank_at_bookmark INTEGER NOT NULL,
    opportunity_score REAL,
    status TEXT NOT NULL DEFAULT 'CONSIDERING',
    priority TEXT NOT NULL DEFAULT 'MEDIUM',
    notes TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(app_id)
);

CREATE INDEX IF NOT EXISTS idx_shortlist_status ON shortlists(status);
CREATE INDEX IF NOT EXISTS idx_shortlist_priority ON shortlists(priority);
CREATE INDEX IF NOT EXISTS idx_shortlist_app ON shortlists(app_id);
```

Bổ sung các phương thức vào `Repository` trong `src/casual_scout/storage/repository.py`:
```python
    def save_shortlist_item(self, item: dict) -> None:
        import json
        with self._write_connection() as conn:
            tags_json = json.dumps(item.get("tags") or [], ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO shortlists (
                    id, app_id, title, icon_url, developer, subgenre, mechanic,
                    primary_country, rank_at_bookmark, opportunity_score,
                    status, priority, notes, tags, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id) DO UPDATE SET
                    title = excluded.title,
                    icon_url = excluded.icon_url,
                    developer = excluded.developer,
                    subgenre = excluded.subgenre,
                    mechanic = excluded.mechanic,
                    rank_at_bookmark = excluded.rank_at_bookmark,
                    opportunity_score = excluded.opportunity_score,
                    updated_at = excluded.updated_at
                """,
                (
                    item["id"],
                    item["app_id"],
                    item["title"],
                    item.get("icon_url"),
                    item.get("developer"),
                    item.get("subgenre"),
                    item.get("mechanic"),
                    item["primary_country"],
                    item["rank_at_bookmark"],
                    item.get("opportunity_score"),
                    item.get("status", "CONSIDERING"),
                    item.get("priority", "MEDIUM"),
                    item.get("notes"),
                    tags_json,
                    item["created_at"],
                    item["updated_at"],
                )
            )

    def get_shortlist_items(self, status: str | None = None, priority: str | None = None) -> list[dict]:
        import json
        query = "SELECT * FROM shortlists WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        query += " ORDER BY updated_at DESC"
        
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
                results.append(d)
            return results

    def get_shortlist_item_by_app_id(self, app_id: str) -> dict | None:
        import json
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM shortlists WHERE app_id = ?", (app_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
            return d

    def update_shortlist_item(self, app_id: str, updates: dict) -> bool:
        import json
        allowed = {"status", "priority", "notes", "tags", "updated_at"}
        valid_updates = {k: v for k, v in updates.items() if k in allowed}
        if not valid_updates:
            return False
        
        set_clauses = []
        params = []
        for k, v in valid_updates.items():
            set_clauses.append(f"{k} = ?")
            if k == "tags" and isinstance(v, list):
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                params.append(v)
        params.append(app_id)
        
        with self._write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE shortlists SET {', '.join(set_clauses)} WHERE app_id = ?",
                params
            )
            return cursor.rowcount > 0

    def delete_shortlist_item(self, app_id: str) -> bool:
        with self._write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shortlists WHERE app_id = ?", (app_id,))
            return cursor.rowcount > 0

    def get_available_analytics_dates(self) -> list[str]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT date FROM daily_rank_analytics ORDER BY date DESC")
            return [r[0] for r in cursor.fetchall()]
```

- [ ] **Step 4: Chạy test để xác nhận vượt qua**

Run: `pytest tests/test_shortlist_storage.py -v`
Expected: PASS

---

### Task 2: Engine Thống Kê Phân Bố & Ma Trận Nhiệt Thị Trường (`aggregator.py`)

**Files:**
- Create: `src/casual_scout/stats/__init__.py`
- Create: `src/casual_scout/stats/aggregator.py`
- Test: `tests/test_stats_aggregator.py`

**Interfaces:**
- Consumes: `repo.get_daily_analytics(date, country)`
- Produces:
  - `compute_genre_distribution(records: list[dict]) -> dict`
  - `compute_mechanic_distribution(records: list[dict]) -> dict`
  - `build_market_heatmap(records_by_country: dict[str, list[dict]]) -> dict`
  - `compute_7day_subgenre_trends(history_records: list[dict]) -> dict`

- [ ] **Step 1: Viết test cho Aggregator**

Tạo file `tests/test_stats_aggregator.py`:
```python
from casual_scout.stats.aggregator import (
    compute_genre_distribution,
    compute_mechanic_distribution,
    build_market_heatmap,
    compute_7day_subgenre_trends,
)

def test_genre_and_mechanic_distribution():
    records = [
        {"subgenre": "Puzzle", "mechanic": "Match-3"},
        {"subgenre": "Puzzle", "mechanic": "Block Puzzle"},
        {"subgenre": "Simulation", "mechanic": "Idle"},
        {"subgenre": "Action", "mechanic": "Runner"},
    ]
    g_dist = compute_genre_distribution(records)
    assert g_dist["total"] == 4
    assert g_dist["breakdown"]["Puzzle"]["count"] == 2
    assert g_dist["breakdown"]["Puzzle"]["percentage"] == 50.0
    assert g_dist["breakdown"]["Simulation"]["count"] == 1
    
    m_dist = compute_mechanic_distribution(records)
    assert m_dist["total"] == 4
    assert m_dist["breakdown"]["Match-3"]["count"] == 1
    assert m_dist["breakdown"]["Match-3"]["percentage"] == 25.0

def test_build_market_heatmap():
    data = {
        "vn": [
            {"subgenre": "Puzzle"}, {"subgenre": "Puzzle"}, {"subgenre": "Simulation"}
        ],
        "us": [
            {"subgenre": "Word"}, {"subgenre": "Word"}, {"subgenre": "Puzzle"}
        ]
    }
    heatmap = build_market_heatmap(data)
    assert "vn" in heatmap["countries"]
    assert "us" in heatmap["countries"]
    assert "Puzzle" in heatmap["genres"]
    vn_idx = heatmap["countries"].index("vn")
    puzzle_idx = heatmap["genres"].index("Puzzle")
    assert heatmap["matrix"][vn_idx][puzzle_idx] == 2

def test_compute_7day_subgenre_trends():
    records = [
        {"date": "2026-09-05", "subgenre": "Puzzle"},
        {"date": "2026-09-05", "subgenre": "Simulation"},
        {"date": "2026-09-06", "subgenre": "Puzzle"},
        {"date": "2026-09-06", "subgenre": "Puzzle"},
    ]
    trends = compute_7day_subgenre_trends(records)
    assert "dates" in trends
    assert "2026-09-05" in trends["dates"]
    assert "2026-09-06" in trends["dates"]
    assert "series" in trends
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `pytest tests/test_stats_aggregator.py -v`
Expected: FAIL (Module chưa tồn tại).

- [ ] **Step 3: Cài đặt code `src/casual_scout/stats/aggregator.py`**

Tạo `src/casual_scout/stats/__init__.py` và `src/casual_scout/stats/aggregator.py`:
```python
from collections import Counter, defaultdict
from typing import Any

def compute_genre_distribution(records: list[dict]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {"total": 0, "breakdown": {}}
    
    counts = Counter(r.get("subgenre") or "Unknown" for r in records)
    breakdown = {}
    for genre, count in counts.most_common():
        breakdown[genre] = {
            "count": count,
            "percentage": round((count / total) * 100, 1)
        }
    return {"total": total, "breakdown": breakdown}

def compute_mechanic_distribution(records: list[dict]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {"total": 0, "breakdown": {}}
    
    counts = Counter(r.get("mechanic") or "General" for r in records)
    breakdown = {}
    for mech, count in counts.most_common():
        breakdown[mech] = {
            "count": count,
            "percentage": round((count / total) * 100, 1)
        }
    return {"total": total, "breakdown": breakdown}

def build_market_heatmap(records_by_country: dict[str, list[dict]]) -> dict[str, Any]:
    countries = sorted(records_by_country.keys())
    all_genres_set = set()
    for recs in records_by_country.values():
        for r in recs:
            all_genres_set.add(r.get("subgenre") or "Unknown")
    
    genres = sorted(list(all_genres_set))
    if not genres:
        return {"countries": countries, "genres": [], "matrix": []}

    matrix = []
    for c in countries:
        c_recs = records_by_country.get(c, [])
        c_counts = Counter(r.get("subgenre") or "Unknown" for r in c_recs)
        row = [c_counts.get(g, 0) for g in genres]
        matrix.append(row)

    return {
        "countries": countries,
        "genres": genres,
        "matrix": matrix
    }

def compute_7day_subgenre_trends(history_records: list[dict]) -> dict[str, Any]:
    if not history_records:
        return {"dates": [], "series": {}}
    
    dates_set = sorted(list(set(r["date"] for r in history_records)))
    genre_date_counts = defaultdict(lambda: Counter())
    
    top_genres_counter = Counter()
    for r in history_records:
        g = r.get("subgenre") or "Unknown"
        d = r["date"]
        genre_date_counts[g][d] += 1
        top_genres_counter[g] += 1
    
    top_5_genres = [g for g, _ in top_genres_counter.most_common(5)]
    
    series = {}
    for g in top_5_genres:
        series[g] = [genre_date_counts[g].get(d, 0) for d in dates_set]

    return {
        "dates": dates_set,
        "series": series
    }
```

- [ ] **Step 4: Chạy test để xác nhận vượt qua**

Run: `pytest tests/test_stats_aggregator.py -v`
Expected: PASS

---

### Task 3: Thuật Toán Điểm Cơ Hội v1 & Phân Tầng Tiềm Năng (`radar.py`)

**Files:**
- Create: `src/casual_scout/stats/radar.py`
- Test: `tests/test_opportunity_radar.py`

**Interfaces:**
- Produces:
  - `calculate_opportunity_score(record: dict) -> dict`
  - `rank_opportunities(records: list[dict], shortlisted_app_ids: set[str] | None = None) -> list[dict]`

- [ ] **Step 1: Viết test cho Opportunity Radar**

Tạo file `tests/test_opportunity_radar.py`:
```python
from casual_scout.stats.radar import calculate_opportunity_score, rank_opportunities

def test_calculate_opportunity_score_hot_wave():
    record = {
        "app_id": "1001",
        "current_rank": 5,
        "delta_1d": 35,
        "delta_3d": 45,
        "signal": "FAST_RISER",
        "cross_market_count": 10,
    }
    scored = calculate_opportunity_score(record)
    assert scored["score"] >= 75.0
    assert scored["badge"] == "HOT WAVE"
    assert scored["momentum_score"] == 37.5
    assert scored["breadth_score"] == 35.0
    assert scored["rank_score"] == 25.0

def test_calculate_opportunity_score_falling():
    record = {
        "app_id": "1002",
        "current_rank": 80,
        "delta_1d": -15,
        "signal": "FALLING",
        "cross_market_count": 1,
    }
    scored = calculate_opportunity_score(record)
    assert scored["momentum_score"] == 0.0
    assert scored["breadth_score"] == 3.5
    assert scored["badge"] == "WATCHLIST"

def test_rank_opportunities_and_deduplication():
    records = [
        {"app_id": "1001", "current_rank": 5, "delta_1d": 30, "signal": "FAST_RISER", "cross_market_count": 8, "country": "vn"},
        {"app_id": "1001", "current_rank": 12, "delta_1d": 25, "signal": "FAST_RISER", "cross_market_count": 8, "country": "th"},
        {"app_id": "1002", "current_rank": 2, "delta_1d": 0, "signal": "STEADY", "cross_market_count": 1, "country": "vn"},
    ]
    ranked = rank_opportunities(records, shortlisted_app_ids={"1001"})
    assert len(ranked) == 2
    assert ranked[0]["app_id"] == "1001"
    assert ranked[0]["is_shortlisted"] is True
    assert ranked[1]["app_id"] == "1002"
    assert ranked[1]["is_shortlisted"] is False
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `pytest tests/test_opportunity_radar.py -v`
Expected: FAIL.

- [ ] **Step 3: Cài đặt code `src/casual_scout/stats/radar.py`**

Tạo `src/casual_scout/stats/radar.py`:
```python
from typing import Any

def calculate_opportunity_score(record: dict) -> dict[str, Any]:
    signal = record.get("signal", "NONE")
    delta_1d = record.get("delta_1d")
    delta_3d = record.get("delta_3d")
    current_rank = record.get("current_rank", 100)
    
    momentum = 0.0
    if signal == "FAST_RISER":
        if delta_1d is not None and delta_1d >= 20:
            momentum = 20.0 + min(20.0, delta_1d * 0.5)
        elif delta_3d is not None and delta_3d >= 30:
            momentum = 15.0 + min(25.0, delta_3d * 0.4)
        else:
            momentum = 20.0
    elif signal == "NEW_ENTRY":
        momentum = 25.0 if current_rank <= 50 else 15.0
    elif signal == "STEADY":
        momentum = 5.0 if current_rank <= 20 else 0.0
    elif signal == "FALLING":
        momentum = 0.0
    else:
        momentum = 0.0

    cross_count = record.get("cross_market_count", 1)
    breadth = min(35.0, round(cross_count * 3.5, 1))

    if current_rank <= 10:
        rank_score = 25.0
    elif current_rank <= 30:
        rank_score = 20.0
    elif current_rank <= 50:
        rank_score = 15.0
    else:
        rank_score = max(0.0, round((100 - current_rank) * 0.2, 1))

    total_score = round(min(100.0, momentum + breadth + rank_score), 1)

    if total_score >= 75.0:
        badge = "HOT WAVE"
    elif total_score >= 50.0:
        badge = "PROMISING"
    elif total_score >= 30.0:
        badge = "EMERGING"
    else:
        badge = "WATCHLIST"

    return {
        "score": total_score,
        "badge": badge,
        "momentum_score": round(momentum, 1),
        "breadth_score": round(breadth, 1),
        "rank_score": round(rank_score, 1)
    }

def rank_opportunities(records: list[dict], shortlisted_app_ids: set[str] | None = None) -> list[dict]:
    shortlisted = shortlisted_app_ids or set()
    best_by_app: dict[str, dict] = {}

    for r in records:
        app_id = r["app_id"]
        scored_info = calculate_opportunity_score(r)
        
        entry = dict(r)
        entry["opportunity_score"] = scored_info["score"]
        entry["opportunity_badge"] = scored_info["badge"]
        entry["momentum_score"] = scored_info["momentum_score"]
        entry["breadth_score"] = scored_info["breadth_score"]
        entry["rank_score"] = scored_info["rank_score"]
        entry["is_shortlisted"] = app_id in shortlisted
        
        if app_id not in best_by_app or entry["opportunity_score"] > best_by_app[app_id]["opportunity_score"]:
            best_by_app[app_id] = entry

    results = list(best_by_app.values())
    results.sort(key=lambda x: (x["opportunity_score"], x.get("cross_market_count", 0), -x.get("current_rank", 100)), reverse=True)
    return results
```

- [ ] **Step 4: Chạy test để xác nhận vượt qua**

Run: `pytest tests/test_opportunity_radar.py -v`
Expected: PASS

---

### Task 4: Dịch Vụ Shortlist & Xuất Dữ Liệu CSV/JSON (`shortlist.py` & `exporter.py`)

**Files:**
- Create: `src/casual_scout/stats/shortlist.py`
- Create: `src/casual_scout/stats/exporter.py`
- Test: `tests/test_stats_export.py`

**Interfaces:**
- Produces:
  - `ShortlistService.bookmark_game(...)`
  - `ShortlistService.list_shortlists(...)`
  - `export_shortlist_to_csv(items: list[dict]) -> str`
  - `export_radar_to_csv(radar_items: list[dict]) -> str`
  - `export_to_json(data: Any) -> str`

- [ ] **Step 1: Viết test cho Shortlist Service & Exporter**

Tạo file `tests/test_stats_export.py`:
```python
from pathlib import Path
import pytest
from casual_scout.storage import Repository
from casual_scout.stats.shortlist import ShortlistService
from casual_scout.stats.exporter import export_shortlist_to_csv, export_radar_to_csv, export_to_json

@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "data")
    r.initialize()
    return r

def test_shortlist_service_flow(repo: Repository):
    service = ShortlistService(repo)
    item = service.bookmark_game(
        app_id="999",
        title="Merge Mansion",
        primary_country="vn",
        rank_at_bookmark=1,
        subgenre="Puzzle",
        mechanic="Merge",
        opportunity_score=85.0,
        notes="Top merge reference",
        priority="HIGH"
    )
    assert item["app_id"] == "999"
    assert item["status"] == "CONSIDERING"
    
    all_items = service.list_shortlists()
    assert len(all_items) == 1
    
    csv_content = export_shortlist_to_csv(all_items)
    assert csv_content.startswith('﻿')
    assert "Merge Mansion" in csv_content
    assert "Top merge reference" in csv_content

def test_export_radar_csv():
    radar_items = [{
        "app_id": "888",
        "title": "Super Game",
        "subgenre": "Simulation",
        "mechanic": "Idle",
        "current_rank": 3,
        "delta_1d": 25,
        "cross_market_count": 6,
        "opportunity_score": 80.0,
        "opportunity_badge": "HOT WAVE"
    }]
    csv_str = export_radar_to_csv(radar_items)
    assert csv_str.startswith('﻿')
    assert "Super Game" in csv_str
    assert "HOT WAVE" in csv_str
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `pytest tests/test_stats_export.py -v`
Expected: FAIL.

- [ ] **Step 3: Cài đặt `shortlist.py` và `exporter.py`**

Tạo `src/casual_scout/stats/shortlist.py`:
```python
from datetime import UTC, datetime
import uuid
from typing import Any
from casual_scout.storage import Repository

class ShortlistService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def bookmark_game(
        self,
        app_id: str,
        title: str,
        primary_country: str,
        rank_at_bookmark: int,
        icon_url: str | None = None,
        developer: str | None = None,
        subgenre: str | None = None,
        mechanic: str | None = None,
        opportunity_score: float | None = None,
        notes: str | None = None,
        priority: str = "MEDIUM",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        now_str = datetime.now(UTC).isoformat()
        existing = self.repo.get_shortlist_item_by_app_id(app_id)
        
        item = {
            "id": existing["id"] if existing else str(uuid.uuid4()),
            "app_id": app_id,
            "title": title,
            "icon_url": icon_url,
            "developer": developer,
            "subgenre": subgenre,
            "mechanic": mechanic,
            "primary_country": primary_country,
            "rank_at_bookmark": rank_at_bookmark,
            "opportunity_score": opportunity_score,
            "status": existing["status"] if existing else "CONSIDERING",
            "priority": priority or (existing["priority"] if existing else "MEDIUM"),
            "notes": notes if notes is not None else (existing.get("notes") if existing else ""),
            "tags": tags if tags is not None else (existing.get("tags") if existing else []),
            "created_at": existing["created_at"] if existing else now_str,
            "updated_at": now_str,
        }
        self.repo.save_shortlist_item(item)
        return item

    def list_shortlists(self, status: str | None = None, priority: str | None = None) -> list[dict]:
        return self.repo.get_shortlist_items(status=status, priority=priority)

    def update_item(self, app_id: str, updates: dict) -> bool:
        updates["updated_at"] = datetime.now(UTC).isoformat()
        return self.repo.update_shortlist_item(app_id, updates)

    def remove_item(self, app_id: str) -> bool:
        return self.repo.delete_shortlist_item(app_id)
```

Tạo `src/casual_scout/stats/exporter.py`:
```python
import csv
import io
import json
from typing import Any

def export_shortlist_to_csv(items: list[dict]) -> str:
    output = io.StringIO()
    output.write('﻿')
    writer = csv.writer(output)
    
    writer.writerow([
        "App ID", "Title", "Developer", "Subgenre", "Mechanic",
        "Primary Country", "Rank At Bookmark", "Opportunity Score",
        "Status", "Priority", "Notes", "Tags", "Updated At"
    ])
    
    for it in items:
        writer.writerow([
            it.get("app_id"),
            it.get("title"),
            it.get("developer") or "",
            it.get("subgenre") or "",
            it.get("mechanic") or "",
            it.get("primary_country"),
            it.get("rank_at_bookmark"),
            it.get("opportunity_score") or "",
            it.get("status"),
            it.get("priority"),
            it.get("notes") or "",
            ", ".join(it.get("tags") or []),
            it.get("updated_at")
        ])
    return output.getvalue()

def export_radar_to_csv(radar_items: list[dict]) -> str:
    output = io.StringIO()
    output.write('﻿')
    writer = csv.writer(output)
    
    writer.writerow([
        "App ID", "Title", "Developer", "Subgenre", "Mechanic",
        "Current Rank", "Delta 1D", "Delta 3D", "Signal",
        "Cross Market Count", "Opportunity Score", "Opportunity Badge"
    ])
    
    for r in radar_items:
        writer.writerow([
            r.get("app_id"),
            r.get("title") or r.get("app_id"),
            r.get("developer") or "",
            r.get("subgenre") or "",
            r.get("mechanic") or "",
            r.get("current_rank"),
            r.get("delta_1d") or "",
            r.get("delta_3d") or "",
            r.get("signal") or "",
            r.get("cross_market_count") or 1,
            r.get("opportunity_score") or 0.0,
            r.get("opportunity_badge") or ""
        ])
    return output.getvalue()

def export_to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Chạy test để xác nhận vượt qua**

Run: `pytest tests/test_stats_export.py -v`
Expected: PASS

---

### Task 5: Web UI & REST API Endpoints Cho Dashboard & Shortlist

**Files:**
- Modify: `src/casual_scout/web/views.py`
- Modify: `src/casual_scout/web/app.py`
- Create: `src/casual_scout/web/templates/dashboard.html`
- Create: `src/casual_scout/web/templates/shortlist.html`
- Modify: `src/casual_scout/web/templates/base.html`
- Test: `tests/test_web_stats.py`

**Interfaces:**
- Endpoints:
  - `GET /dashboard` (Render dashboard template)
  - `GET /shortlist` (Render shortlist template)
  - `GET /api/stats/summary`
  - `GET /api/stats/heatmap`
  - `GET /api/stats/trends`
  - `GET /api/stats/radar`
  - `GET /api/shortlist`
  - `POST /api/shortlist`
  - `PATCH /api/shortlist/{app_id}`
  - `DELETE /api/shortlist/{app_id}`
  - `GET /api/export/shortlist`
  - `GET /api/export/radar`

- [ ] **Step 1: Viết test cho Web Dashboard & Shortlist Endpoints**

Tạo file `tests/test_web_stats.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from casual_scout.storage import Repository
from casual_scout.web.app import create_app

@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    repo = Repository(tmp_path / "data")
    repo.initialize()
    app = create_app(repo)
    return TestClient(app)

def test_web_dashboard_page(client: TestClient):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Market Research Dashboard" in resp.text
    assert "Opportunity Radar" in resp.text

def test_web_shortlist_page(client: TestClient):
    resp = client.get("/shortlist")
    assert resp.status_code == 200
    assert "Opportunity Shortlist" in resp.text

def test_api_shortlist_crud(client: TestClient):
    add_resp = client.post("/api/shortlist", json={
        "app_id": "1001",
        "title": "Royal Match",
        "primary_country": "vn",
        "rank_at_bookmark": 1,
        "subgenre": "Puzzle",
        "mechanic": "Match-3",
        "priority": "HIGH",
        "notes": "Excellent meta layer"
    })
    assert add_resp.status_code == 200
    assert add_resp.json()["app_id"] == "1001"
    
    list_resp = client.get("/api/shortlist")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    
    patch_resp = client.patch("/api/shortlist/1001", json={"status": "PROTOTYPE"})
    assert patch_resp.status_code == 200
    
    del_resp = client.delete("/api/shortlist/1001")
    assert del_resp.status_code == 200
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `pytest tests/test_web_stats.py -v`
Expected: FAIL (404 Not Found).

- [ ] **Step 3: Cài đặt views & templates**

Cập nhật `base.html` và viết các template `dashboard.html`, `shortlist.html` cùng endpoints xử lý trong `views.py` và `app.py`.

- [ ] **Step 4: Chạy test để xác nhận vượt qua**

Run: `pytest tests/test_web_stats.py -v`
Expected: PASS

---

### Task 6: Tích Hợp CLI Thống Kê & Báo Cáo Cơ Hội (`cli.py`)

**Files:**
- Modify: `src/casual_scout/cli.py`
- Test: `tests/test_cli_stats.py`

**Interfaces:**
- CLI Commands:
  - `casual-scout stats overview [--date YYYY-MM-DD] [--country COUNTRY]`
  - `casual-scout stats radar [--date YYYY-MM-DD] [--limit N]`
  - `casual-scout shortlist list`
  - `casual-scout shortlist add <app_id> --title <title> --country <country> --rank <rank>`
  - `casual-scout export shortlist --format csv|json [--output path]`

- [ ] **Step 1: Viết test cho CLI stats commands**

Tạo file `tests/test_cli_stats.py`:
```python
import pytest
from casual_scout.cli import main

def test_cli_stats_radar_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["stats", "radar", "--help"])
    assert e.value.code == 0
    captured = capsys.readouterr()
    assert "radar" in captured.out

def test_cli_shortlist_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["shortlist", "--help"])
    assert e.value.code == 0
    captured = capsys.readouterr()
    assert "shortlist" in captured.out
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `pytest tests/test_cli_stats.py -v`
Expected: FAIL.

- [ ] **Step 3: Cập nhật `cli.py` với subcommands mới**

Bổ sung `stats` subparser (`overview`, `radar`) và `shortlist` subparser (`list`, `add`, `export`) vào `src/casual_scout/cli.py`.

- [ ] **Step 4: Chạy test để xác nhận vượt qua**

Run: `pytest tests/test_cli_stats.py -v`
Expected: PASS

---

### Task 7: End-to-End Acceptance Tests & Nghiệm Thu Phase 3

**Files:**
- Create: `tests/test_p3_acceptance.py`

- [ ] **Step 1: Viết E2E Acceptance Test cho toàn bộ chu trình P3**

Tạo file `tests/test_p3_acceptance.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from casual_scout.storage import Repository
from casual_scout.web.app import create_app

def test_p3_end_to_end_flow(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    
    records = [
        {
            "id": f"an-{i}",
            "date": "2026-09-11",
            "country": "vn",
            "app_id": f"app-{i}",
            "current_rank": i,
            "rank_1d_ago": i + 25 if i <= 10 else None,
            "delta_1d": 25 if i <= 10 else None,
            "rank_3d_ago": None,
            "delta_3d": None,
            "rank_7d_ago": None,
            "delta_7d": None,
            "signal": "FAST_RISER" if i <= 10 else "STEADY",
            "signal_reasons": ["delta_1d >= 20"],
            "subgenre": "Puzzle" if i % 2 == 0 else "Simulation",
            "mechanic": "Match-3" if i % 2 == 0 else "Idle",
            "mechanic_evidence": "match gems",
            "mechanic_confidence": "high",
            "cross_market_count": 8 if i <= 5 else 1,
            "cross_markets": ["vn", "th", "sg", "ph", "id", "my", "us", "tw"],
            "created_at": "2026-09-11T00:00:00Z"
        }
        for i in range(1, 21)
    ]
    repo.save_daily_analytics(records)
    
    app = create_app(repo)
    client = TestClient(app)
    
    summary_resp = client.get("/api/stats/summary?date=2026-09-11&country=all")
    assert summary_resp.status_code == 200
    data = summary_resp.json()
    assert data["total_games"] == 20
    assert "Puzzle" in data["genre_distribution"]["breakdown"]
    
    radar_resp = client.get("/api/stats/radar?date=2026-09-11")
    assert radar_resp.status_code == 200
    radar_data = radar_resp.json()
    assert len(radar_data) == 20
    assert radar_data[0]["opportunity_score"] >= 75.0
    assert radar_data[0]["opportunity_badge"] == "HOT WAVE"
    
    top_game = radar_data[0]
    bm_resp = client.post("/api/shortlist", json={
        "app_id": top_game["app_id"],
        "title": "Top Trending Game",
        "primary_country": "vn",
        "rank_at_bookmark": top_game["current_rank"],
        "opportunity_score": top_game["opportunity_score"],
        "notes": "Verified top opportunity candidate"
    })
    assert bm_resp.status_code == 200
    
    csv_resp = client.get("/api/export/shortlist?format=csv")
    assert csv_resp.status_code == 200
    assert "Top Trending Game" in csv_resp.text
    assert "Verified top opportunity candidate" in csv_resp.text
```

- [ ] **Step 2: Chạy toàn bộ test suite để xác nhận 100% đạt chuẩn**

Run: `pytest -v`
Expected: 100% tests PASS without error.
