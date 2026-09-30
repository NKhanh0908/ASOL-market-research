# Remove Internal AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely retire the internal Gemini AI evaluation subsystem, drop AI tables and foreign keys via an irreversible SQLite migration, and remove all AI UI/CLI hooks while preserving all core ranking, taxonomy, radar, and shortlist data.

**Architecture:** A database migration runs with foreign key enforcement to safely drop AI triggers and tables (`ai_run_evidence_seals`, `ai_run_evidence`, `ai_evaluation_runs`). The `src/casual_scout/ai/` package, AI web router, recommendation templates, and AI lifespan management are pruned from the codebase, freeing snapshots from foreign key constraints so that data retention can later proceed.

**Tech Stack:** Python 3.12+, FastAPI, SQLite, Pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-remove-internal-ai-design.md`

## Global Constraints

- Never remove or alter user-curated Shortlist bookmarks, tags, notes, or rank_at_bookmark.
- Never remove deterministic analysis modules: `analysis/delta.py`, `signals.py`, taxonomy classification, or Opportunity Radar.
- Active or running AI runs must block migration with a clear error; never silently corrupt or cancel active jobs.
- All AI schema retirement must run inside a single transaction with `PRAGMA foreign_keys = ON;` followed by `PRAGMA foreign_key_check;`.
- Preserve existing uncommitted AI working tree changes into a patch file before removal.
- All former AI web endpoints must return 404 cleanly; no 500 crashes or dangling references.

---

### Task 1: Preserve Uncommitted Changes and Preflight Check

**Files:**
- Create: `docs/superpowers/patches/2026-09-30-pre-retirement-ai.patch`
- Test: Verify patch creation

**Interfaces:**
- Produces: Git diff patch capturing unstaged work in `src/casual_scout/ai/` and `tests/test_ai_*`

- [x] **Step 1: Check git diff of uncommitted AI changes**

Run: `git diff -- src/casual_scout/ai/ tests/test_ai_*`
Expected: View current modifications in `gemini.py`, `output.py`, `settings.py`, and test files.

- [x] **Step 2: Save the patch to docs/superpowers/patches/**

```bash
mkdir -p docs/superpowers/patches
git diff -- src/casual_scout/ai/ tests/test_ai_* > docs/superpowers/patches/2026-09-30-pre-retirement-ai.patch
```

- [x] **Step 3: Verify the patch file exists and is non-empty**

Run: `test -s docs/superpowers/patches/2026-09-30-pre-retirement-ai.patch && echo "Patch verified"`
Expected: "Patch verified"

- [x] **Step 4: Commit the patch backup**

```bash
git add docs/superpowers/patches/2026-09-30-pre-retirement-ai.patch
git commit -m "docs(ai): preserve pre-retirement AI diff before removal"
```

---

### Task 2: Database Retirement Migration

**Files:**
- Create: `src/casual_scout/storage/migrations_ai_retirement.py`
- Modify: `src/casual_scout/storage/repository.py:60-90`
- Test: `tests/test_migration_ai_retirement.py`

**Interfaces:**
- Produces:
  - `migrate_ai_retirement(conn: sqlite3.Connection) -> None`
  - Integration with `Repository.initialize()`

- [x] **Step 1: Write failing test for retirement migration**

```python
# tests/test_migration_ai_retirement.py
import sqlite3
import pytest
from pathlib import Path
from casual_scout.storage.migrations_ai_retirement import migrate_ai_retirement, ActiveAIRunError

def test_migration_refuses_if_active_run(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE ai_evaluation_runs (id TEXT PRIMARY KEY, status TEXT);
        INSERT INTO ai_evaluation_runs VALUES ('run1', 'running');
    """)
    conn.commit()
    with pytest.raises(ActiveAIRunError):
        migrate_ai_retirement(conn)
    conn.close()

def test_migration_drops_tables_and_preserves_shortlist(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE shortlist (app_id TEXT PRIMARY KEY, title TEXT, notes TEXT);
        INSERT INTO shortlist VALUES ('app1', 'Cool Game', 'Must evaluate');

        CREATE TABLE ai_evaluation_runs (id TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE ai_run_evidence (run_id TEXT, evidence TEXT, FOREIGN KEY(run_id) REFERENCES ai_evaluation_runs(id));
        CREATE TABLE ai_run_evidence_seals (run_id TEXT, seal TEXT, FOREIGN KEY(run_id) REFERENCES ai_evaluation_runs(id));
        INSERT INTO ai_evaluation_runs VALUES ('run1', 'succeeded');
        INSERT INTO ai_run_evidence VALUES ('run1', 'ev1');
        INSERT INTO ai_run_evidence_seals VALUES ('run1', 'seal1');
    """)
    conn.commit()

    migrate_ai_retirement(conn)

    # Verify tables dropped
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "ai_evaluation_runs" not in tables
    assert "ai_run_evidence" not in tables
    assert "ai_run_evidence_seals" not in tables
    assert "shortlist" in tables

    # Verify shortlist intact
    row = conn.execute("SELECT title, notes FROM shortlist WHERE app_id = 'app1'").fetchone()
    assert row[0] == "Cool Game"
    assert row[1] == "Must evaluate"
    conn.close()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration_ai_retirement.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.storage.migrations_ai_retirement'`

