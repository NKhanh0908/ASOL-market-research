import sqlite3
from pathlib import Path
import pytest

from casual_scout.storage.migrations_retention import (
    authorize_maintenance_connection,
    deauthorize_maintenance_connection,
    migrate_retention_triggers,
)
from casual_scout.storage.repository import Repository


def test_regular_connection_cannot_delete_snapshot(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT);
        INSERT INTO snapshots VALUES ('s1', '2026-09-01T00:00:00Z');
    """)
    conn.commit()
    migrate_retention_triggers(conn)

    # Standard connection attempting DELETE should abort
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM snapshots WHERE id = 's1'")
    conn.close()


def test_maintenance_session_can_delete_snapshot_and_deauthorize(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT);
        CREATE TABLE entries (snapshot_id TEXT, app_id TEXT);
        CREATE TABLE metadata_versions (id TEXT PRIMARY KEY);
        CREATE TABLE snapshot_metadata (snapshot_id TEXT, app_id TEXT);

        INSERT INTO snapshots VALUES ('s1', '2026-09-01T00:00:00Z');
        INSERT INTO entries VALUES ('s1', 'a1');
        INSERT INTO metadata_versions VALUES ('m1');
        INSERT INTO snapshot_metadata VALUES ('s1', 'a1');
    """)
    conn.commit()
    migrate_retention_triggers(conn)

    # Authorize maintenance connection
    authorize_maintenance_connection(conn)
    conn.execute("DELETE FROM snapshot_metadata WHERE snapshot_id = 's1'")
    conn.execute("DELETE FROM entries WHERE snapshot_id = 's1'")
    conn.execute("DELETE FROM metadata_versions WHERE id = 'm1'")
    conn.execute("DELETE FROM snapshots WHERE id = 's1'")
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM metadata_versions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM snapshot_metadata").fetchone()[0] == 0

    # Deauthorize and verify it protects again
    deauthorize_maintenance_connection(conn)
    conn.execute("INSERT INTO snapshots VALUES ('s2', '2026-09-02T00:00:00Z')")
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM snapshots WHERE id = 's2'")
    conn.close()


def test_repository_initialize_applies_retention_triggers(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()

    conn = sqlite3.connect(repo.database_path)
    # Verify migration record is present
    row = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = '2026-09-30-data-retention-triggers'"
    ).fetchone()
    assert row is not None

    # Check that regular connection cannot delete snapshots
    conn.execute(
        "INSERT OR IGNORE INTO snapshots (id, observed_at, raw_hash) VALUES ('test-snap', '2026-09-01T00:00:00Z', 'dummy-hash')"
    )
    conn.commit()

    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM snapshots WHERE id = 'test-snap'")

    # Authorize connection and delete
    authorize_maintenance_connection(conn)
    conn.execute("DELETE FROM snapshots WHERE id = 'test-snap'")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM snapshots WHERE id = 'test-snap'").fetchone()[0] == 0
    conn.close()
