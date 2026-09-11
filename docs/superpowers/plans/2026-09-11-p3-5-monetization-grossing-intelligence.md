# Phase 3.5: Monetization & Grossing Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Casual Scout with Top Grossing chart collection, In-App Purchase (IAP) metadata parsing, automated Monetization Model classification (`PURE_IAP`, `HYBRID`, `PURE_ADS`, `PAID_PREMIUM`), Download vs. Revenue correlation signals (`HIGH_GROSSING_EFFICIENCY`), Opportunity Radar v1.5 with Grossing Power, and interactive Web UI dual-chart tabs.

**Architecture:** 
1. Database schema migration for multi-chart storage and IAP/monetization attributes.
2. Apple provider and collection extensions for Top Grossing RSS and IAP lookup.
3. Deterministic Monetization Classifier and Correlation Matrix engine.
4. Opportunity Radar v1.5 scoring formula (100-point scale factoring Grossing Power).
5. Web UI dual-chart tabs on `/data`, IAP breakdown cards on `/games/{country}/{app_id}`, and CLI parameter extensions.

**Tech Stack:** Python 3.12, SQLite (WAL mode), FastAPI, Jinja2, Chart.js, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-p3-5-monetization-grossing-intelligence-design.md`

## Global Constraints
- Target 12 countries: `vn`, `us`, `sg`, `th`, `id`, `my`, `ph`, `kh`, `la`, `mm`, `bn`, and `tl` (unverified).
- Zero cost ($0 budget) using free Apple RSS and iTunes APIs.
- Non-destructive SQLite schema migrations (idempotent `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS`).
- Deterministic, explainable opportunity scoring and monetization classification.
- All CSV exports use `utf-8-sig` (UTF-8 with BOM) for Microsoft Excel compatibility.
- 100% automated test coverage with regression validation.

---

### Task 1: Schema Evolution & Multi-Chart Storage Models

**Files:**
- Modify: `src/casual_scout/models/chart.py`
- Modify: `src/casual_scout/storage/schema.sql`
- Modify: `src/casual_scout/storage/repository.py`
- Test: `tests/test_monetization_storage.py`

**Interfaces:**
- Consumes: Existing SQLite tables (`charts`, `metadata_versions`, `daily_rank_analytics`).
- Produces: `Chart(country, feed_type="top-free"|"top-grossing")`, repository migration creating `in_app_purchases_json`, `has_in_app_purchases`, `monetization_model`, `grossing_rank`, `free_rank`, `monetization_efficiency_flag`.

- [ ] **Step 1: Write failing tests for chart models and schema migrations**

```python
# tests/test_monetization_storage.py
from pathlib import Path
import sqlite3
from casual_scout.models.chart import Chart
from casual_scout.storage.repository import Repository

def test_chart_supports_feed_type():
    c_free = Chart("vn", feed_type="top-free")
    c_grossing = Chart("vn", feed_type="top-grossing")
    assert c_free.feed_type == "top-free"
    assert c_grossing.feed_type == "top-grossing"
    assert c_free.id != c_grossing.id

def test_schema_migration_adds_monetization_columns(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    
    with sqlite3.connect(repo.database_path) as conn:
        # Check metadata_versions columns
        meta_cols = [r[1] for r in conn.execute("PRAGMA table_info(metadata_versions)").fetchall()]
        assert "in_app_purchases_json" in meta_cols
        assert "has_in_app_purchases" in meta_cols
        assert "monetization_model" in meta_cols
        
        # Check daily_rank_analytics columns
        an_cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_rank_analytics)").fetchall()]
        assert "grossing_rank" in an_cols
        assert "free_rank" in an_cols
        assert "monetization_model" in an_cols
        assert "monetization_efficiency_flag" in an_cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_monetization_storage.py -v`
Expected: FAIL

- [ ] **Step 3: Implement chart models and repository migration logic**

Update `src/casual_scout/models/chart.py`:
- Support `feed_type: str = "top-free"` in `Chart` dataclass.
- Adjust chart identity hashing to include `feed_type`.

Update `src/casual_scout/storage/schema.sql` and `src/casual_scout/storage/repository.py`:
- In `schema.sql`: add new columns with defaults.
- In `repository.py` `initialize()`: execute idempotent column addition migrations (`ALTER TABLE ... ADD COLUMN ...` catching duplicate column errors).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_monetization_storage.py -v`
Expected: PASS

---

### Task 2: Provider & Collector Top Grossing Chart Support

**Files:**
- Modify: `src/casual_scout/providers/apple.py`
- Modify: `src/casual_scout/collection/service.py`
- Test: `tests/test_monetization_collector.py`

**Interfaces:**
- Consumes: `AppleProvider.fetch_chart(chart, client)`
- Produces: `AppleProvider` supports `feed_type="top-grossing"`, `Collector.execute()` supports collecting both free and grossing charts with IAP metadata parsing.

- [ ] **Step 1: Write failing tests for Top Grossing collection**

