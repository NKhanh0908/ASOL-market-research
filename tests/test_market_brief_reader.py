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
