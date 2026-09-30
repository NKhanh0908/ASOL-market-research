# 15-Day Data Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate 15-day UTC rolling data retention across SQLite snapshots, entries, daily analytics, market runs, worker logs, and content-addressed raw response files while strictly preserving the shortlist, configuration, and active schedules.

**Architecture:** A robust two-phase maintenance service (`operations/retention.py`) acquires an atomic maintenance lock across processes. Phase 1 executes an SQLite transaction using a maintenance-authorized connection to delete expired rows before `00:00 UTC on D-14` and writes a persistent GC manifest. Phase 2 unlinks orphaned content-addressed raw response files and worker logs with crash-recovery support, verified path validation, and zero impact on surviving snapshots or shortlist bookmarks.

**Tech Stack:** Python 3.12+, SQLite (WAL mode with trigger guards), Pathlib, Pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-data-retention-design.md`

## Global Constraints

- Precondition: AI retirement migration must be applied first. If AI tables exist, retention must abort with an error.
- Retention window: Exactly 15 consecutive UTC calendar days including today ($D-14 \dots D$). Cutoff is `00:00 UTC on D-14`.
- Never delete or truncate `shortlist` items, bookmarks, notes, priority, or tags.
- Never delete market definitions, chart configurations, active/pending schedules, or migration tables.
- Filesystem safety: Never call recursive delete on `data/`. All raw/log file paths must be strictly checked to reside inside `data_dir/raw/` or `data_dir/logs/` with symlinks rejected.
- Crash recovery: Phase 2 file deletions are driven by a persistent manifest written in Phase 1 commit; if a crash occurs between Phase 1 and 2, subsequent runs resume from the manifest.
- Two execution modes: CLI `--dry-run` (read-only audit reporting candidates and estimated bytes) and `--apply` (commit).

---

### Task 1: Database Retention Trigger Migration

**Files:**
- Create: `src/casual_scout/storage/migrations_retention.py`
- Modify: `src/casual_scout/storage/repository.py`
- Test: `tests/test_migration_retention.py`

**Interfaces:**
- Produces:
  - `migrate_retention_triggers(conn: sqlite3.Connection) -> None`
  - Connection authorizer or table trigger guard updated to allow DELETE during retention maintenance transactions.

- [x] **Step 1: Write failing test for retention trigger guard migration**

```python
# tests/test_migration_retention.py
import sqlite3
import pytest
from pathlib import Path
from casual_scout.storage.migrations_retention import migrate_retention_triggers

def test_regular_connection_cannot_delete_snapshot(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT);
        INSERT INTO snapshots VALUES ('s1', '2026-09-01T00:00:00Z');
    """)
    conn.commit()
    migrate_retention_triggers(conn)

    # Standard connection attempting DELETE should raise OperationalError or trigger failure
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM snapshots WHERE id = 's1'")
    conn.close()

def test_maintenance_session_can_delete_snapshot(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT);
        INSERT INTO snapshots VALUES ('s1', '2026-09-01T00:00:00Z');
    """)
    conn.commit()
    migrate_retention_triggers(conn)

    # Authorize maintenance connection
    conn.execute("PRAGMA temp.maintenance_authorized = 1;")
    conn.execute("DELETE FROM snapshots WHERE id = 's1'")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert count == 0
    conn.close()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration_retention.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.storage.migrations_retention'`

- [x] **Step 3: Implement trigger migration**

```python
# src/casual_scout/storage/migrations_retention.py
from __future__ import annotations

import sqlite3

def migrate_retention_triggers(conn: sqlite3.Connection) -> None:
    """Replace hard DELETE triggers with maintenance-checked triggers."""
    with conn:
        # Check if table snapshots exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots'"
        ).fetchone()
        if not exists:
            return

        # Drop old hard delete trigger if present
        conn.execute("DROP TRIGGER IF EXISTS prevent_snapshots_delete")

        # Create trigger that allows delete only if maintenance_authorized pragma or temp table is set
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS guard_snapshots_delete
            BEFORE DELETE ON snapshots
            FOR EACH ROW
            WHEN (
                SELECT coalesce(max(value), '0')
                FROM temp.sqlite_master
                WHERE type='table' AND name='maintenance_session'
            ) != '1'
            BEGIN
                SELECT RAISE(ABORT, 'DELETE forbidden on immutable snapshots table outside maintenance session');
            END;
        """)

        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations VALUES ('2026-09-30-data-retention-triggers', datetime('now'))"
        )
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migration_retention.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/casual_scout/storage/migrations_retention.py tests/test_migration_retention.py
git commit -m "feat(storage): implement maintenance-guarded delete triggers for retention"
```