- [x] **Step 3: Implement `migrate_ai_retirement`**

```python
# src/casual_scout/storage/migrations_ai_retirement.py
from __future__ import annotations

import sqlite3

class ActiveAIRunError(RuntimeError):
    pass

def migrate_ai_retirement(conn: sqlite3.Connection) -> None:
    # Check if AI tables even exist
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_%'"
        ).fetchall()
    }
    if not existing:
        return

    # Check for active runs if ai_evaluation_runs exists
    if "ai_evaluation_runs" in existing:
        active = conn.execute(
            "SELECT id, status FROM ai_evaluation_runs WHERE status IN ('queued', 'running')"
        ).fetchall()
        if active:
            runs_summary = ", ".join(f"{r[0]} ({r[1]})" for r in active)
            raise ActiveAIRunError(
                f"Cannot retire AI subsystem while active runs exist: {runs_summary}. Wait or resolve before upgrading."
            )

    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        # Drop triggers
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%ai_%'"
        ).fetchall()
        for trig in triggers:
            conn.execute(f"DROP TRIGGER IF EXISTS {trig[0]}")

        # Drop tables in reverse FK dependency order
        for tbl in ["ai_run_evidence_seals", "ai_run_evidence", "ai_evaluation_runs"]:
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")

        # Verify foreign keys
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key check failed after AI retirement migration: {fk_errors}")

        # Record migration
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations VALUES ('2026-09-30-remove-internal-ai', datetime('now'))"
        )
```

- [x] **Step 4: Connect migration to `Repository.initialize` and run test**

Modify `src/casual_scout/storage/repository.py`:
In `initialize()`, call `migrate_ai_retirement(connection)`.
Run: `pytest tests/test_migration_ai_retirement.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/casual_scout/storage/migrations_ai_retirement.py src/casual_scout/storage/repository.py tests/test_migration_ai_retirement.py
git commit -m "feat(storage): implement safe AI retirement database migration"
```

---

### Task 3: Remove AI Package and Web Endpoints

**Files:**
- Delete: `src/casual_scout/ai/`
- Delete: `src/casual_scout/web/ai.py`
- Delete: `src/casual_scout/web/templates/recommendations.html`
- Delete: `src/casual_scout/web/templates/recommendation_detail.html`
- Modify: `src/casual_scout/web/app.py`
- Modify: `src/casual_scout/web/templates/dashboard.html`
- Modify: `src/casual_scout/cli.py`
- Test: `tests/test_web_ai_removed.py`

**Interfaces:**
- Web app no longer registers `/recommendations` router.
- Accessing `/recommendations` or `/recommendations/{id}` returns HTTP 404.

- [x] **Step 1: Write test verifying AI endpoints return 404 and dashboard renders without AI elements**

```python
# tests/test_web_ai_removed.py
import pytest
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.web.app import create_app

def test_ai_routes_return_404(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    res = client.get("/recommendations")
    assert res.status_code == 404

    res2 = client.post("/recommendations/evaluate")
    assert res2.status_code == 404

def test_dashboard_does_not_contain_ai_button(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Tạo gợi ý AI" not in res.text
    assert "/recommendations" not in res.text
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_ai_removed.py -v`
Expected: FAIL (endpoints return 200 or AI buttons exist)

- [x] **Step 3: Remove AI files and prune web/CLI integrations**

1. Delete directory `src/casual_scout/ai/`.
2. Delete `src/casual_scout/web/ai.py`, `src/casual_scout/web/templates/recommendations.html`, `src/casual_scout/web/templates/recommendation_detail.html`.
3. In `src/casual_scout/web/app.py`:
   - Remove imports referencing `casual_scout.ai` or `casual_scout.web.ai`.
   - Remove `ai_engine`, `ai_store`, and `ai_worker` from lifespan startup/shutdown.
   - Remove `app.include_router(ai_router)`.
4. In `src/casual_scout/web/templates/dashboard.html`:
   - Remove modal and button for "Tạo gợi ý AI".
5. In `src/casual_scout/cli.py`:
   - Remove `GEMINI_API_KEY` and AI settings setup from `_run_serve`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_ai_removed.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add -u src/casual_scout/ tests/test_web_ai_removed.py
git commit -m "feat(web): remove AI router, templates, and lifespan management"
```

---

### Task 4: Clean up AI Tests and Verify Core Regression

**Files:**
- Delete: `tests/test_ai_*.py`
- Modify: `tests/test_cli_serve.py` (if referencing AI)
- Test: Full test suite `pytest`

**Interfaces:**
- All tests pass; zero imports of deleted modules.

- [x] **Step 1: Remove obsolete AI test files**

Delete:
- `tests/test_ai_gemini.py`
- `tests/test_ai_output.py`
- `tests/test_ai_storage.py`
- `tests/test_ai_engine.py`
- `tests/test_ai_service.py`
- `tests/test_ai_worker.py`
- `tests/test_ai_evidence.py`
- Any remaining `tests/test_ai_*.py` files.

- [x] **Step 2: Run full regression test suite**

Run: `pytest tests/test_analysis_*.py tests/test_storage_*.py tests/test_web_*.py -v`
Expected: All core tests pass without failure.

- [x] **Step 3: Verify git status and commit**

```bash
git add -u tests/
git commit -m "test: prune obsolete internal AI test suite"
```
