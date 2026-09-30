from datetime import date as Date, datetime, UTC
from pathlib import Path
import sqlite3
import pytest

from casual_scout.operations.retention import RetentionService, compute_utc_cutoff


def test_cutoff_is_d_minus_14_at_midnight():
    ref = Date(2026, 9, 30)
    cutoff = compute_utc_cutoff(ref)
    assert cutoff.isoformat() == "2026-09-16T00:00:00+00:00"


def test_scan_aborts_if_ai_tables_present(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE ai_evaluation_runs (id TEXT PRIMARY KEY);")
    conn.commit()
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    with pytest.raises(RuntimeError, match="internal AI tables still exist"):
        service.scan_candidates()


def test_scan_candidates_finds_old_snapshots_and_retains_shortlist(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT);
        CREATE TABLE entries (snapshot_id TEXT, app_id TEXT);
        CREATE TABLE raw_responses (hash TEXT PRIMARY KEY, path TEXT);
        CREATE TABLE shortlists (app_id TEXT PRIMARY KEY, title TEXT);

        -- Expired (observed 2026-09-10)
        INSERT INTO snapshots VALUES ('s_old', '2026-09-10T12:00:00Z', 'hash_old');
        INSERT INTO entries VALUES ('s_old', 'game_old');
        INSERT INTO raw_responses VALUES ('hash_old', 'raw/01/hash_old');

        -- Kept (observed 2026-09-25)
        INSERT INTO snapshots VALUES ('s_new', '2026-09-25T12:00:00Z', 'hash_new');
        INSERT INTO entries VALUES ('s_new', 'game_new');
        INSERT INTO raw_responses VALUES ('hash_new', 'raw/02/hash_new');

        -- Shortlist bookmarked game_old (must be preserved)
        INSERT INTO shortlists VALUES ('game_old', 'Old But Gold');
    """)
    conn.commit()
    conn.close()

    # Create dummy raw file for hash_old
    hash_old_dir = raw_dir / "ha"
    hash_old_dir.mkdir(parents=True)
    hash_old_file = hash_old_dir / "hash_old"
    hash_old_file.write_text("old content")

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    report = service.scan_candidates()

    assert report.expired_snapshots_count == 1
    assert "s_old" in report.expired_snapshot_ids
    assert "s_new" not in report.expired_snapshot_ids
    assert "hash_old" in report.unreferenced_raw_hashes
    assert "hash_new" not in report.unreferenced_raw_hashes
    assert len(report.raw_files_to_delete) == 1
    assert report.estimated_bytes_reclaimable > 0


def test_scan_candidates_preserves_shared_raw_hashes(tmp_path: Path):
    db_file = tmp_path / "casual-scout.sqlite3"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT);
        CREATE TABLE raw_responses (hash TEXT PRIMARY KEY, path TEXT);

        -- Shared raw hash between old and new snapshots
        INSERT INTO snapshots VALUES ('s_old', '2026-09-10T12:00:00Z', 'shared_hash');
        INSERT INTO snapshots VALUES ('s_new', '2026-09-25T12:00:00Z', 'shared_hash');
        INSERT INTO raw_responses VALUES ('shared_hash', 'raw/sh/shared_hash');
    """)
    conn.commit()
    conn.close()

    service = RetentionService(tmp_path, reference_date=Date(2026, 9, 30))
    report = service.scan_candidates()

    assert report.expired_snapshots_count == 1
    assert "s_old" in report.expired_snapshot_ids
    # shared_hash is still needed by s_new!
    assert "shared_hash" not in report.unreferenced_raw_hashes
    assert len(report.raw_files_to_delete) == 0