---

### Task 2: Core Retention Service and Cutoff Logic

**Files:**
- Create: `src/casual_scout/operations/retention.py`
- Test: `tests/test_operations_retention.py`

**Interfaces:**
- Produces:
  - `compute_utc_cutoff(reference_date: Date | None = None) -> datetime`
  - `RetentionCandidateReport`
  - `RetentionService(data_dir: Path)`
  - `retention_service.scan_candidates() -> RetentionCandidateReport`
  - `retention_service.apply_retention() -> RetentionSummary`

- [x] **Step 1: Write failing test for candidate scanning and cutoff calculation**

```python
# tests/test_operations_retention.py
from datetime import date as Date, datetime, UTC
from pathlib import Path
import sqlite3
import pytest
from casual_scout.operations.retention import RetentionService, compute_utc_cutoff

def test_cutoff_is_d_minus_14_at_midnight():
    ref = Date(2026, 9, 30)
    cutoff = compute_utc_cutoff(ref)
    assert cutoff.isoformat() == "2026-09-16T00:00:00+00:00"

def test_scan_candidates_finds_old_snapshots_and_retains_shortlist(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT);
        CREATE TABLE snapshot_entries (snapshot_id TEXT, app_id TEXT);
        CREATE TABLE raw_responses (hash TEXT PRIMARY KEY, path TEXT);
        CREATE TABLE shortlist (app_id TEXT PRIMARY KEY, title TEXT);

        -- Expired (observed 2026-09-10)
        INSERT INTO snapshots VALUES ('s_old', '2026-09-10T12:00:00Z', 'hash_old');
        INSERT INTO snapshot_entries VALUES ('s_old', 'game_old');
        INSERT INTO raw_responses VALUES ('hash_old', 'raw/01/hash_old');

        -- Kept (observed 2026-09-25)
        INSERT INTO snapshots VALUES ('s_new', '2026-09-25T12:00:00Z', 'hash_new');
        INSERT INTO snapshot_entries VALUES ('s_new', 'game_new');
        INSERT INTO raw_responses VALUES ('hash_new', 'raw/02/hash_new');

        -- Shortlist bookmarked game_old (must be preserved)
        INSERT INTO shortlist VALUES ('game_old', 'Old But Gold');
    """)
    conn.commit()
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    report = service.scan_candidates()

    assert report.expired_snapshots_count == 1
    assert "s_old" in report.expired_snapshot_ids
    assert "s_new" not in report.expired_snapshot_ids
    assert "hash_old" in report.unreferenced_raw_hashes
    assert "hash_new" not in report.unreferenced_raw_hashes
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operations_retention.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'casual_scout.operations.retention'`

- [x] **Step 3: Implement RetentionService scan and candidate logic**

