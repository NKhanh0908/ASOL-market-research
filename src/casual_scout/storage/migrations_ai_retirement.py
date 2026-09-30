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