```python
# tests/test_monetization_collector.py
from pathlib import Path
from casual_scout.models.chart import Chart
from casual_scout.providers.apple import AppleProvider
from casual_scout.config import Settings
from casual_scout.storage.repository import Repository
from casual_scout.collection.service import Collector
from casual_scout.collection.jobs import JobService

def test_apple_provider_constructs_grossing_url(tmp_path: Path):
    settings = Settings(tmp_path / "data")
    provider = AppleProvider(settings)
    c_free = Chart("vn", feed_type="top-free")
    c_grossing = Chart("vn", feed_type="top-grossing")
    
    url_free = provider.chart_url(c_free)
    url_grossing = provider.chart_url(c_grossing)
    
    assert "top-free" in url_free or "topfreeapplications" in url_free
    assert "top-paid" in url_grossing or "topgrossingapplications" in url_grossing or "top-grossing" in url_grossing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_monetization_collector.py -v`
Expected: FAIL

- [ ] **Step 3: Implement provider and collector multi-chart support**

Update `src/casual_scout/providers/apple.py`:
- Add URL builder support for `top-grossing` / `top-paid` feed.
- In `parse_lookup()`: parse `inAppPurchases`, `formattedPrice`, `price`, `currency`.

Update `src/casual_scout/collection/service.py`:
- Allow collecting multiple charts per country (`top-free` and `top-grossing`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_monetization_collector.py -v`
Expected: PASS

---

### Task 3: Monetization Classifier & Correlation Matrix Engine

**Files:**
- Create: `src/casual_scout/analysis/monetization.py`
- Modify: `src/casual_scout/analysis/service.py`
- Test: `tests/test_monetization_analysis.py`

**Interfaces:**
- Consumes: Metadata (price, IAP list, description) + Ranks (`free_rank`, `grossing_rank`).
- Produces: `classify_monetization_model()` -> `'PURE_IAP'` | `'HYBRID'` | `'PURE_ADS'` | `'PAID_PREMIUM'`, `compute_monetization_efficiency()` -> `'HIGH_GROSSING_EFFICIENCY'` | `'MEGA_HIT'` | `'VIRAL_FREE'` | `None`.

- [ ] **Step 1: Write failing tests for Monetization Classifier**

```python
# tests/test_monetization_analysis.py
from casual_scout.analysis.monetization import classify_monetization_model, compute_monetization_efficiency

def test_classify_paid_premium():
    model = classify_monetization_model(price=2.99, iap_list=[], free_rank=None, grossing_rank=5)
    assert model == "PAID_PREMIUM"

def test_classify_hybrid():
    model = classify_monetization_model(price=0.0, iap_list=[{"name": "No Ads", "price": 1.99}], free_rank=10, grossing_rank=25)
    assert model == "HYBRID"

def test_classify_pure_ads():
    model = classify_monetization_model(price=0.0, iap_list=[], free_rank=5, grossing_rank=None)
    assert model == "PURE_ADS"

def test_monetization_efficiency_signals():
    # Whale monetization: Free #60, Grossing #15
    sig1 = compute_monetization_efficiency(free_rank=60, grossing_rank=15)
    assert sig1 == "HIGH_GROSSING_EFFICIENCY"
    
    # Mega Hit: Free #3, Grossing #5
    sig2 = compute_monetization_efficiency(free_rank=3, grossing_rank=5)
    assert sig2 == "MEGA_HIT"
    
    # Viral Free: Free #2, Not in Grossing
    sig3 = compute_monetization_efficiency(free_rank=2, grossing_rank=None)
    assert sig3 == "VIRAL_FREE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_monetization_analysis.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `src/casual_scout/analysis/monetization.py` and integrate with `AnalysisService`**

Implement `classify_monetization_model` and `compute_monetization_efficiency` in `src/casual_scout/analysis/monetization.py`.
Integrate into `AnalysisService.analyze_date()` to persist `grossing_rank`, `free_rank`, `monetization_model`, and `monetization_efficiency_flag` into `daily_rank_analytics`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_monetization_analysis.py -v`
Expected: PASS

---

### Task 4: Opportunity Radar v1.5 with Grossing Power

**Files:**
- Modify: `src/casual_scout/stats/radar.py`
- Test: `tests/test_monetization_radar.py`

**Interfaces:**
- Consumes: `daily_rank_analytics` rows with `grossing_rank`, `monetization_model`, `monetization_efficiency_flag`.
- Produces: `calculate_opportunity_score_v15()`, `rank_opportunities()` returning items with `grossing_power`, `monetization_model`, `monetization_efficiency_flag`.

- [ ] **Step 1: Write failing tests for Opportunity Radar v1.5**

```python
# tests/test_monetization_radar.py
from casual_scout.stats.radar import calculate_opportunity_score_v15

def test_radar_v15_grossing_power_boost():
    # High momentum + High Grossing Rank #5
    score_with_grossing, breakdown = calculate_opportunity_score_v15(
        current_rank=10,
        delta_1d=20,
        delta_3d=30,
        signal="FAST_RISER",
        cross_market_count=8,
        grossing_rank=5,
        monetization_efficiency="MEGA_HIT"
    )
    assert breakdown["grossing_power"] == 15
    assert score_with_grossing >= 85
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_monetization_radar.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Opportunity Radar v1.5 scoring formula**

Update `src/casual_scout/stats/radar.py`:
- Factor in `grossing_power` (max 15 points) and efficiency bonus (+5 points for `HIGH_GROSSING_EFFICIENCY`).
- Cap score at 100.
- Return updated breakdown dictionary.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_monetization_radar.py -v`
Expected: PASS

---

### Task 5: Web UI & REST API Endpoints (Top Grossing Tabs & Dual Charts)

**Files:**
- Modify: `src/casual_scout/web/views.py`
- Modify: `src/casual_scout/web/app.py`
- Modify: `src/casual_scout/web/templates/data.html`
- Modify: `src/casual_scout/web/templates/dashboard.html`
- Modify: `src/casual_scout/web/templates/game.html`
- Test: `tests/test_web_monetization.py`

**Interfaces:**
- Consumes: `get_data_view`, `get_game_view`, `get_dashboard_view`.
- Produces: Tab switcher (`feed_type=top-free` vs `feed_type=top-grossing`), cross-chart rank badges, monetization model tags, IAP breakdown card on game details.

- [ ] **Step 1: Write failing tests for Web Monetization features**

```python
# tests/test_web_monetization.py
from pathlib import Path
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.storage.repository import Repository
from casual_scout.web.app import create_app

def test_data_view_feed_type_toggle(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    settings = Settings(tmp_path / "data")
    app = create_app(settings)
    client = TestClient(app)
    
    res_free = client.get("/data?country=vn&feed_type=top-free")
    assert res_free.status_code == 200
    assert "Top Free" in res_free.text
    
    res_grossing = client.get("/data?country=vn&feed_type=top-grossing")
    assert res_grossing.status_code == 200
    assert "Top Grossing" in res_grossing.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_web_monetization.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Web Views and Templates**

1. `views.py`: Support `feed_type: str = "top-free"` in `get_data_view`.
2. `templates/data.html`: Add sub-navigation tabs `[🆓 Top Free (100)]` vs `[💰 Top Grossing (100)]` and display monetization model badges.
3. `templates/dashboard.html`: Add Monetization Model chips in the Radar table.
4. `templates/game.html`: Add In-App Purchases card and dual rank history graph.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_web_monetization.py -v`
Expected: PASS

---

### Task 6: CLI Expansion (`collect --chart-type`, `stats radar --monetization`)

**Files:**
- Modify: `src/casual_scout/cli.py`
- Test: `tests/test_cli_monetization.py`

**Interfaces:**
- Consumes: CLI arguments `collect`, `stats radar`, `trends`.
- Produces: `--chart-type` and `--monetization` CLI options.

- [ ] **Step 1: Write failing tests for CLI flags**

```python
# tests/test_cli_monetization.py
import pytest
from casual_scout.cli import main

def test_cli_collect_chart_type_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["collect", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--chart-type" in captured.out or "--feed-type" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_cli_monetization.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI arguments**

Update `src/casual_scout/cli.py`:
- Add `--chart-type` to `collect` and `trends`.
- Add `--monetization` filter to `stats radar`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_cli_monetization.py -v`
Expected: PASS

---

### Task 7: End-to-End Acceptance Tests & Full Regression

**Files:**
- Create: `tests/test_p3_5_acceptance.py`

- [ ] **Step 1: Write full end-to-end acceptance test**

```python
# tests/test_p3_5_acceptance.py
from pathlib import Path
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.storage.repository import Repository
from casual_scout.web.app import create_app
from test_analysis_service import _create_snapshot_with_entries
from casual_scout.analysis.service import AnalysisService

def test_p3_5_end_to_end_flow(tmp_path: Path):
    data_dir = tmp_path / "data"
    repo = Repository(data_dir)
    repo.initialize()
    
    # Create Free and Grossing snapshots
    _create_snapshot_with_entries(
        repo=repo,
        run_id="run-p35-free",
        snap_id="snap-vn-free",
        country="vn",
        date_str="2026-09-11",
        observed_time_str="2026-09-11T08:00:00Z",
        entries=[
            ("1001", 1, "Royal Match"),
            ("1002", 5, "Block Blast"),
        ],
        metadata_map={
            "1001": {"description": "Match 3 puzzle", "price": 0.0, "in_app_purchases": [{"name": "Coin Pack", "price": 1.99}]},
            "1002": {"description": "Simple block game", "price": 0.0, "in_app_purchases": []},
        }
    )
    
    # Run analysis
    service = AnalysisService(repo)
    service.analyze_date("2026-09-11", countries=["vn"])
    
    settings = Settings(data_dir)
    app = create_app(settings)
    client = TestClient(app)
    
    # Verify Web data view
    res = client.get("/data?country=vn")
    assert res.status_code == 200
    
    # Verify Dashboard
    res_dash = client.get("/dashboard?country=vn")
    assert res_dash.status_code == 200
```

- [ ] **Step 2: Run full test suite**

Run: `.venv\Scripts\pytest -v`
Expected: All tests PASS (100% pass rate).
