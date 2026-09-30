# MCP Market Brief Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, read-only HTTP Model Context Protocol (MCP) server running on `127.0.0.1:8003/mcp` that exposes Top Free Casual daily market briefs, 7-day game rank history, and coverage metrics across 9 ASEAN and US markets.

**Architecture:** A lightweight ASGI service using the official `mcp` Python SDK running independently from the FastAPI web dashboard. It opens a read-only SQLite transaction to extract complete snapshots across $T-6 \dots T$, feeds them to pure calculation functions for Top 10 and strong movers ($|delta_{1d}| \ge 20$ or $|delta_{3d}| \ge 30$), and formats responses according to strict Pydantic v1 contracts without altering database state or invoking web crawlers.

**Tech Stack:** Python 3.12+, `mcp>=1.2.0`, `pydantic>=2.0`, `sqlite3` (URI read-only mode), `uvicorn>=0.30`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-30-mcp-market-brief-design.md`

## Global Constraints

- Standalone HTTP process on loopback `127.0.0.1:8003`, endpoint `/mcp`. Never bind to LAN or `0.0.0.0`.
- Read-only operations (`readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`, `openWorldHint=false`). Never mutate SQLite tables, initialize schemas, or trigger background crawlers.
- Exactly 9 allowed market countries: `vn`, `th`, `id`, `my`, `ph`, `sg`, `la`, `kh`, `us`. Case-insensitive input normalized to lowercase.
- Chart scope: Apple iOS `topfreeapplications` (genre `7003`) and Google Play Android `top-free` (genre `GAME_CASUAL`), depth 100.
- Selection rules: Top 10 games always included; games 11–100 included if and only if $|delta_{1d}| \ge 20$ or $|delta_{3d}| \ge 30$.
- Rank history window: Exactly 7 consecutive calendar days $T-6 \dots T$ in UTC. Target date $T$ must be within the last 7 UTC calendar days (including today).
- All tool execution must happen inside a single SQLite read transaction to guarantee cross-platform consistency.

---

### Task 1: Contracts and Dependency Setup

**Files:**
- Modify: `pyproject.toml:8-18`
- Create: `src/casual_scout/mcp/contracts.py`
- Test: `tests/test_mcp_contracts.py`

**Interfaces:**
- Produces:
  - `MarketBriefRequest(country: str, date: str | None = None)`
  - `GameHistoryRequest(country: str, platform: Literal['ios', 'android'], app_id: str, date: str | None = None)`
  - `CoverageRequest(country: str)`
  - `DailyMarketBriefResponse`, `GameRankHistoryResponse`, `CoverageResponse`

- [ ] **Step 1: Write the failing test for MCP input/output contracts**

```python
# tests/test_mcp_contracts.py
import pytest
from pydantic import ValidationError
from casual_scout.mcp.contracts import (
    MarketBriefRequest,
    GameHistoryRequest,
    CoverageRequest,
    StrongMove,
    RankHistoryPoint,
)

def test_market_brief_request_validates_country():
    req = MarketBriefRequest(country="VN")
    assert req.country == "vn"

    with pytest.raises(ValidationError):
        MarketBriefRequest(country="invalid_code")

def test_market_brief_request_validates_date():
    req = MarketBriefRequest(country="vn", date="2026-09-30")
    assert req.date == "2026-09-30"

    with pytest.raises(ValidationError):
        MarketBriefRequest(country="vn", date="30-09-2026")

def test_game_history_request_validates_platform():
    req = GameHistoryRequest(country="us", platform="ios", app_id="123456")
    assert req.platform == "ios"

    with pytest.raises(ValidationError):
        GameHistoryRequest(country="us", platform="windows", app_id="123456")

def test_strong_move_contract():
    move = StrongMove(window_days=1, delta=25, direction="up", threshold=20)
    assert move.window_days == 1
    assert move.delta == 25
    assert move.direction == "up"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_contracts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.mcp'`

- [ ] **Step 3: Add `mcp` dependency to `pyproject.toml` and implement contracts**

Update `pyproject.toml` dependencies: add `"mcp>=1.2.0"`.

