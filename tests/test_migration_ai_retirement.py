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
