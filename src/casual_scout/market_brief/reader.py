from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, date as Date, timedelta
from pathlib import Path
from typing import Any

@dataclass
class SnapshotData:
    snapshot_id: str
    observed_at: str
    observed_date: str
    quality: str
    raw_hash: str
    entries: list[dict[str, Any]]

class MarketBriefReader:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()

    def _get_connection(self) -> sqlite3.Connection:
        # SQLite read-only URI connection
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get_window_snapshots(
        self, country: str, platform: str, target_date: str
    ) -> dict[str, SnapshotData]:
        end_date = Date.fromisoformat(target_date)
        date_strings = [(end_date - timedelta(days=i)).isoformat() for i in range(7)]

        provider = "apple" if platform == "ios" else "google"
        collection = "topfreeapplications" if platform == "ios" else "top-free"
        genre = "7003" if platform == "ios" else "GAME_CASUAL"

        result: dict[str, SnapshotData] = {}
        if not self.db_path.is_file():
            return result

        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Find chart
                chart_row = conn.execute(
                    """
                    SELECT id FROM charts
                    WHERE provider = ? AND platform = ? AND country = ?
                      AND collection = ? AND genre = ? AND depth = 100
                    LIMIT 1
                    """,
                    (provider, platform, country, collection, genre),
                ).fetchone()

                if not chart_row:
                    return result
                chart_id = chart_row["id"]

                for d_str in date_strings:
                    # 1. Prefer canonical
                    snap_row = None
                    # check if canonical_snapshots table exists
                    has_canonical = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='canonical_snapshots'"
                    ).fetchone()
                    if has_canonical:
                        snap_row = conn.execute(
                            """
                            SELECT s.id, s.observed_at, s.quality, s.raw_hash
                            FROM canonical_snapshots c
                            JOIN snapshots s ON s.id = c.snapshot_id
                            WHERE c.chart_id = ? AND c.observed_date = ? AND s.quality = 'complete'
                            LIMIT 1
                            """,
                            (chart_id, d_str),
                        ).fetchone()

                    # 2. Fallback to latest complete in day
                    if not snap_row:
                        start_utc = f"{d_str}T00:00:00Z"
                        end_utc = f"{d_str}T23:59:59Z"
                        snap_row = conn.execute(
                            """
                            SELECT id, observed_at, quality, raw_hash
                            FROM snapshots
                            WHERE chart_id = ? AND observed_at >= ? AND observed_at <= ? AND quality = 'complete'
                            ORDER BY observed_at DESC, id ASC
                            LIMIT 1
                            """,
                            (chart_id, start_utc, end_utc),
                        ).fetchone()

                    if snap_row:
                        snap_id = snap_row["id"]
                        entries_cursor = conn.execute(
                            """
                            SELECT app_id, rank, name, store_url
                            FROM snapshot_entries
                            WHERE snapshot_id = ?
                            ORDER BY rank ASC
                            """,
                            (snap_id,),
                        )
                        entries = [dict(r) for r in entries_cursor.fetchall()]
                        result[d_str] = SnapshotData(
                            snapshot_id=snap_id,
                            observed_at=snap_row["observed_at"],
                            observed_date=d_str,
                            quality=snap_row["quality"],
                            raw_hash=snap_row["raw_hash"],
                            entries=entries,
                        )
            finally:
                conn.execute("ROLLBACK")
        return result