```python
# src/casual_scout/mcp/contracts.py
from __future__ import annotations

import re
from datetime import UTC, datetime, date as Date
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

ALLOWED_COUNTRIES = {"vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"}

def normalize_country(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in ALLOWED_COUNTRIES:
        raise ValueError(f"Country must be one of {sorted(ALLOWED_COUNTRIES)}, got '{value}'")
    return cleaned

def validate_iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = Date.fromisoformat(value)
        return parsed.isoformat()
    except ValueError:
        raise ValueError(f"Date must be in YYYY-MM-DD format, got '{value}'")

class MarketBriefRequest(BaseModel):
    country: str
    date: str | None = None

    @field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        return normalize_country(v)

    @field_validator("date")
    @classmethod
    def validate_date_field(cls, v: str | None) -> str | None:
        return validate_iso_date(v)

class GameHistoryRequest(BaseModel):
    country: str
    platform: Literal["ios", "android"]
    app_id: str
    date: str | None = None

    @field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        return normalize_country(v)

    @field_validator("app_id")
    @classmethod
    def validate_app_id_field(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("app_id cannot be empty")
        return s

    @field_validator("date")
    @classmethod
    def validate_date_field(cls, v: str | None) -> str | None:
        return validate_iso_date(v)

class CoverageRequest(BaseModel):
    country: str

    @field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        return normalize_country(v)

class StrongMove(BaseModel):
    window_days: int
    delta: int
    direction: Literal["up", "down"]
    threshold: int

class RankHistoryPoint(BaseModel):
    date: str
    rank: int | None
    status: Literal["observed", "not_in_observed_chart", "no_complete_snapshot", "incompatible_chart", "expired"]

class BriefGameEntry(BaseModel):
    app_id: str
    name: str
    store_url: str | None
    rank: int
    rank_1d_ago: int | None
    rank_3d_ago: int | None
    delta_1d: int | None
    delta_3d: int | None
    movement_1d: Literal["up", "down", "unchanged", "new_entry", "unknown"]
    comparison_1d: Literal["available", "no_baseline", "partial", "unavailable"]
    comparison_3d: Literal["available", "no_baseline", "partial", "unavailable"]
    strong_moves: list[StrongMove]
    rank_history: list[RankHistoryPoint]
    developer: str | None = None
    genre: str | None = None
    metadata_fetched_at: str | None = None

class PlatformBrief(BaseModel):
    data_status: Literal["available", "partial", "unavailable"]
    comparison_status: Literal["available", "partial", "unavailable"]
    warnings: list[dict[str, str]] = Field(default_factory=list)
    snapshots: dict[str, Any] = Field(default_factory=dict)
    top_10: list[BriefGameEntry] = Field(default_factory=list)
    strong_movers_outside_top_10: list[BriefGameEntry] = Field(default_factory=list)
    total_top_10: int = 0
    total_strong_movers: int = 0

class DailyMarketBriefResponse(BaseModel):
    schema_version: str = "market-brief.v1"
    rules_version: str = "market-brief-selection.v1"
    generated_at: str
    country: str
    date: str
    date_timezone: str = "UTC"
    feed_type: str = "top-free-casual"
    history_days: int = 7
    platforms: dict[str, PlatformBrief]

class GameRankHistoryResponse(BaseModel):
    schema_version: str = "game-history.v1"
    country: str
    platform: Literal["ios", "android"]
    app_id: str
    date: str
    history_days: int = 7
    game_status: Literal["observed", "not_observed_in_window"]
    name: str | None
    rank_history: list[RankHistoryPoint]

class PlatformCoverage(BaseModel):
    platform: Literal["ios", "android"]
    days_complete: int
    latest_complete_date: str | None
    days: dict[str, dict[str, Any]]

class CoverageResponse(BaseModel):
    schema_version: str = "coverage.v1"
    country: str
    history_days: int = 7
    platforms: dict[str, PlatformCoverage]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/casual_scout/mcp/contracts.py tests/test_mcp_contracts.py
git commit -m "feat(mcp): define data contracts and validation for market brief tools"
```

---

### Task 2: Market Brief Snapshot Reader

**Files:**
- Create: `src/casual_scout/market_brief/reader.py`
- Test: `tests/test_market_brief_reader.py`

**Interfaces:**
- Consumes: Database schema from `casual_scout/storage/schema.sql`
- Produces:
  - `MarketBriefReader(db_path: Path)`
  - `reader.get_window_snapshots(country: str, platform: str, target_date: str) -> dict[str, SnapshotData]`