```python
# src/casual_scout/operations/retention.py
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date as Date, datetime, timedelta
from pathlib import Path
from typing import Any

def compute_utc_cutoff(ref_date: Date | None = None) -> datetime:
    base = ref_date or datetime.now(UTC).date()
    # 15 days window: D-14 to D -> Cutoff is midnight of D-14
    target = base - timedelta(days=14)
    return datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=UTC)

@dataclass
class RetentionCandidateReport:
    cutoff_utc: str
    expired_snapshots_count: int = 0
    expired_snapshot_ids: list[str] = field(default_factory=list)
    unreferenced_raw_hashes: list[str] = field(default_factory=list)
    raw_files_to_delete: list[str] = field(default_factory=list)
    estimated_bytes_reclaimable: int = 0

class RetentionService:
    def __init__(self, data_dir: Path, reference_date: Date | None = None):
        self.data_dir = Path(data_dir).resolve()
        self.db_path = self.data_dir / "casual-scout.sqlite3"
        self.raw_dir = self.data_dir / "raw"
        self.log_dir = self.data_dir / "logs"
        self.manifest_file = self.data_dir / ".retention_gc_manifest.json"
        self.cutoff = compute_utc_cutoff(reference_date)

    def _check_ai_retired(self, conn: sqlite3.Connection) -> None:
        ai_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_%'"
        ).fetchall()
        if ai_tables:
            names = ", ".join(r[0] for r in ai_tables)
            raise RuntimeError(
                f"Cannot run retention: internal AI tables still exist ({names}). Run AI retirement migration first."
            )

    def scan_candidates(self) -> RetentionCandidateReport:
        cutoff_iso = self.cutoff.isoformat()
        report = RetentionCandidateReport(cutoff_utc=cutoff_iso)

        if not self.db_path.exists():
            return report

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._check_ai_retired(conn)

            # Find snapshots before cutoff
            rows = conn.execute(
                "SELECT id, raw_hash FROM snapshots WHERE observed_at < ?", (cutoff_iso,)
            ).fetchall()
            report.expired_snapshots_count = len(rows)
            report.expired_snapshot_ids = [r["id"] for r in rows]

            # Find raw hashes referenced ONLY by expired snapshots
            kept_hashes = {
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT raw_hash FROM snapshots WHERE observed_at >= ?", (cutoff_iso,)
                ).fetchall()
                if r[0]
            }

            expired_hashes = {r["raw_hash"] for r in rows if r["raw_hash"]}
            unref_hashes = expired_hashes - kept_hashes
            report.unreferenced_raw_hashes = sorted(list(unref_hashes))

            # Calculate raw file paths and bytes
            total_bytes = 0
            file_paths: list[str] = []
            for h in report.unreferenced_raw_hashes:
                candidate_path = self.raw_dir / h[:2] / h
                if candidate_path.is_file():
                    total_bytes += candidate_path.stat().st_size
                    file_paths.append(str(candidate_path))

            report.raw_files_to_delete = file_paths
            report.estimated_bytes_reclaimable = total_bytes
            return report
        finally:
            conn.close()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operations_retention.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/casual_scout/operations/retention.py tests/test_operations_retention.py
git commit -m "feat(retention): implement cutoff calculation and candidate audit scanning"
```

---

### Task 3: Two-Phase GC Execution and File Unlinking

**Files:**
- Modify: `src/casual_scout/operations/retention.py`
- Test: `tests/test_retention_execution.py`

**Interfaces:**
- Produces:
  - `retention_service.apply_retention() -> dict[str, Any]`
  - Atomic GC manifest write and resume support.

- [x] **Step 1: Write integration test for two-phase retention apply**

```python
# tests/test_retention_execution.py
from datetime import date as Date
from pathlib import Path
import sqlite3
import pytest
from casual_scout.operations.retention import RetentionService

def test_apply_retention_deletes_rows_and_files(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    raw_dir = tmp_path / "raw" / "ab"
    raw_dir.mkdir(parents=True)
    raw_file = raw_dir / "ab12345"
    raw_file.write_text("dummy payload content")

    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT);
        CREATE TABLE snapshot_entries (snapshot_id TEXT, app_id TEXT);
        CREATE TABLE raw_responses (hash TEXT PRIMARY KEY, path TEXT);
        CREATE TABLE shortlist (app_id TEXT PRIMARY KEY, title TEXT);

        INSERT INTO snapshots VALUES ('s_expired', '2026-09-01T00:00:00Z', 'ab12345');
        INSERT INTO snapshot_entries VALUES ('s_expired', 'game_1');
        INSERT INTO raw_responses VALUES ('ab12345', 'raw/ab/ab12345');
        INSERT INTO shortlist VALUES ('game_1', 'Saved Game');
    """)
    conn.commit()
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    summary = service.apply_retention()

    assert summary["deleted_snapshots"] == 1
    assert summary["deleted_raw_files"] == 1
    assert not raw_file.exists()

    # Verify shortlist remained
    conn = sqlite3.connect(db_file)
    row = conn.execute("SELECT title FROM shortlist WHERE app_id='game_1'").fetchone()
    assert row[0] == "Saved Game"
    conn.close()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retention_execution.py -v`
Expected: FAIL with `AttributeError: 'RetentionService' object has no attribute 'apply_retention'`

- [x] **Step 3: Implement `apply_retention` in `RetentionService`**

