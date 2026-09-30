from __future__ import annotations

import sqlite3


def authorize_maintenance_connection(conn: sqlite3.Connection) -> None:
    """Authorize connection to execute maintenance DELETE operations on immutable tables."""
    conn.create_function("is_maintenance_authorized", 0, lambda: 1)


def deauthorize_maintenance_connection(conn: sqlite3.Connection) -> None:
    """Revoke maintenance authorization on connection."""
    conn.create_function("is_maintenance_authorized", 0, lambda: 0)


def migrate_retention_triggers(conn: sqlite3.Connection) -> None:
    """Replace hard DELETE triggers on immutable tables with maintenance-checked triggers."""
    with conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        # 1. snapshots
        if "snapshots" in tables:
            conn.execute("DROP TRIGGER IF EXISTS snapshots_are_immutable_delete")
            conn.execute("DROP TRIGGER IF EXISTS guard_snapshots_delete")
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS snapshots_are_immutable_delete
                BEFORE DELETE ON snapshots
                FOR EACH ROW
                WHEN is_maintenance_authorized() != 1
                BEGIN
                    SELECT RAISE(ABORT, 'snapshots are immutable outside maintenance');
                END;
            """)

        # 2. entries
        if "entries" in tables:
            conn.execute("DROP TRIGGER IF EXISTS entries_are_immutable_delete")
            conn.execute("DROP TRIGGER IF EXISTS guard_entries_delete")
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS entries_are_immutable_delete
                BEFORE DELETE ON entries
                FOR EACH ROW
                WHEN is_maintenance_authorized() != 1
                BEGIN
                    SELECT RAISE(ABORT, 'snapshot entries are immutable outside maintenance');
                END;
            """)

        # 3. metadata_versions
        if "metadata_versions" in tables:
            conn.execute("DROP TRIGGER IF EXISTS metadata_versions_are_immutable_delete")
            conn.execute("DROP TRIGGER IF EXISTS guard_metadata_versions_delete")
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS metadata_versions_are_immutable_delete
                BEFORE DELETE ON metadata_versions
                FOR EACH ROW
                WHEN is_maintenance_authorized() != 1
                BEGIN
                    SELECT RAISE(ABORT, 'metadata versions are immutable outside maintenance');
                END;
            """)

        # 4. snapshot_metadata
        if "snapshot_metadata" in tables:
            conn.execute("DROP TRIGGER IF EXISTS snapshot_metadata_is_immutable_delete")
            conn.execute("DROP TRIGGER IF EXISTS guard_snapshot_metadata_delete")
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS snapshot_metadata_is_immutable_delete
                BEFORE DELETE ON snapshot_metadata
                FOR EACH ROW
                WHEN is_maintenance_authorized() != 1
                BEGIN
                    SELECT RAISE(ABORT, 'snapshot metadata bindings are immutable outside maintenance');
                END;
            """)

        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations VALUES ('2026-09-30-data-retention-triggers', datetime('now'))"
        )