- [ ] **Step 1: Write the failing test for MarketBriefReader**

```python
# tests/test_market_brief_reader.py
import sqlite3
import pytest
from pathlib import Path
from casual_scout.market_brief.reader import MarketBriefReader

@pytest.fixture
def sample_db(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE markets (country TEXT PRIMARY KEY, name TEXT);
        INSERT INTO markets VALUES ('vn', 'Vietnam');
        CREATE TABLE charts (
            id TEXT PRIMARY KEY, provider TEXT, platform TEXT, country TEXT,
            collection TEXT, genre TEXT, depth INTEGER, version INTEGER
        );
        INSERT INTO charts VALUES ('c1', 'apple', 'ios', 'vn', 'topfreeapplications', '7003', 100, 1);
        CREATE TABLE snapshots (
            id TEXT PRIMARY KEY, chart_id TEXT, observed_at TEXT, quality TEXT, raw_hash TEXT
        );
        INSERT INTO snapshots VALUES ('s1', 'c1', '2026-09-30T07:00:00Z', 'complete', 'hash1');
        CREATE TABLE snapshot_entries (
            snapshot_id TEXT, app_id TEXT, rank INTEGER, name TEXT, store_url TEXT,
            PRIMARY KEY(snapshot_id, app_id)
        );
        INSERT INTO snapshot_entries VALUES ('s1', 'app1', 1, 'Puzzle Game', 'https://example.com/app1');
        CREATE TABLE canonical_snapshots (
            chart_id TEXT, observed_date TEXT, snapshot_id TEXT,
            PRIMARY KEY(chart_id, observed_date)
        );
        INSERT INTO canonical_snapshots VALUES ('c1', '2026-09-30', 's1');
    """)
    conn.commit()
    conn.close()
    return db_file

def test_reader_finds_canonical_snapshot(sample_db):
    reader = MarketBriefReader(sample_db)
    window = reader.get_window_snapshots("vn", "ios", "2026-09-30")
    assert "2026-09-30" in window
    snap = window["2026-09-30"]
    assert snap.snapshot_id == "s1"
    assert len(snap.entries) == 1
    assert snap.entries[0]["app_id"] == "app1"
    assert snap.entries[0]["rank"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_brief_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.market_brief'`

- [ ] **Step 3: Implement `MarketBriefReader`**

```python
# src/casual_scout/market_brief/reader.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, date as Date, timedelta
from pathlib import Path
from typing import Any

@dataclass
class SnapshotData:
    snapshot_id: str
    observed_at: str
    observed_date: str
    quality: str
    raw_hash: str
    entries: list[dict[str, Any]]

class MarketBriefReader:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()

    def _get_connection(self) -> sqlite3.Connection:
        # SQLite read-only URI connection
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get_window_snapshots(
        self, country: str, platform: str, target_date: str
    ) -> dict[str, SnapshotData]:
        end_date = Date.fromisoformat(target_date)
        date_strings = [(end_date - timedelta(days=i)).isoformat() for i in range(7)]

        provider = "apple" if platform == "ios" else "google"
        collection = "topfreeapplications" if platform == "ios" else "top-free"
        genre = "7003" if platform == "ios" else "GAME_CASUAL"

        result: dict[str, SnapshotData] = {}
        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Find chart
                chart_row = conn.execute(
                    """
                    SELECT id FROM charts
                    WHERE provider = ? AND platform = ? AND country = ?
                      AND collection = ? AND genre = ? AND depth = 100
                    LIMIT 1
                    """,
                    (provider, platform, country, collection, genre),
                ).fetchone()

                if not chart_row:
                    return result
                chart_id = chart_row["id"]

                for d_str in date_strings:
                    # 1. Prefer canonical
                    snap_row = conn.execute(
                        """
                        SELECT s.id, s.observed_at, s.quality, s.raw_hash
                        FROM canonical_snapshots c
                        JOIN snapshots s ON s.id = c.snapshot_id
                        WHERE c.chart_id = ? AND c.observed_date = ? AND s.quality = 'complete'
                        LIMIT 1
                        """,
                        (chart_id, d_str),
                    ).fetchone()

                    # 2. Fallback to latest complete in day
                    if not snap_row:
                        start_utc = f"{d_str}T00:00:00Z"
                        end_utc = f"{d_str}T23:59:59Z"
                        snap_row = conn.execute(
                            """
                            SELECT id, observed_at, quality, raw_hash
                            FROM snapshots
                            WHERE chart_id = ? AND observed_at >= ? AND observed_at <= ? AND quality = 'complete'
                            ORDER BY observed_at DESC, id ASC
                            LIMIT 1
                            """,
                            (chart_id, start_utc, end_utc),
                        ).fetchone()

                    if snap_row:
                        snap_id = snap_row["id"]
                        entries_cursor = conn.execute(
                            """
                            SELECT app_id, rank, name, store_url
                            FROM snapshot_entries
                            WHERE snapshot_id = ?
                            ORDER BY rank ASC
                            """,
                            (snap_id,),
                        )
                        entries = [dict(r) for r in entries_cursor.fetchall()]
                        result[d_str] = SnapshotData(
                            snapshot_id=snap_id,
                            observed_at=snap_row["observed_at"],
                            observed_date=d_str,
                            quality=snap_row["quality"],
                            raw_hash=snap_row["raw_hash"],
                            entries=entries,
                        )
            finally:
                conn.execute("ROLLBACK")
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_brief_reader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/casual_scout/market_brief/reader.py tests/test_market_brief_reader.py
git commit -m "feat(mcp): implement read-only snapshot window query in reader"
```

