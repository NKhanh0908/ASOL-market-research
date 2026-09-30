from datetime import date as Date
import json
from pathlib import Path
import sqlite3
import pytest

from casual_scout.operations.retention import RetentionService
from casual_scout.storage.migrations_retention import migrate_retention_triggers


def test_apply_retention_deletes_rows_and_files(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    raw_dir = tmp_path / "raw" / "ab"
    raw_dir.mkdir(parents=True)
    raw_file = raw_dir / "ab12345"
    raw_file.write_text("dummy payload content")

    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT);
        CREATE TABLE entries (snapshot_id TEXT, app_id TEXT);
        CREATE TABLE raw_responses (hash TEXT PRIMARY KEY, path TEXT);
        CREATE TABLE shortlists (app_id TEXT PRIMARY KEY, title TEXT);

        INSERT INTO snapshots VALUES ('s_expired', '2026-09-01T00:00:00Z', 'ab12345');
        INSERT INTO entries VALUES ('s_expired', 'game_1');
        INSERT INTO raw_responses VALUES ('ab12345', 'raw/ab/ab12345');
        INSERT INTO shortlists VALUES ('game_1', 'Saved Game');
    """)
    conn.commit()
    migrate_retention_triggers(conn)
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    summary = service.apply_retention()

    assert summary["status"] == "success"
    assert summary["deleted_snapshots"] == 1
    assert summary["deleted_raw_files"] == 1
    assert not raw_file.exists()

    # Verify shortlist remained intact
    conn = sqlite3.connect(db_file)
    row = conn.execute("SELECT title FROM shortlists WHERE app_id='game_1'").fetchone()
    assert row[0] == "Saved Game"
    # Verify snapshot was removed
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
    conn.close()


def test_apply_retention_preserves_shared_raw_file(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    raw_dir = tmp_path / "raw" / "sh"
    raw_dir.mkdir(parents=True)
    raw_file = raw_dir / "shared123"
    raw_file.write_text("shared payload")

    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT);
        CREATE TABLE entries (snapshot_id TEXT, app_id TEXT);
        CREATE TABLE raw_responses (hash TEXT PRIMARY KEY, path TEXT);

        -- s_old is expired, s_new is kept, both reference shared123
        INSERT INTO snapshots VALUES ('s_old', '2026-09-01T00:00:00Z', 'shared123');
        INSERT INTO snapshots VALUES ('s_new', '2026-09-25T00:00:00Z', 'shared123');
        INSERT INTO raw_responses VALUES ('shared123', 'raw/sh/shared123');
    """)
    conn.commit()
    migrate_retention_triggers(conn)
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    summary = service.apply_retention()

    assert summary["status"] == "success"
    assert summary["deleted_snapshots"] == 1
    assert summary["deleted_raw_files"] == 0
    # Raw file must still exist!
    assert raw_file.exists()

    conn = sqlite3.connect(db_file)
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM raw_responses WHERE hash='shared123'").fetchone()[0] == 1
    conn.close()


def test_apply_retention_cleans_analytics_and_canonical(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE daily_canonical_snapshots (date TEXT PRIMARY KEY, snapshot_id TEXT, observed_at TEXT);
        CREATE TABLE daily_rank_analytics (date TEXT, app_id TEXT, PRIMARY KEY (date, app_id));

        INSERT INTO daily_canonical_snapshots VALUES ('2026-09-10', 's1', '2026-09-10T12:00:00Z');
        INSERT INTO daily_canonical_snapshots VALUES ('2026-09-25', 's2', '2026-09-25T12:00:00Z');

        INSERT INTO daily_rank_analytics VALUES ('2026-09-10', 'app1');
        INSERT INTO daily_rank_analytics VALUES ('2026-09-25', 'app1');
    """)
    conn.commit()
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    summary = service.apply_retention()

    assert summary["status"] == "success"
    assert summary["deleted_daily_canonical"] == 1
    assert summary["deleted_daily_analytics"] == 1

    conn = sqlite3.connect(db_file)
    canon_dates = [r[0] for r in conn.execute("SELECT date FROM daily_canonical_snapshots").fetchall()]
    assert canon_dates == ["2026-09-25"]
    an_dates = [r[0] for r in conn.execute("SELECT date FROM daily_rank_analytics").fetchall()]
    assert an_dates == ["2026-09-25"]
    conn.close()


def test_apply_retention_crash_recovery_from_manifest(tmp_path: Path):
    raw_dir = tmp_path / "raw" / "zz"
    raw_dir.mkdir(parents=True)
    stale_file = raw_dir / "zz999"
    stale_file.write_text("orphaned content")

    manifest_file = tmp_path / ".retention_gc_manifest.json"
    manifest_data = {
        "cutoff_utc": "2026-09-16T00:00:00Z",
        "expired_snapshot_ids": [],
        "raw_files": [str(stale_file)],
        "raw_hashes": ["zz999"],
        "log_files": [],
    }
    manifest_file.write_text(json.dumps(manifest_data))

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    # DB does not even exist, but manifest exists: apply_retention should clean pending files
    summary = service.apply_retention()

    assert not stale_file.exists()
    assert not manifest_file.exists()


def test_apply_retention_rejects_paths_outside_raw_or_logs(tmp_path: Path):
    external_file = tmp_path.parent / "important_secret.txt"
    external_file.write_text("critical external data")

    manifest_file = tmp_path / ".retention_gc_manifest.json"
    manifest_data = {
        "cutoff_utc": "2026-09-16T00:00:00Z",
        "expired_snapshot_ids": [],
        "raw_files": [str(external_file)],
        "raw_hashes": ["important_secret"],
        "log_files": [],
    }
    manifest_file.write_text(json.dumps(manifest_data))

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    summary = service.apply_retention()

    # External file must NOT be deleted
    assert external_file.exists()
    external_file.unlink(missing_ok=True)
