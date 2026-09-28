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