---

### Task 3: Pure Market Brief Calculation Engine

**Files:**
- Create: `src/casual_scout/market_brief/service.py`
- Test: `tests/test_market_brief_service.py`

**Interfaces:**
- Consumes: `MarketBriefReader`, `contracts.py`
- Produces:
  - `compute_platform_brief(country: str, platform: str, target_date: str, snapshots: dict[str, SnapshotData]) -> PlatformBrief`
  - `compute_game_history(app_id: str, target_date: str, snapshots: dict[str, SnapshotData]) -> list[RankHistoryPoint]`

- [ ] **Step 1: Write failing tests for calculation logic and threshold boundaries**

```python
# tests/test_market_brief_service.py
from casual_scout.market_brief.reader import SnapshotData
from casual_scout.market_brief.service import compute_platform_brief

def test_top_10_always_included_regardless_of_movement():
    entries_t = [{"app_id": f"app_{i}", "rank": i, "name": f"Game {i}", "store_url": None} for i in range(1, 11)]
    snap_t = SnapshotData("s_t", "2026-09-30T00:00:00Z", "2026-09-30", "complete", "h_t", entries_t)
    snapshots = {"2026-09-30": snap_t}

    brief = compute_platform_brief("vn", "ios", "2026-09-30", snapshots)
    assert len(brief.top_10) == 10
    assert brief.total_top_10 == 10
    assert len(brief.strong_movers_outside_top_10) == 0

def test_strong_movers_threshold_boundary():
    # app_up20 moved from rank 40 (T-1) to rank 20 (T) -> delta +20 (qualifies)
    # app_up19 moved from rank 39 (T-1) to rank 20 (T) -> delta +19 (does not qualify)
    # app_3d30 moved from rank 60 (T-3) to rank 30 (T) -> delta +30 (qualifies)
    entries_t = [
        {"app_id": "app_up20", "rank": 20, "name": "Mover 20", "store_url": None},
        {"app_id": "app_up19", "rank": 21, "name": "Mover 19", "store_url": None},
        {"app_id": "app_3d30", "rank": 30, "name": "Mover 3d30", "store_url": None},
    ]
    entries_t1 = [
        {"app_id": "app_up20", "rank": 40, "name": "Mover 20", "store_url": None},
        {"app_id": "app_up19", "rank": 40, "name": "Mover 19", "store_url": None},
    ]
    entries_t3 = [
        {"app_id": "app_3d30", "rank": 60, "name": "Mover 3d30", "store_url": None},
    ]
    snapshots = {
        "2026-09-30": SnapshotData("s0", "2026-09-30T00:00:00Z", "2026-09-30", "complete", "h0", entries_t),
        "2026-09-29": SnapshotData("s1", "2026-09-29T00:00:00Z", "2026-09-29", "complete", "h1", entries_t1),
        "2026-09-27": SnapshotData("s3", "2026-09-27T00:00:00Z", "2026-09-27", "complete", "h3", entries_t3),
    }
    brief = compute_platform_brief("vn", "ios", "2026-09-30", snapshots)
    movers = {m.app_id for m in brief.strong_movers_outside_top_10}
    assert "app_up20" in movers
    assert "app_3d30" in movers
    assert "app_up19" not in movers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_brief_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.market_brief.service'`

