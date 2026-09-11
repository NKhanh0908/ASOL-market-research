# Phase 2 (P2): Engine Phân Tích & Phát Hiện Game Casual Trend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng Engine phân tích dữ liệu tự động cho Phase 2: tính toán biến động thứ hạng (Rank Delta $\Delta_{1D}, \Delta_{3D}, \Delta_{7D}$), phát hiện game trend (`NEW_ENTRY`, `FAST_RISER`, `FALLING`, `STEADY`), phân loại 2 tầng thể loại phụ và cơ chế chơi (`Match-3`, `Merge`, `Sort`, `Idle`, `Runner`, ...), đo độ phủ thị trường khu vực, và nâng cấp Web UI localhost cùng lệnh CLI.

**Architecture:** Mở rộng cơ sở dữ liệu SQLite với các bảng materialized analytics (`daily_canonical_snapshots`, `daily_rank_analytics`). Tách biệt các module phân tích chuyên biệt trong `src/casual_scout/analysis/` (`taxonomy.py`, `signals.py`, `delta.py`, `service.py`), tích hợp điều phối vào CLI và nâng cấp giao diện Web FastAPI/Jinja2.

**Tech Stack:** Python 3.12+, SQLite 3 (WAL mode), FastAPI, Jinja2, Pytest.