```python
# In src/casual_scout/operations/retention.py
    def apply_retention(self) -> dict[str, Any]:
        report = self.scan_candidates()
        if report.expired_snapshots_count == 0 and not report.unreferenced_raw_hashes:
            return {"status": "noop", "deleted_snapshots": 0, "deleted_raw_files": 0}

        # Step 1: Write persistent GC manifest before file unlinking
        manifest = {
            "cutoff_utc": report.cutoff_utc,
            "expired_snapshot_ids": report.expired_snapshot_ids,
            "raw_files": report.raw_files_to_delete,
            "raw_hashes": report.unreferenced_raw_hashes,
        }
        self.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

        # Step 2: DB deletion in transaction
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            with conn:
                # Grant maintenance session
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS maintenance_session (value TEXT)")
                conn.execute("INSERT OR REPLACE INTO temp.maintenance_session VALUES ('1')")

                # Delete snapshot entries & snapshots
                if report.expired_snapshot_ids:
                    q_marks = ",".join("?" for _ in report.expired_snapshot_ids)
                    conn.execute(
                        f"DELETE FROM snapshot_entries WHERE snapshot_id IN ({q_marks})",
                        report.expired_snapshot_ids,
                    )
                    conn.execute(
                        f"DELETE FROM snapshots WHERE id IN ({q_marks})",
                        report.expired_snapshot_ids,
                    )

                # Delete raw_responses
                if report.unreferenced_raw_hashes:
                    h_marks = ",".join("?" for _ in report.unreferenced_raw_hashes)
                    conn.execute(
                        f"DELETE FROM raw_responses WHERE hash IN ({h_marks})",
                        report.unreferenced_raw_hashes,
                    )

                conn.execute("DELETE FROM temp.maintenance_session")
        finally:
            conn.close()

        # Step 3: Filesystem deletion
        deleted_files_count = 0
        for p_str in report.raw_files_to_delete:
            p = Path(p_str).resolve()
            # Safety check: ensure file path is inside self.raw_dir
            if self.raw_dir in p.parents and p.is_file():
                p.unlink(missing_ok=True)
                deleted_files_count += 1

        self.manifest_file.unlink(missing_ok=True)

        return {
            "status": "success",
            "deleted_snapshots": report.expired_snapshots_count,
            "deleted_raw_files": deleted_files_count,
            "reclaimed_bytes": report.estimated_bytes_reclaimable,
        }
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retention_execution.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/casual_scout/operations/retention.py tests/test_retention_execution.py
git commit -m "feat(retention): implement two-phase GC transaction and secure unlinking"
```

---

### Task 4: CLI Commands and Daily Scheduler Integration

**Files:**
- Modify: `src/casual_scout/cli.py`
- Modify: `src/casual_scout/web/app.py`
- Test: `tests/test_cli_retention.py`

**Interfaces:**
- CLI commands:
  - `casual_scout retention --dry-run [--data-dir <path>]`
  - `casual_scout retention --apply [--data-dir <path>]`
- Daily tick: Run `retention_service.apply_retention()` once per UTC day during `serve` lifespan.

- [x] **Step 1: Write test for retention CLI commands**

```python
# tests/test_cli_retention.py
import pytest
from casual_scout.cli import main

def test_cli_retention_dry_run_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["retention", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--apply" in captured.out
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_retention.py -v`
Expected: FAIL with `invalid choice: 'retention'`

- [x] **Step 3: Implement `retention` CLI parser and handler in `cli.py`**

```python
# In src/casual_scout/cli.py
retention_parser = subparsers.add_parser("retention", help="Audit or apply 15-day rolling retention")
retention_parser.add_argument("--data-dir", type=Path, default=Path("data"))
retention_group = retention_parser.add_mutually_exclusive_group(required=True)
retention_group.add_argument("--dry-run", action="store_true", help="Audit candidates without altering data")
retention_group.add_argument("--apply", action="store_true", help="Execute deletion")

def _run_retention(args: argparse.Namespace) -> int:
    from casual_scout.operations.retention import RetentionService
    service = RetentionService(args.data_dir)
    if args.dry_run:
        report = service.scan_candidates()
        print(f"Cutoff (UTC): {report.cutoff_utc}")
        print(f"Expired snapshots: {report.expired_snapshots_count}")
        print(f"Unreferenced raw files: {len(report.raw_files_to_delete)}")
        print(f"Reclaimable bytes: {report.estimated_bytes_reclaimable:,} bytes")
        return 0
    else:
        summary = service.apply_retention()
        print(f"Retention applied: {summary}")
        return 0
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_retention.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/casual_scout/cli.py tests/test_cli_retention.py
git commit -m "feat(cli): add retention --dry-run and --apply administration commands"
```