- [ ] **Step 3: Implement calculation service**

```python
# src/casual_scout/market_brief/service.py
from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any
from casual_scout.market_brief.reader import SnapshotData
from casual_scout.mcp.contracts import (
    BriefGameEntry,
    PlatformBrief,
    RankHistoryPoint,
    StrongMove,
)

def compute_game_history(
    app_id: str, target_date: str, snapshots: dict[str, SnapshotData]
) -> list[RankHistoryPoint]:
    end_date = Date.fromisoformat(target_date)
    date_strings = [(end_date - timedelta(days=i)).isoformat() for i in range(7)]
    history: list[RankHistoryPoint] = []

    for d_str in reversed(date_strings):
        snap = snapshots.get(d_str)
        if not snap:
            history.append(RankHistoryPoint(date=d_str, rank=None, status="no_complete_snapshot"))
            continue
        matched = next((e for e in snap.entries if e["app_id"] == app_id), None)
        if matched:
            history.append(RankHistoryPoint(date=d_str, rank=matched["rank"], status="observed"))
        else:
            history.append(RankHistoryPoint(date=d_str, rank=None, status="not_in_observed_chart"))
    return history

def compute_platform_brief(
    country: str, platform: str, target_date: str, snapshots: dict[str, SnapshotData]
) -> PlatformBrief:
    target_snap = snapshots.get(target_date)
    if not target_snap:
        return PlatformBrief(
            data_status="unavailable",
            comparison_status="unavailable",
            warnings=[{"code": "MISSING_TARGET_DATE", "message": f"No complete snapshot for {target_date}"}],
        )

    t_minus_1_str = (Date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    t_minus_3_str = (Date.fromisoformat(target_date) - timedelta(days=3)).isoformat()
    snap_t1 = snapshots.get(t_minus_1_str)
    snap_t3 = snapshots.get(t_minus_3_str)

    rank_t1_map = {e["app_id"]: e["rank"] for e in snap_t1.entries} if snap_t1 else {}
    rank_t3_map = {e["app_id"]: e["rank"] for e in snap_t3.entries} if snap_t3 else {}

    top_10_list: list[BriefGameEntry] = []
    movers_candidates: list[tuple[float, BriefGameEntry]] = []

    for entry in target_snap.entries:
        app_id = entry["app_id"]
        cur_rank = entry["rank"]
        r1 = rank_t1_map.get(app_id)
        r3 = rank_t3_map.get(app_id)

        delta_1d = (r1 - cur_rank) if r1 is not None else None
        delta_3d = (r3 - cur_rank) if r3 is not None else None

        # Movement 1d
        if r1 is None:
            movement_1d = "new_entry" if snap_t1 is not None else "unknown"
        elif delta_1d > 0:
            movement_1d = "up"
        elif delta_1d < 0:
            movement_1d = "down"
        else:
            movement_1d = "unchanged"

        comp_1d = "available" if r1 is not None else ("no_baseline" if snap_t1 else "unavailable")
        comp_3d = "available" if r3 is not None else ("no_baseline" if snap_t3 else "unavailable")

        strong_moves: list[StrongMove] = []
        ratio_1d = 0.0
        ratio_3d = 0.0

        if delta_1d is not None and abs(delta_1d) >= 20:
            strong_moves.append(
                StrongMove(
                    window_days=1,
                    delta=delta_1d,
                    direction="up" if delta_1d > 0 else "down",
                    threshold=20,
                )
            )
            ratio_1d = abs(delta_1d) / 20.0

        if delta_3d is not None and abs(delta_3d) >= 30:
            strong_moves.append(
                StrongMove(
                    window_days=3,
                    delta=delta_3d,
                    direction="up" if delta_3d > 0 else "down",
                    threshold=30,
                )
            )
            ratio_3d = abs(delta_3d) / 30.0

        history = compute_game_history(app_id, target_date, snapshots)

        brief_entry = BriefGameEntry(
            app_id=app_id,
            name=entry["name"],
            store_url=entry.get("store_url"),
            rank=cur_rank,
            rank_1d_ago=r1,
            rank_3d_ago=r3,
            delta_1d=delta_1d,
            delta_3d=delta_3d,
            movement_1d=movement_1d,
            comparison_1d=comp_1d,
            comparison_3d=comp_3d,
            strong_moves=strong_moves,
            rank_history=history,
        )

        if cur_rank <= 10:
            top_10_list.append(brief_entry)
        elif strong_moves:
            max_ratio = max(ratio_1d, ratio_3d)
            movers_candidates.append((max_ratio, brief_entry))

    # Sort top 10 by current rank
    top_10_list.sort(key=lambda g: g.rank)

    # Sort movers by max ratio descending, then current rank ascending, then app_id
    movers_candidates.sort(key=lambda item: (-item[0], item[1].rank, item[1].app_id))
    movers_list = [item[1] for item in movers_candidates]

    snapshots_summary = {
        d: {
            "snapshot_id": s.snapshot_id,
            "observed_at": s.observed_at,
            "quality": s.quality,
            "raw_hash": s.raw_hash,
        }
        for d, s in snapshots.items()
    }

    comp_status = "available" if snap_t1 and snap_t3 else ("partial" if snap_t1 or snap_t3 else "unavailable")

    return PlatformBrief(
        data_status="available",
        comparison_status=comp_status,
        snapshots=snapshots_summary,
        top_10=top_10_list,
        strong_movers_outside_top_10=movers_list,
        total_top_10=len(top_10_list),
        total_strong_movers=len(movers_list),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_brief_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/casual_scout/market_brief/service.py tests/test_market_brief_service.py
git commit -m "feat(mcp): implement market brief sorting and threshold evaluation service"
```