**Spec:** [`docs/superpowers/specs/2026-09-10-p2-analysis-trend-engine-design.md`](file:///D:/Working/ASOL/tool/ASOL-market-research/docs/superpowers/specs/2026-09-10-p2-analysis-trend-engine-design.md)

## Global Constraints

- **Chi phí $0 (Free-First):** Toàn bộ phân tích chạy hoàn toàn cục bộ trên máy Windows, không dùng API trả phí hay gọi dịch vụ ngoài.
- **Tính Minh Bạch & Bằng Chứng:** Delta chỉ tính khi có snapshot thực tế đầy đủ tại mốc thời gian đối chiếu; thiếu ngày đối chiếu thì $\Delta = \text{null}$, tuyệt đối không bịa số 0 hoặc gán mốc thời gian giả. Phân loại cơ chế phải lưu trích dẫn từ khóa tìm thấy.
- **Bảo toàn Dữ liệu:** Không làm ảnh hưởng đến tính bất biến của các bảng snapshot và raw storage đã có ở Phase 1.
- **Tương thích Windows:** Mọi xử lý file, database, timestamp tuân thủ chuẩn UTC lưu trữ và UTC+7 hiển thị.

---

### Task 1: Mở Rộng Schema & Repository Cho Dữ Liệu Phân Tích

**Files:**
- Modify: `src/casual_scout/storage/schema.sql`
- Modify: `src/casual_scout/storage/repository.py`
- Test: `tests/test_analytics_storage.py`

**Interfaces:**
- Consumes: `Repository._connect()`, `Repository._write_connection()`
- Produces:
  - `repo.save_canonical_snapshot(date_str: str, country: str, snapshot_id: str, observed_at: str) -> None`
  - `repo.get_canonical_snapshot(date_str: str, country: str) -> dict | None`
  - `repo.save_daily_analytics(records: list[dict]) -> None`
  - `repo.get_daily_analytics(date_str: str, country: str, signal: str | None = None) -> list[dict]`
  - `repo.get_app_rank_history(app_id: str, country: str, limit: int = 14) -> list[dict]`

- [x] **Step 1: Viết test thất bại (Failing Test) cho Analytics Storage**

Tạo file `tests/test_analytics_storage.py`:
```python
from datetime import UTC, datetime
from pathlib import Path
import pytest
from casual_scout.storage import Repository

@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "data")
    r.initialize()
    return r

def test_canonical_snapshot_crud(repo: Repository):
    # Should be None initially
    assert repo.get_canonical_snapshot("2026-09-10", "vn") is None
    
    # Needs a valid snapshot_id from a real run or dummy insert
    with repo._write_connection() as conn:
        conn.execute("INSERT INTO runs (id, request_key, trigger, status, started_at) VALUES ('run-1', 'req-1', 'manual', 'completed', '2026-09-10T00:00:00Z')")
        conn.execute("INSERT INTO charts (id, provider, platform, country, collection, genre, depth, version, endpoint, created_at) VALUES ('chart-1', 'apple', 'ios', 'vn', 'topfreeapplications', '7003', 100, 1, 'url', '2026-09-10T00:00:00Z')")
        conn.execute("INSERT INTO market_runs (id, run_id, chart_id, chart_status, enrichment_status, started_at) VALUES ('mr-1', 'run-1', 'chart-1', 'complete', 'complete', '2026-09-10T00:00:00Z')")
        conn.execute("INSERT INTO snapshots (id, market_run_id, raw_hash, observed_at, quality, issues_json) VALUES ('snap-1', 'mr-1', 'hash-1', '2026-09-10T00:00:00Z', 'complete', '[]')")
    
    repo.save_canonical_snapshot("2026-09-10", "vn", "snap-1", "2026-09-10T00:00:00Z")
    canonical = repo.get_canonical_snapshot("2026-09-10", "vn")
    assert canonical is not None
    assert canonical["snapshot_id"] == "snap-1"

def test_daily_analytics_crud(repo: Repository):
    records = [
        {
            "id": "an-1",
            "date": "2026-09-10",
            "country": "vn",
            "app_id": "123456",
            "current_rank": 5,
            "rank_1d_ago": 30,
            "delta_1d": 25,
            "rank_3d_ago": None,
            "delta_3d": None,
            "rank_7d_ago": None,
            "delta_7d": None,
            "signal": "FAST_RISER",
            "signal_reasons": ["delta_1d >= 20 (+25)"],
            "subgenre": "Puzzle",
            "mechanic": "Match-3",
            "mechanic_evidence": "match 3 gems",
            "mechanic_confidence": "high",
            "cross_market_count": 3,
            "cross_markets": ["vn", "th", "sg"],
            "created_at": "2026-09-10T01:00:00Z",
        }
    ]
    repo.save_daily_analytics(records)
    results = repo.get_daily_analytics("2026-09-10", "vn")
    assert len(results) == 1
    assert results[0]["app_id"] == "123456"
    assert results[0]["signal"] == "FAST_RISER"
    assert results[0]["mechanic"] == "Match-3"
    assert results[0]["cross_market_count"] == 3

    # Test filtering by signal
    fast_risers = repo.get_daily_analytics("2026-09-10", "vn", signal="FAST_RISER")
    assert len(fast_risers) == 1
    new_entries = repo.get_daily_analytics("2026-09-10", "vn", signal="NEW_ENTRY")
    assert len(new_entries) == 0
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_analytics_storage.py -v`  
Expected: FAIL (bảng chưa tồn tại và method chưa có trong Repository).

- [x] **Step 3: Cập nhật `schema.sql` và thêm methods vào `repository.py`**

1. Thêm vào cuối `src/casual_scout/storage/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS daily_canonical_snapshots (
    date TEXT NOT NULL,
    country TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (date, country)
);

CREATE TABLE IF NOT EXISTS daily_rank_analytics (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    country TEXT NOT NULL,
    app_id TEXT NOT NULL,
    current_rank INTEGER NOT NULL,
    rank_1d_ago INTEGER,
    delta_1d INTEGER,
    rank_3d_ago INTEGER,
    delta_3d INTEGER,
    rank_7d_ago INTEGER,
    delta_7d INTEGER,
    signal TEXT NOT NULL,
    signal_reasons_json TEXT NOT NULL,
    subgenre TEXT,
    mechanic TEXT NOT NULL,
    mechanic_evidence TEXT,
    mechanic_confidence TEXT NOT NULL,
    cross_market_count INTEGER NOT NULL,
    cross_markets_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(date, country, app_id)
);

CREATE INDEX IF NOT EXISTS idx_analytics_date_country ON daily_rank_analytics(date, country);
CREATE INDEX IF NOT EXISTS idx_analytics_signal ON daily_rank_analytics(date, signal);
CREATE INDEX IF NOT EXISTS idx_analytics_app ON daily_rank_analytics(app_id);
```

2. Thêm methods vào `src/casual_scout/storage/repository.py`:
- `save_canonical_snapshot(date_str, country, snapshot_id, observed_at)`
- `get_canonical_snapshot(date_str, country)`
- `save_daily_analytics(records)`
- `get_daily_analytics(date_str, country, signal=None)`
- `get_app_rank_history(app_id, country, limit=14)`

- [x] **Step 4: Chạy lại test để xác nhận passed**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_analytics_storage.py -v`  
Expected: PASS (100%).

---

### Task 2: Engine Phân Loại Thể Loại Phụ & Cơ Chế Chơi (Taxonomy v1)

**Files:**
- Create: `src/casual_scout/analysis/taxonomy.py`
- Test: `tests/test_taxonomy.py`

**Interfaces:**
- Produces:
  - `classify_subgenre(apple_genres: list[str] | list[dict]) -> str`
  - `classify_mechanic(title: str, description: str, apple_subgenre: str) -> tuple[str, str | None, str]` (trả về `(mechanic, evidence, confidence)`)
  - `classify_app(name: str, description: str, genres: list[dict] | list[str]) -> dict` (trả về `{"subgenre": str, "mechanic": str, "evidence": str | None, "confidence": str}`)

- [x] **Step 1: Viết test cho Taxonomy & Mechanic Classification**

Tạo file `tests/test_taxonomy.py`:
```python
from casual_scout.analysis.taxonomy import classify_subgenre, classify_mechanic, classify_app

def test_classify_subgenre_extracts_apple_genre():
    genres = [{"name": "Games"}, {"name": "Casual"}, {"name": "Puzzle"}]
    assert classify_subgenre(genres) == "Puzzle"

    simulation_genres = ["Games", "Casual", "Simulation"]
    assert classify_subgenre(simulation_genres) == "Simulation"

    casual_only = [{"name": "Games"}, {"name": "Casual"}]
    assert classify_subgenre(casual_only) == "Casual"

def test_classify_mechanic_match3():
    title = "Royal Match"
    desc = "Solve match-3 puzzles and decorate the King's castle! Swap and match 3 items."
    mechanic, evidence, confidence = classify_mechanic(title, desc, "Puzzle")
    assert mechanic == "Match-3"
    assert "match-3" in evidence.lower()
    assert confidence == "high"

def test_classify_mechanic_merge():
    title = "Merge Mansion"
    desc = "A mysterious mansion. Merge items to restore the grounds."
    mechanic, evidence, confidence = classify_mechanic(title, desc, "Puzzle")
    assert mechanic == "Merge"
    assert "merge" in evidence.lower()
    assert confidence == "high"

def test_classify_mechanic_sorting_physics():
    title = "Water Sort Puzzle"
    desc = "Pour colored water into bottles until each bottle has only one color sort."
    mechanic, evidence, confidence = classify_mechanic(title, desc, "Puzzle")
    assert mechanic == "Sort"
    assert "water sort" in evidence.lower()
    assert confidence == "high"

def test_classify_mechanic_idle():
    title = "Idle Mining Factory"
    desc = "Build your mining empire and become an idle tycoon."
    mechanic, evidence, confidence = classify_mechanic(title, desc, "Simulation")
    assert mechanic == "Idle"
    assert "idle" in evidence.lower()

def test_classify_mechanic_runner():
    title = "Subway Surfers"
    desc = "Dash as fast as you can through the subway runner tracks."
    mechanic, evidence, confidence = classify_mechanic(title, desc, "Action")
    assert mechanic == "Runner"

def test_classify_mechanic_general_fallback():
    title = "Unknown Game"
    desc = "Have fun playing this game with friends."
    mechanic, evidence, confidence = classify_mechanic(title, desc, "Casual")
    assert mechanic == "General"
    assert evidence is None
    assert confidence == "unknown"
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_taxonomy.py -v`  
Expected: FAIL (module `casual_scout.analysis.taxonomy` chưa tồn tại).

- [x] **Step 3: Hiện thực `src/casual_scout/analysis/taxonomy.py`**

Hiện thực logic nhận diện 2 tầng với các từ điển từ khóa chuẩn (`Match-3`, `Merge`, `Sort`, `Idle`, `Runner`, `Card / Board`, `Word / Trivia`, `Drawing`).

- [x] **Step 4: Chạy test để xác nhận passed**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_taxonomy.py -v`  
Expected: PASS (100%).

---

### Task 3: Engine Tính Toán Delta, Gắn Nhãn Trend & Đo Độ Phủ

**Files:**
- Create: `src/casual_scout/analysis/signals.py`
- Create: `src/casual_scout/analysis/delta.py`
- Test: `tests/test_signals.py`
- Test: `tests/test_delta.py`

**Interfaces:**
- Produces:
  - `evaluate_signal(current_rank: int, rank_1d: int | None, delta_1d: int | None, delta_3d: int | None, has_1d_snapshot: bool) -> tuple[str, list[str]]` (trả về `(signal, reasons)`)
  - `compute_rank_deltas(current_entries: list[dict], prev_1d_map: dict[str, int] | None, prev_3d_map: dict[str, int] | None, prev_7d_map: dict[str, int] | None) -> list[dict]`
  - `compute_cross_market_presence(all_market_entries: dict[str, list[str]]) -> dict[str, tuple[int, list[str]]]` (trả về map `app_id -> (count, country_list)`)

- [x] **Step 1: Viết test cho Signals và Delta Calculation**

1. Tạo `tests/test_signals.py`:
```python
from casual_scout.analysis.signals import evaluate_signal

def test_fast_riser_1d():
    signal, reasons = evaluate_signal(current_rank=15, rank_1d=40, delta_1d=25, delta_3d=10, has_1d_snapshot=True)
    assert signal == "FAST_RISER"
    assert any("delta_1d >= 20" in r for r in reasons)

def test_fast_riser_3d():
    signal, reasons = evaluate_signal(current_rank=10, rank_1d=15, delta_1d=5, delta_3d=35, has_1d_snapshot=True)
    assert signal == "FAST_RISER"
    assert any("delta_3d >= 30" in r for r in reasons)

def test_new_entry_when_1d_snapshot_exists():
    signal, reasons = evaluate_signal(current_rank=50, rank_1d=None, delta_1d=None, delta_3d=None, has_1d_snapshot=True)
    assert signal == "NEW_ENTRY"
    assert "new_entry_in_top100" in reasons

def test_no_new_entry_when_1d_snapshot_missing():
    # If 1d snapshot is missing, cannot claim new entry
    signal, reasons = evaluate_signal(current_rank=50, rank_1d=None, delta_1d=None, delta_3d=None, has_1d_snapshot=False)
    assert signal == "NONE"

def test_falling():
    signal, reasons = evaluate_signal(current_rank=70, rank_1d=40, delta_1d=-30, delta_3d=-35, has_1d_snapshot=True)
    assert signal == "FALLING"

def test_steady():
    signal, reasons = evaluate_signal(current_rank=20, rank_1d=22, delta_1d=2, delta_3d=3, has_1d_snapshot=True)
    assert signal == "STEADY"
```

2. Tạo `tests/test_delta.py`:
```python
from casual_scout.analysis.delta import compute_rank_deltas, compute_cross_market_presence

def test_compute_rank_deltas_with_missing_dates():
    current_entries = [{"app_id": "app-1", "rank": 10}, {"app_id": "app-2", "rank": 20}]
    prev_1d = {"app-1": 35} # app-2 is new
    prev_3d = None # 3D snapshot was missing
    prev_7d = {"app-1": 50, "app-2": 80}

    deltas = compute_rank_deltas(current_entries, prev_1d, prev_3d, prev_7d)
    
    # app-1
    assert deltas["app-1"]["current_rank"] == 10
    assert deltas["app-1"]["rank_1d_ago"] == 35
    assert deltas["app-1"]["delta_1d"] == 25
    assert deltas["app-1"]["delta_3d"] is None # Must be None, not 0!
    assert deltas["app-1"]["delta_7d"] == 40
    
    # app-2
    assert deltas["app-2"]["rank_1d_ago"] is None
    assert deltas["app-2"]["delta_1d"] is None
    assert deltas["app-2"]["delta_7d"] == 60

def test_compute_cross_market_presence():
    market_data = {
        "vn": ["app-1", "app-2", "app-3"],
        "us": ["app-1", "app-4"],
        "th": ["app-1", "app-2"],
    }
    presence = compute_cross_market_presence(market_data)
    assert presence["app-1"] == (3, ["vn", "us", "th"])
    assert presence["app-2"] == (2, ["vn", "th"])
    assert presence["app-3"] == (1, ["vn"])
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_signals.py tests/test_delta.py -v`  
Expected: FAIL.

- [x] **Step 3: Hiện thực `signals.py` và `delta.py`**

1. Hiện thực `src/casual_scout/analysis/signals.py`.
2. Hiện thực `src/casual_scout/analysis/delta.py`.

- [x] **Step 4: Chạy test để xác nhận passed**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_signals.py tests/test_delta.py -v`  
Expected: PASS (100%).

---

### Task 4: Analysis Service Điều Phối & Lệnh CLI

**Files:**
- Create: `src/casual_scout/analysis/service.py`
- Create: `src/casual_scout/analysis/__init__.py`
- Modify: `src/casual_scout/cli.py`
- Test: `tests/test_analysis_service.py`
- Test: `tests/test_cli_analysis.py`

**Interfaces:**
- Produces:
  - `AnalysisService(repo).analyze_date(target_date: str) -> dict` (phân tích toàn bộ 11 thị trường của ngày `target_date`)
  - CLI `casual_scout analyze [--date YYYY-MM-DD] [--data-dir PATH]`
  - CLI `casual_scout trends [--country vn] [--signal fast_riser|new_entry] [--date YYYY-MM-DD] [--data-dir PATH]`

- [x] **Step 1: Viết test cho AnalysisService và CLI**

1. Tạo `tests/test_analysis_service.py`:
```python
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from casual_scout.storage import Repository
from casual_scout.analysis.service import AnalysisService

@pytest.fixture
def repo_with_consecutive_days(tmp_path: Path, evidence_dir: Path) -> Repository:
    repo = Repository(tmp_path / "data")
    repo.initialize()
    
    from casual_scout.providers.apple import parse_chart
    from casual_scout.models import Chart, HttpResult
    
    body = (evidence_dir / "vn-casual-100.json").read_bytes()
    parsed = parse_chart(body, Chart("vn"))
    
    # Create Day 1 (2026-09-09) and Day 2 (2026-09-10)
    for date_str, offset_day in [("2026-09-09", 1), ("2026-09-10", 0)]:
        dt = datetime(2026, 9, 10, 0, 0, tzinfo=UTC) - timedelta(days=offset_day)
        with repo._write_connection() as conn:
            conn.execute("INSERT INTO runs (id, request_key, trigger, status, started_at) VALUES (?, ?, 'manual', 'completed', ?)", (f"run-{date_str}", f"req-{date_str}", dt.isoformat()))
            conn.execute("INSERT OR IGNORE INTO charts (id, provider, platform, country, collection, genre, depth, version, endpoint, created_at) VALUES ('c-vn', 'apple', 'ios', 'vn', 'topfreeapplications', '7003', 100, 1, 'url', ?)", (dt.isoformat(),))
            conn.execute("INSERT INTO market_runs (id, run_id, chart_id, chart_status, enrichment_status, started_at) VALUES (?, ?, 'c-vn', 'complete', 'complete', ?)", (f"mr-{date_str}", f"run-{date_str}", dt.isoformat()))
        
        http_res = HttpResult(url="https://itunes.apple.com/vn/rss/...", started_at=dt, elapsed_ms=50, status=200, body=body, headers={}, error=None)
        repo.save_snapshot(f"run-{date_str}", http_res, parsed)
    
    return repo

def test_analysis_service_runs_and_stores_analytics(repo_with_consecutive_days: Repository):
    service = AnalysisService(repo_with_consecutive_days)
    summary = service.analyze_date("2026-09-10")
    
    assert summary["date"] == "2026-09-10"
    assert "vn" in summary["processed_countries"]
    
    analytics = repo_with_consecutive_days.get_daily_analytics("2026-09-10", "vn")
    assert len(analytics) == 100
    assert analytics[0]["delta_1d"] is not None
```

2. Tạo `tests/test_cli_analysis.py`:
```python
from pathlib import Path
from casual_scout.cli import main

def test_cli_analyze_command(tmp_path: Path):
    from casual_scout.storage import Repository
    repo = Repository(tmp_path / "data")
    repo.initialize()
    
    code = main(["analyze", "--date", "2026-09-10", "--data-dir", str(tmp_path / "data")])
    assert code == 0

def test_cli_trends_command(tmp_path: Path):
    from casual_scout.storage import Repository
    repo = Repository(tmp_path / "data")
    repo.initialize()
    
    code = main(["trends", "--country", "vn", "--data-dir", str(tmp_path / "data")])
    assert code == 0
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_analysis_service.py tests/test_cli_analysis.py -v`  
Expected: FAIL.

- [x] **Step 3: Hiện thực `AnalysisService` và mở rộng `cli.py`**

1. Hiện thực `src/casual_scout/analysis/service.py`.
2. Thêm subcommands `analyze` và `trends` vào `src/casual_scout/cli.py`.

- [x] **Step 4: Chạy test để xác nhận passed**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_analysis_service.py tests/test_cli_analysis.py -v`  
Expected: PASS (100%).

---

### Task 5: Nâng Cấp Web UI (Delta, Mechanics, Badges, Quick Filters & CSV Export)

**Files:**
- Modify: `src/casual_scout/web/views.py`
- Modify: `src/casual_scout/web/app.py`
- Modify: `src/casual_scout/web/templates/data.html`
- Modify: `src/casual_scout/web/templates/game.html`
- Modify: `src/casual_scout/web/static/app.css`
- Test: `tests/test_web_analysis.py`

**Interfaces:**
- Consumes: `repo.get_daily_analytics()`, `repo.get_app_rank_history()`
- Produces:
  - Dashboard `/`: Hỗ trợ query params `tab=all|fast_risers|new_entries`, hiển thị Delta badges, Subgenre/Mechanic badges, Cross-market badges.
  - Game Detail `/games/{app_id}`: Hiển thị Rank History Table (D, D-1, D-3, D-7), Classification Evidence box, Cross-market presence list.
  - CSV Export `/data/download`: Xuất thêm `rank_1d_ago, delta_1d, delta_3d, delta_7d, signal, subgenre, mechanic, cross_market_count`.

- [x] **Step 1: Viết test cho Web UI Analytics & Filters**

Tạo `tests/test_web_analysis.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app

@pytest.fixture
def web_client(tmp_path: Path) -> tuple[Repository, TestClient]:
    settings = Settings(tmp_path / "data")
    repo = Repository(tmp_path / "data")
    repo.initialize()
    
    # Seed dummy daily analytics record
    record = {
        "id": "an-1",
        "date": "2026-09-10",
        "country": "vn",
        "app_id": "app-test-1",
        "current_rank": 1,
        "rank_1d_ago": 30,
        "delta_1d": 29,
        "rank_3d_ago": 50,
        "delta_3d": 49,
        "rank_7d_ago": None,
        "delta_7d": None,
        "signal": "FAST_RISER",
        "signal_reasons": ["delta_1d >= 20 (+29)"],
        "subgenre": "Puzzle",
        "mechanic": "Match-3",
        "mechanic_evidence": "match 3 items",
        "mechanic_confidence": "high",
        "cross_market_count": 5,
        "cross_markets": ["vn", "us", "th", "sg", "id"],
        "created_at": "2026-09-10T00:00:00Z",
    }
    repo.save_daily_analytics([record])
    
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    return repo, client

def test_web_dashboard_displays_analysis_badges(web_client):
    repo, client = web_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Fast Risers" in resp.text
    assert "New Entries" in resp.text

def test_web_csv_export_contains_analytics_columns(web_client):
    repo, client = web_client
    resp = client.get("/data/download?country=vn&format=csv")
    assert resp.status_code == 200
    assert "delta_1d" in resp.text
    assert "signal" in resp.text
    assert "mechanic" in resp.text
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_web_analysis.py -v`  
Expected: FAIL.

- [x] **Step 3: Cập nhật View Models, Templates và Endpoints**

1. Cập nhật `src/casual_scout/web/views.py`: Nối dữ liệu từ `daily_rank_analytics` vào `get_data_view` và `get_game_view`.
2. Cập nhật `src/casual_scout/web/templates/data.html`: Thêm tab bộ lọc nhanh (`Tất cả`, `⚡ Fast Risers`, `🟢 New Entries`), thêm các cột Delta, Phân loại & Cơ chế, Độ phủ khu vực.
3. Cập nhật `src/casual_scout/web/templates/game.html`: Bảng lịch sử rank và hộp căn cứ trích dẫn từ khóa.
4. Cập nhật `src/casual_scout/web/static/app.css`: Thêm kiểu dáng badge cho `badge-fast-riser`, `badge-new-entry`, `badge-mechanic`.
5. Cập nhật `src/casual_scout/web/app.py`: Bổ sung các cột phân tích vào endpoint `/data/download`.

- [x] **Step 4: Chạy test để xác nhận passed**

Chạy: `.\.venv\Scripts\python.exe -m pytest tests/test_web_analysis.py -v`  
Expected: PASS (100%).

---

### Task 6: Nghiệm Thu Tích Hợp Phase 2 & Xác Nhận Toàn Bộ Hệ Thống

**Files:**
- Create: `tests/test_p2_acceptance.py`
- Create: `docs/operations/p2-acceptance.md`

- [x] **Step 1: Viết test nghiệm thu tích hợp End-to-End cho Phase 2 (`test_p2_acceptance.py`)**

Bao phủ toàn bộ luồng:
1. Fake Collector thu thập 2 ngày liên tiếp cho các thị trường VN, US, TH.
2. `AnalysisService` chạy phân tích tự động.
3. Kiểm tra tính toán chính xác $\Delta_{1D}$, gán nhãn `FAST_RISER` và `NEW_ENTRY`.
4. Kiểm tra phân loại `Match-3`, `Merge`, `Sort` có bằng chứng trích dẫn.
5. Kiểm tra Web UI hiển thị bảng phân tích và tải CSV đầy đủ 100%.

- [x] **Step 2: Chạy toàn bộ test suite và kiểm tra chất lượng code**

Chạy:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pip check
```
Expected: 100% tests pass, Ruff linter sạch 0 lỗi, dependencies hợp lệ.

- [x] **Step 3: Ghi nhận báo cáo nghiệm thu Phase 2 (`docs/operations/p2-acceptance.md`)**

Tạo tài liệu nghiệm thu tổng kết Phase 2 với đầy đủ bằng chứng kiểm tra và số liệu thực tế.

---

## 🎯 Bàn Giao Thực Thi (Execution Options)

Kế hoạch đã sẵn sàng để thực thi. Bạn có 2 phương án lựa chọn:

1. **Subagent-Driven Development (Khuyến nghị):** Mình sẽ kích hoạt subagent chuyên biệt thực hiện tuần tự từng Task, kiểm tra TDD và review checkpoint sau mỗi Task.
2. **Inline Execution (Thực hiện trực tiếp):** Thực thi từng Task trong phiên hội thoại này với các điểm dừng review.

👉 Bạn muốn chọn phương án thực thi nào?
