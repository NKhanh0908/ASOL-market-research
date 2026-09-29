"""Additive and non-destructive migrations for Android core support."""
from __future__ import annotations

import sqlite3


def migrate_android_columns(conn: sqlite3.Connection) -> None:
    """Add Android columns, indices, and canonical snapshot table without breaking existing data."""
    additions = {
        "metadata_versions": {
            "installs": "TEXT",
            "min_installs": "INTEGER",
            "has_ads": "INTEGER",
            "has_iap": "INTEGER",
        },
        "daily_rank_analytics": {
            "platform": "TEXT NOT NULL DEFAULT 'ios'",
            "installs": "TEXT",
            "min_installs": "INTEGER",
        },
    }
    for table, columns in additions.items():
        existing_info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in existing_info}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    # Core indices
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analytics_date_platform_country "
        "ON daily_rank_analytics(date, platform, country)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_cache_platform "
        "ON metadata_versions(platform, country, fetched_at)"
    )

    # Core platform canonical snapshots table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_canonical_snapshots (
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            feed_type TEXT NOT NULL,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
            observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(date, platform, country, feed_type)
        )
        """
    )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_canonical_snapshots'").fetchone():
        conn.execute("""
            INSERT OR IGNORE INTO platform_canonical_snapshots
                (date,platform,country,feed_type,snapshot_id,observed_at,created_at)
            SELECT d.date,c.platform,d.country,
                   CASE WHEN c.collection IN ('topgrossingapplications','top-grossing')
                        THEN 'top-grossing' ELSE 'top-free' END,
                   d.snapshot_id,d.observed_at,d.created_at
            FROM daily_canonical_snapshots d
            JOIN snapshots s ON s.id=d.snapshot_id
            JOIN market_runs m ON m.id=s.market_run_id
            JOIN charts c ON c.id=m.chart_id
        """)