---

### Task 4: MCP Server and Tool Registration

**Files:**
- Create: `src/casual_scout/mcp/server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `MarketBriefReader`, `service.py`, `contracts.py`
- Produces:
  - `create_mcp_app(db_path: Path) -> mcp.server.fastmcp.FastMCP` or ASGI app
  - Registered tools: `get_daily_market_brief`, `get_game_rank_history`, `get_coverage`

- [ ] **Step 1: Write integration test calling MCP tools via test client**

```python
# tests/test_mcp_server.py
import pytest
from pathlib import Path
from casual_scout.mcp.server import create_mcp_server

def test_mcp_server_lists_tools(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    server = create_mcp_server(db_file)
    tool_names = [t.name for t in server.list_tools()]
    assert "get_daily_market_brief" in tool_names
    assert "get_game_rank_history" in tool_names
    assert "get_coverage" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.mcp.server'`

- [ ] **Step 3: Implement MCP server with tools**

```python
# src/casual_scout/mcp/server.py
from __future__ import annotations

from datetime import UTC, datetime, date as Date, timedelta
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from casual_scout.market_brief.reader import MarketBriefReader
from casual_scout.market_brief.service import compute_platform_brief, compute_game_history
from casual_scout.mcp.contracts import (
    DailyMarketBriefResponse,
    GameRankHistoryResponse,
    CoverageResponse,
    PlatformCoverage,
    normalize_country,
    validate_iso_date,
)

def create_mcp_server(db_path: Path) -> FastMCP:
    mcp = FastMCP("Casual Scout Market Brief")
    reader = MarketBriefReader(db_path)

    @mcp.tool(
        name="get_daily_market_brief",
        description="Fetch Top Free Casual daily market brief for iOS and Android across 9 allowed markets."
    )
    def get_daily_market_brief(country: str, date: str | None = None) -> str:
        norm_country = normalize_country(country)
        target_date = validate_iso_date(date) or datetime.now(UTC).strftime("%Y-%m-%d")

        ios_snaps = reader.get_window_snapshots(norm_country, "ios", target_date)
        android_snaps = reader.get_window_snapshots(norm_country, "android", target_date)

        ios_brief = compute_platform_brief(norm_country, "ios", target_date, ios_snaps)
        android_brief = compute_platform_brief(norm_country, "android", target_date, android_snaps)

        response = DailyMarketBriefResponse(
            generated_at=datetime.now(UTC).isoformat(),
            country=norm_country,
            date=target_date,
            platforms={"ios": ios_brief, "android": android_brief},
        )
        return response.model_dump_json(indent=2)

    @mcp.tool(
        name="get_game_rank_history",
        description="Fetch 7-day rank history for a single game in a target market."
    )
    def get_game_rank_history(country: str, platform: str, app_id: str, date: str | None = None) -> str:
        norm_country = normalize_country(country)
        plat = "ios" if platform.lower() == "ios" else "android"
        target_date = validate_iso_date(date) or datetime.now(UTC).strftime("%Y-%m-%d")

        snaps = reader.get_window_snapshots(norm_country, plat, target_date)
        history = compute_game_history(app_id, target_date, snaps)
        observed = any(p.rank is not None for p in history)

        response = GameRankHistoryResponse(
            country=norm_country,
            platform=plat,
            app_id=app_id,
            date=target_date,
            game_status="observed" if observed else "not_observed_in_window",
            name=None,
            rank_history=history,
        )
        return response.model_dump_json(indent=2)

    @mcp.tool(
        name="get_coverage",
        description="Inspect complete snapshot coverage for the last 7 UTC days."
    )
    def get_coverage(country: str) -> str:
        norm_country = normalize_country(country)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        ios_snaps = reader.get_window_snapshots(norm_country, "ios", today)
        android_snaps = reader.get_window_snapshots(norm_country, "android", today)

        response = CoverageResponse(
            country=norm_country,
            platforms={
                "ios": PlatformCoverage(
                    platform="ios",
                    days_complete=len(ios_snaps),
                    latest_complete_date=max(ios_snaps.keys()) if ios_snaps else None,
                    days={d: {"quality": s.quality, "entries": len(s.entries)} for d, s in ios_snaps.items()},
                ),
                "android": PlatformCoverage(
                    platform="android",
                    days_complete=len(android_snaps),
                    latest_complete_date=max(android_snaps.keys()) if android_snaps else None,
                    days={d: {"quality": s.quality, "entries": len(s.entries)} for d, s in android_snaps.items()},
                ),
            },
        )
        return response.model_dump_json(indent=2)

    return mcp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/casual_scout/mcp/server.py tests/test_mcp_server.py
git commit -m "feat(mcp): implement FastMCP server with 3 market brief tools"
```

---

### Task 5: CLI Command `casual_scout mcp-serve`

**Files:**
- Modify: `src/casual_scout/cli.py`
- Test: `tests/test_cli_mcp.py`

**Interfaces:**
- CLI command: `casual_scout mcp-serve --data-dir <path> --port 8003`

- [ ] **Step 1: Write test for `mcp-serve` argument parsing**

```python
# tests/test_cli_mcp.py
import pytest
from casual_scout.cli import main

def test_mcp_serve_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["mcp-serve", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--port" in captured.out
    assert "--data-dir" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_mcp.py -v`
Expected: FAIL with `invalid choice: 'mcp-serve'`

- [ ] **Step 3: Add `mcp-serve` subparser and runner to `cli.py`**

In `src/casual_scout/cli.py`:
Add subparser `mcp-serve`:
```python
mcp_parser = subparsers.add_parser("mcp-serve", help="Run standalone HTTP MCP server")
mcp_parser.add_argument("--data-dir", type=Path, default=Path("data"))
mcp_parser.add_argument("--port", type=int, default=8003)
mcp_parser.add_argument("--host", type=str, default="127.0.0.1")
```
Implement dispatch handler `_run_mcp_serve(args)`:
```python
def _run_mcp_serve(args: argparse.Namespace) -> int:
    from casual_scout.mcp.server import create_mcp_server
    db_file = Path(args.data_dir) / "casual-scout.sqlite3"
    if not db_file.is_file():
        sys.stderr.write(f"Database not found: {db_file}\n")
        return 1
    server = create_mcp_server(db_file)
    server.run(transport="sse", host=args.host, port=args.port)
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_mcp.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/casual_scout/cli.py tests/test_cli_mcp.py
git commit -m "feat(cli): add mcp-serve command to launch loopback MCP server"
```
