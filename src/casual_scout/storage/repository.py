from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from casual_scout.config import Settings
from casual_scout.models import Chart, HttpResult, ParsedChart
from casual_scout.storage.raw import RawStore

_OPEN_RUN_STATUSES = {"queued", "running"}
_MARKETS = (
    ("vn", "Vietnam", "ASEAN", "verified", None),
    ("us", "United States", "US", "verified", None),
    ("bn", "Brunei", "ASEAN", "verified", None),
    ("kh", "Cambodia", "ASEAN", "verified", None),
    ("id", "Indonesia", "ASEAN", "verified", None),
    ("la", "Laos", "ASEAN", "verified", None),
    ("my", "Malaysia", "ASEAN", "verified", None),
    ("mm", "Myanmar", "ASEAN", "verified", None),
    ("ph", "Philippines", "ASEAN", "verified", None),
    ("sg", "Singapore", "ASEAN", "verified", None),
    ("th", "Thailand", "ASEAN", "verified", None),
    ("tl", "Timor-Leste", "ASEAN", "unverified", "Apple source not verified"),
)


def _uuid() -> str:
    return str(uuid4())


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_utc_text(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return _utc_text(parsed)


class Repository:
    """SQLite persistence for immutable market snapshots and metadata versions."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        settings = Settings(self.data_dir)
        self.database_path = settings.database_path
        self._raw = RawStore(settings.raw_dir)

    def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        now = _utc_text(datetime.now(UTC))
        with closing(self._connect()) as connection:
            connection.executescript(schema)
            # Idempotent column migrations for Phase 3.5
            meta_cols = [r[1] for r in connection.execute("PRAGMA table_info(metadata_versions)").fetchall()]
            if "in_app_purchases_json" not in meta_cols:
                connection.execute("ALTER TABLE metadata_versions ADD COLUMN in_app_purchases_json TEXT DEFAULT '[]'")
            if "has_in_app_purchases" not in meta_cols:
                connection.execute("ALTER TABLE metadata_versions ADD COLUMN has_in_app_purchases INTEGER DEFAULT 0")
            if "monetization_model" not in meta_cols:
                connection.execute("ALTER TABLE metadata_versions ADD COLUMN monetization_model TEXT DEFAULT 'UNKNOWN'")

            an_cols = [r[1] for r in connection.execute("PRAGMA table_info(daily_rank_analytics)").fetchall()]
            if "grossing_rank" not in an_cols:
                connection.execute("ALTER TABLE daily_rank_analytics ADD COLUMN grossing_rank INTEGER")
            if "free_rank" not in an_cols:
                connection.execute("ALTER TABLE daily_rank_analytics ADD COLUMN free_rank INTEGER")
            if "monetization_model" not in an_cols:
                connection.execute("ALTER TABLE daily_rank_analytics ADD COLUMN monetization_model TEXT")
            if "monetization_efficiency_flag" not in an_cols:
                connection.execute("ALTER TABLE daily_rank_analytics ADD COLUMN monetization_efficiency_flag TEXT")

            connection.executemany(
                """
                INSERT OR IGNORE INTO markets
                    (country, name, market_group, source_status, source_note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(*market, now) for market in _MARKETS],
            )
            connection.commit()

    def save_snapshot(
        self, run_id: str, result: HttpResult, parsed: ParsedChart
    ) -> str:
        if result.body is None:
            raise ValueError("snapshot response body is required")
        raw_records, final_hash = self._persist_result_bodies(result)

        with self._write_connection() as connection:
            run = connection.execute(
                "SELECT id FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise ValueError(f"unknown run: {run_id}")

            chart_id = self._ensure_chart(connection, parsed.chart, result.url)
            market_run_id = self._ensure_market_run(
                connection, run_id, chart_id, result.started_at
            )
            existing = connection.execute(
                "SELECT id FROM snapshots WHERE market_run_id = ?", (market_run_id,)
            ).fetchone()
            if existing is not None:
                return str(existing["id"])

            self._insert_raw_records(connection, raw_records)
            snapshot_id = _uuid()
            connection.execute(
                """
                INSERT INTO snapshots
                    (id, market_run_id, raw_hash, observed_at, source_updated,
                     quality, issues_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    market_run_id,
                    final_hash,
                    _utc_text(result.started_at),
                    _optional_utc_text(parsed.source_updated),
                    parsed.quality,
                    json.dumps(parsed.issues, ensure_ascii=False),
                ),
            )
            for entry in parsed.entries:
                app_ref = self._ensure_app(
                    connection,
                    parsed.chart.provider,
                    parsed.chart.platform,
                    entry.app_id,
                    result.started_at,
                )
                connection.execute(
                    """
                    INSERT INTO entries
                        (snapshot_id, app_ref, app_id, rank, name, store_url,
                         icon_url, developer, source_genres_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        app_ref,
                        entry.app_id,
                        entry.rank,
                        entry.name,
                        entry.store_url,
                        entry.icon_url,
                        entry.developer,
                        json.dumps(entry.source_genres, ensure_ascii=False, sort_keys=True),
                    ),
                )

            chart_status = {
                "complete": "complete",
                "partial": "partial",
                "invalid": "failed",
            }[parsed.quality]
            valid_count = len(parsed.entries) if parsed.quality != "invalid" else 0
            connection.execute(
                """
                UPDATE market_runs
                SET chart_status = ?, error = ?, received_count = ?, valid_count = ?,
                    ended_at = ?
                WHERE id = ?
                """,
                (
                    chart_status,
                    "; ".join(parsed.issues) or None,
                    len(parsed.entries),
                    valid_count,
                    _utc_text(result.started_at + timedelta(milliseconds=result.elapsed_ms)),
                    market_run_id,
                ),
            )
            self._insert_observations(
                connection, result, raw_records, run_id, market_run_id
            )
            return snapshot_id

    def latest_complete(self, chart: Chart) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT snapshots.id
                FROM snapshots
                JOIN market_runs ON market_runs.id = snapshots.market_run_id
                JOIN charts ON charts.id = market_runs.chart_id
                WHERE charts.provider = ? AND charts.platform = ? AND charts.country = ?
                  AND charts.collection = ? AND charts.genre = ? AND charts.depth = ?
                  AND charts.version = ? AND snapshots.quality = 'complete'
                ORDER BY snapshots.observed_at DESC, snapshots.id DESC
                LIMIT 1
                """,
                (
                    chart.provider,
                    chart.platform,
                    chart.country.lower(),
                    chart.collection,
                    chart.genre,
                    chart.depth,
                    chart.version,
                ),
            ).fetchone()
        return None if row is None else self.get_snapshot(str(row["id"]))

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            snapshot = connection.execute(
                """
                SELECT snapshots.id, snapshots.raw_hash, snapshots.quality, snapshots.observed_at,
                       snapshots.source_updated, snapshots.issues_json,
                       charts.provider, charts.platform, charts.country,
                       charts.collection, charts.genre, charts.depth, charts.version
                FROM snapshots
                JOIN market_runs ON market_runs.id = snapshots.market_run_id
                JOIN charts ON charts.id = market_runs.chart_id
                WHERE snapshots.id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            if snapshot is None:
                raise KeyError(snapshot_id)
            entries = connection.execute(
                """
                SELECT app_id, rank, name, store_url, icon_url, developer,
                       source_genres_json
                FROM entries
                WHERE snapshot_id = ?
                ORDER BY rank
                """,
                (snapshot_id,),
            ).fetchall()
            bindings = connection.execute(
                """
                SELECT app_id, metadata_version_id
                FROM snapshot_metadata
                WHERE snapshot_id = ?
                ORDER BY app_id
                """,
                (snapshot_id,),
            ).fetchall()

        return {
            "id": str(snapshot["id"]),
            "raw_hash": snapshot["raw_hash"],
            "chart": {
                "provider": snapshot["provider"],
                "platform": snapshot["platform"],
                "country": snapshot["country"],
                "collection": snapshot["collection"],
                "genre": snapshot["genre"],
                "depth": snapshot["depth"],
                "version": snapshot["version"],
            },
            "entries": [
                {
                    "app_id": row["app_id"],
                    "rank": row["rank"],
                    "name": row["name"],
                    "store_url": row["store_url"],
                    "icon_url": row["icon_url"],
                    "developer": row["developer"],
                    "source_genres": json.loads(row["source_genres_json"]),
                }
                for row in entries
            ],
            "quality": snapshot["quality"],
            "observed_at": snapshot["observed_at"],
            "source_updated": snapshot["source_updated"],
            "issues": json.loads(snapshot["issues_json"]),
            "metadata_versions": {
                row["app_id"]: row["metadata_version_id"] for row in bindings
            },
        }


    def save_metadata(
        self, country: str, values: dict[str, dict], result: HttpResult
    ) -> dict[str, str]:
        if result.body is None:
            raise ValueError("metadata response body is required")
        country = country.lower()
        raw_records, final_hash = self._persist_result_bodies(result)
        fetched_at = _utc_text(result.started_at)
        versions: dict[str, str] = {}

        with self._write_connection() as connection:
            market = connection.execute(
                "SELECT country FROM markets WHERE country = ?", (country,)
            ).fetchone()
            if market is None:
                raise ValueError(f"unknown market: {country}")
            self._insert_raw_records(connection, raw_records)
            for app_id, metadata in values.items():
                if not isinstance(app_id, str) or not app_id:
                    raise ValueError("metadata app IDs must be non-empty text")
                if not isinstance(metadata, dict):
                    raise TypeError(f"metadata for {app_id} must be a mapping")
                app_ref = self._ensure_app(
                    connection, "apple", "ios", app_id, result.started_at
                )
                existing = connection.execute(
                    """
                    SELECT id FROM metadata_versions
                    WHERE provider = 'apple' AND platform = 'ios' AND country = ?
                      AND app_id = ? AND fetched_at = ? AND raw_hash = ?
                    """,
                    (country, app_id, fetched_at, final_hash),
                ).fetchone()
                if existing is not None:
                    versions[app_id] = str(existing["id"])
                    continue

                version_id = _uuid()
                genres = metadata.get("genres") or []
                iap_list = metadata.get("inAppPurchases") or metadata.get("in_app_purchases") or []
                has_iap = 1 if len(iap_list) > 0 or metadata.get("hasInAppPurchases") or metadata.get("has_in_app_purchases") else 0
                monetization_model = metadata.get("monetization_model") or metadata.get("monetizationModel") or "UNKNOWN"

                connection.execute(
                    """
                    INSERT INTO metadata_versions
                        (id, app_ref, provider, platform, country, app_id, fetched_at,
                         status, raw_hash, name, developer, primary_genre, genres_json,
                         description, average_rating, rating_count, store_url, price,
                         currency, in_app_purchases_json, has_in_app_purchases, monetization_model, values_json)
                    VALUES (?, ?, 'apple', 'ios', ?, ?, ?, 'complete', ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        app_ref,
                        country,
                        app_id,
                        fetched_at,
                        final_hash,
                        metadata.get("trackName"),
                        metadata.get("artistName") or metadata.get("sellerName"),
                        metadata.get("primaryGenreName"),
                        json.dumps(genres, ensure_ascii=False, sort_keys=True),
                        metadata.get("description"),
                        metadata.get("averageUserRating"),
                        metadata.get("userRatingCount"),
                        metadata.get("trackViewUrl"),
                        metadata.get("price"),
                        metadata.get("currency"),
                        json.dumps(iap_list, ensure_ascii=False, sort_keys=True),
                        has_iap,
                        monetization_model,
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )
                versions[app_id] = version_id

            self._insert_observations(connection, result, raw_records, None, None)
        return versions

    def cached_metadata(
        self, country: str, app_ids: list[str], now: datetime
    ) -> dict[str, str]:
        if not app_ids:
            return {}
        now_text = _utc_text(now)
        fresh_after = _utc_text(now.astimezone(UTC) - timedelta(hours=24))
        unique_ids = list(dict.fromkeys(app_ids))
        placeholders = ", ".join("?" for _ in unique_ids)
        query = f"""
            SELECT app_id, id
            FROM (
                SELECT app_id, id,
                       ROW_NUMBER() OVER (
                           PARTITION BY app_id ORDER BY fetched_at DESC, id DESC
                       ) AS newest
                FROM metadata_versions
                WHERE provider = 'apple' AND platform = 'ios' AND country = ?
                  AND status = 'complete' AND fetched_at >= ? AND fetched_at <= ?
                  AND app_id IN ({placeholders})
            )
            WHERE newest = 1
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(
                query, (country.lower(), fresh_after, now_text, *unique_ids)
            ).fetchall()
        return {row["app_id"]: row["id"] for row in rows}

    def bind_metadata(self, snapshot_id: str, versions: dict[str, str]) -> None:
        with self._write_connection() as connection:
            snapshot = connection.execute(
                """
                SELECT market_runs.id AS market_run_id, runs.status AS run_status,
                       charts.provider, charts.platform, charts.country
                FROM snapshots
                JOIN market_runs ON market_runs.id = snapshots.market_run_id
                JOIN runs ON runs.id = market_runs.run_id
                JOIN charts ON charts.id = market_runs.chart_id
                WHERE snapshots.id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            if snapshot is None:
                raise KeyError(snapshot_id)
            if snapshot["run_status"] not in _OPEN_RUN_STATUSES:
                raise RuntimeError("cannot bind metadata to a snapshot from a closed run")

            for app_id, version_id in versions.items():
                entry = connection.execute(
                    "SELECT 1 FROM entries WHERE snapshot_id = ? AND app_id = ?",
                    (snapshot_id, app_id),
                ).fetchone()
                version = connection.execute(
                    """
                    SELECT provider, platform, country, app_id
                    FROM metadata_versions WHERE id = ?
                    """,
                    (version_id,),
                ).fetchone()
                if entry is None or version is None or (
                    version["provider"],
                    version["platform"],
                    version["country"],
                    version["app_id"],
                ) != (
                    snapshot["provider"],
                    snapshot["platform"],
                    snapshot["country"],
                    app_id,
                ):
                    raise ValueError(
                        f"metadata version {version_id} does not match snapshot app {app_id}"
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO snapshot_metadata
                        (snapshot_id, app_id, metadata_version_id)
                    VALUES (?, ?, ?)
                    """,
                    (snapshot_id, app_id, version_id),
                )

            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM entries WHERE snapshot_id = ?) AS entries,
                    (SELECT COUNT(*) FROM snapshot_metadata WHERE snapshot_id = ?) AS bound
                """,
                (snapshot_id, snapshot_id),
            ).fetchone()
            enrichment_status = (
                "complete" if counts["entries"] == counts["bound"] else "partial"
            )
            connection.execute(
                "UPDATE market_runs SET enrichment_status = ? WHERE id = ?",
                (enrichment_status, snapshot["market_run_id"]),
            )

    def get_snapshot_metadata(
        self, snapshot_id: str
    ) -> dict[str, dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT mv.app_id, mv.name, mv.developer, mv.primary_genre,
                       mv.genres_json, mv.description, mv.average_rating,
                       mv.rating_count, mv.store_url, mv.price, mv.currency
                FROM snapshot_metadata sm
                JOIN metadata_versions mv ON mv.id = sm.metadata_version_id
                WHERE sm.snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchall()
        result = {}
        for r in rows:
            d = dict(r)
            d["genres"] = (
                json.loads(d["genres_json"]) if d["genres_json"] else []
            )
            result[d["app_id"]] = d
        return result

    def save_canonical_snapshot(
        self, date_str: str, country: str, snapshot_id: str, observed_at: str
    ) -> None:
        country_norm = country.lower()
        now = _utc_text(datetime.now(UTC))
        with self._write_connection() as connection:
            connection.execute(
                """
                INSERT INTO daily_canonical_snapshots (date, country, snapshot_id, observed_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date, country) DO UPDATE SET
                    snapshot_id = excluded.snapshot_id,
                    observed_at = excluded.observed_at,
                    created_at = excluded.created_at
                """,
                (date_str, country_norm, snapshot_id, observed_at, now),
            )

    def get_canonical_snapshot(
        self, date_str: str, country: str
    ) -> dict[str, Any] | None:
        country_norm = country.lower()
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT date, country, snapshot_id, observed_at, created_at
                FROM daily_canonical_snapshots
                WHERE date = ? AND country = ?
                """,
                (date_str, country_norm),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def find_latest_complete_snapshot_for_date(
        self, date_str: str, country: str
    ) -> dict[str, Any] | None:
        """Find the latest complete snapshot observed on date_str (UTC YYYY-MM-DD) for country."""
        country_norm = country.lower()
        day_start = f"{date_str}T00:00:00Z"
        day_end = f"{date_str}T23:59:59.999999Z"
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT snapshots.id, snapshots.observed_at
                FROM snapshots
                JOIN market_runs ON market_runs.id = snapshots.market_run_id
                JOIN charts ON charts.id = market_runs.chart_id
                WHERE charts.country = ? AND snapshots.quality = 'complete'
                  AND snapshots.observed_at >= ? AND snapshots.observed_at <= ?
                ORDER BY snapshots.observed_at DESC, snapshots.id DESC
                LIMIT 1
                """,
                (country_norm, day_start, day_end),
            ).fetchone()
            if row is None:
                return None
            return {"id": str(row["id"]), "observed_at": row["observed_at"]}

    def save_daily_analytics(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        now = _utc_text(datetime.now(UTC))
        with self._write_connection() as connection:
            for rec in records:
                rec_id = rec.get("id") or _uuid()
                signal_reasons = rec.get("signal_reasons")
                if isinstance(signal_reasons, (list, dict)):
                    signal_reasons = json.dumps(signal_reasons, ensure_ascii=False)
                elif signal_reasons is None and "signal_reasons_json" in rec:
                    signal_reasons = rec["signal_reasons_json"]

                cross_markets = rec.get("cross_markets")
                if isinstance(cross_markets, (list, dict)):
                    cross_markets = json.dumps(cross_markets, ensure_ascii=False)
                elif cross_markets is None and "cross_markets_json" in rec:
                    cross_markets = rec["cross_markets_json"]

                created_at = rec.get("created_at") or now

                connection.execute(
                    """
                    INSERT INTO daily_rank_analytics (
                        id, date, country, app_id, current_rank,
                        rank_1d_ago, delta_1d,
                        rank_3d_ago, delta_3d,
                        rank_7d_ago, delta_7d,
                        signal, signal_reasons_json,
                        subgenre, mechanic, mechanic_evidence, mechanic_confidence,
                        cross_market_count, cross_markets_json,
                        grossing_rank, free_rank, monetization_model, monetization_efficiency_flag,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date, country, app_id) DO UPDATE SET
                        current_rank = excluded.current_rank,
                        rank_1d_ago = excluded.rank_1d_ago,
                        delta_1d = excluded.delta_1d,
                        rank_3d_ago = excluded.rank_3d_ago,
                        delta_3d = excluded.delta_3d,
                        rank_7d_ago = excluded.rank_7d_ago,
                        delta_7d = excluded.delta_7d,
                        signal = excluded.signal,
                        signal_reasons_json = excluded.signal_reasons_json,
                        subgenre = excluded.subgenre,
                        mechanic = excluded.mechanic,
                        mechanic_evidence = excluded.mechanic_evidence,
                        mechanic_confidence = excluded.mechanic_confidence,
                        cross_market_count = excluded.cross_market_count,
                        cross_markets_json = excluded.cross_markets_json,
                        grossing_rank = excluded.grossing_rank,
                        free_rank = excluded.free_rank,
                        monetization_model = excluded.monetization_model,
                        monetization_efficiency_flag = excluded.monetization_efficiency_flag,
                        created_at = excluded.created_at
                    """,
                    (
                        rec_id,
                        rec["date"],
                        rec["country"].lower(),
                        str(rec["app_id"]),
                        rec["current_rank"],
                        rec.get("rank_1d_ago"),
                        rec.get("delta_1d"),
                        rec.get("rank_3d_ago"),
                        rec.get("delta_3d"),
                        rec.get("rank_7d_ago"),
                        rec.get("delta_7d"),
                        rec.get("signal", "STEADY"),
                        signal_reasons,
                        rec.get("subgenre"),
                        rec.get("mechanic"),
                        rec.get("mechanic_evidence"),
                        rec.get("mechanic_confidence", "unknown"),
                        rec.get("cross_market_count", 1),
                        cross_markets,
                        rec.get("grossing_rank"),
                        rec.get("free_rank"),
                        rec.get("monetization_model"),
                        rec.get("monetization_efficiency_flag"),
                        created_at,
                    ),
                )

    def get_daily_analytics(
        self, date_str: str, country: str, signal: str | None = None
    ) -> list[dict[str, Any]]:
        country_norm = country.lower()
        query = """
            SELECT id, date, country, app_id, current_rank,
                   rank_1d_ago, delta_1d,
                   rank_3d_ago, delta_3d,
                   rank_7d_ago, delta_7d,
                   signal, signal_reasons_json,
                   subgenre, mechanic, mechanic_evidence, mechanic_confidence,
                   cross_market_count, cross_markets_json,
                   grossing_rank, free_rank, monetization_model, monetization_efficiency_flag,
                   created_at
            FROM daily_rank_analytics
            WHERE date = ? AND country = ?
        """
        params: list[Any] = [date_str, country_norm]
        if signal:
            query += " AND signal = ?"
            params.append(signal)
        query += " ORDER BY current_rank ASC"

        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["signal_reasons"] = (
                json.loads(d["signal_reasons_json"])
                if d["signal_reasons_json"]
                else []
            )
            d["cross_markets"] = (
                json.loads(d["cross_markets_json"])
                if d["cross_markets_json"]
                else []
            )
            results.append(d)
        return results

    def get_app_rank_history(
        self, app_id: str, country: str, limit: int = 14
    ) -> list[dict[str, Any]]:
        country_norm = country.lower()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT date, country, app_id, current_rank,
                       rank_1d_ago, delta_1d,
                       rank_3d_ago, delta_3d,
                       rank_7d_ago, delta_7d,
                       signal, subgenre, mechanic, mechanic_confidence,
                       cross_market_count
                FROM daily_rank_analytics
                WHERE app_id = ? AND country = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (str(app_id), country_norm, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_shortlist_item(self, item: dict[str, Any]) -> None:
        now = _utc_text(datetime.now(UTC))
        tags_json = json.dumps(item.get("tags") or [], ensure_ascii=False)
        with self._write_connection() as connection:
            connection.execute(
                """
                INSERT INTO shortlists (
                    id, app_id, title, icon_url, developer, subgenre, mechanic,
                    primary_country, rank_at_bookmark, opportunity_score,
                    status, priority, notes, tags, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id) DO UPDATE SET
                    title = excluded.title,
                    icon_url = excluded.icon_url,
                    developer = excluded.developer,
                    subgenre = excluded.subgenre,
                    mechanic = excluded.mechanic,
                    rank_at_bookmark = excluded.rank_at_bookmark,
                    opportunity_score = excluded.opportunity_score,
                    updated_at = excluded.updated_at
                """,
                (
                    item.get("id") or _uuid(),
                    str(item["app_id"]),
                    item["title"],
                    item.get("icon_url"),
                    item.get("developer"),
                    item.get("subgenre"),
                    item.get("mechanic"),
                    item["primary_country"].lower(),
                    int(item["rank_at_bookmark"]),
                    item.get("opportunity_score"),
                    item.get("status", "CONSIDERING"),
                    item.get("priority", "MEDIUM"),
                    item.get("notes"),
                    tags_json,
                    item.get("created_at") or now,
                    item.get("updated_at") or now,
                ),
            )

    def get_shortlist_items(
        self, status: str | None = None, priority: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM shortlists WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        query += " ORDER BY updated_at DESC"

        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
            results.append(d)
        return results

    def get_shortlist_item_by_app_id(self, app_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM shortlists WHERE app_id = ?", (str(app_id),)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
            return d

    def update_shortlist_item(self, app_id: str, updates: dict[str, Any]) -> bool:
        allowed = {"status", "priority", "notes", "tags", "updated_at"}
        valid_updates = {k: v for k, v in updates.items() if k in allowed}
        if not valid_updates:
            return False

        set_clauses = []
        params: list[Any] = []
        for k, v in valid_updates.items():
            set_clauses.append(f"{k} = ?")
            if k == "tags" and isinstance(v, list):
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                params.append(v)
        params.append(str(app_id))

        with self._write_connection() as connection:
            cursor = connection.execute(
                f"UPDATE shortlists SET {', '.join(set_clauses)} WHERE app_id = ?",
                params,
            )
            return cursor.rowcount > 0

    def delete_shortlist_item(self, app_id: str) -> bool:
        with self._write_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM shortlists WHERE app_id = ?", (str(app_id),)
            )
            return cursor.rowcount > 0

    def get_available_analytics_dates(self) -> list[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT date FROM daily_rank_analytics ORDER BY date DESC"
            ).fetchall()
            return [r["date"] for r in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _ensure_chart(
        self, connection: sqlite3.Connection, chart: Chart, endpoint: str
    ) -> str:
        country = chart.country.lower()
        existing = connection.execute(
            """
            SELECT id FROM charts
            WHERE provider = ? AND platform = ? AND country = ? AND collection = ?
              AND genre = ? AND depth = ? AND version = ?
            """,
            (
                chart.provider,
                chart.platform,
                country,
                chart.collection,
                chart.genre,
                chart.depth,
                chart.version,
            ),
        ).fetchone()
        if existing is not None:
            return str(existing["id"])
        market = connection.execute(
            "SELECT 1 FROM markets WHERE country = ?", (country,)
        ).fetchone()
        if market is None:
            raise ValueError(f"unknown market: {country}")
        chart_id = _uuid()
        connection.execute(
            """
            INSERT INTO charts
                (id, provider, platform, country, collection, genre, depth,
                 version, endpoint, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chart_id,
                chart.provider,
                chart.platform,
                country,
                chart.collection,
                chart.genre,
                chart.depth,
                chart.version,
                endpoint,
                _utc_text(datetime.now(UTC)),
            ),
        )
        return chart_id

    def _ensure_market_run(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        chart_id: str,
        started_at: datetime,
    ) -> str:
        existing = connection.execute(
            "SELECT id FROM market_runs WHERE run_id = ? AND chart_id = ?",
            (run_id, chart_id),
        ).fetchone()
        if existing is not None:
            return str(existing["id"])
        market_run_id = _uuid()
        connection.execute(
            """
            INSERT INTO market_runs
                (id, run_id, chart_id, chart_status, enrichment_status, started_at)
            VALUES (?, ?, ?, 'pending', 'pending', ?)
            """,
            (market_run_id, run_id, chart_id, _utc_text(started_at)),
        )
        return market_run_id

    def _ensure_app(
        self,
        connection: sqlite3.Connection,
        provider: str,
        platform: str,
        app_id: str,
        created_at: datetime,
    ) -> str:
        if not isinstance(app_id, str) or not app_id:
            raise ValueError("app IDs must be non-empty text")
        existing = connection.execute(
            """
            SELECT id FROM apps
            WHERE provider = ? AND platform = ? AND source_app_id = ?
            """,
            (provider, platform, app_id),
        ).fetchone()
        if existing is not None:
            return str(existing["id"])
        app_ref = _uuid()
        connection.execute(
            """
            INSERT INTO apps (id, provider, platform, source_app_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (app_ref, provider, platform, app_id, _utc_text(created_at)),
        )
        return app_ref

    def _persist_result_bodies(
        self, result: HttpResult
    ) -> tuple[list[tuple[HttpResult, str | None, Path | None]], str]:
        records: list[tuple[HttpResult, str | None, Path | None]] = []
        final_hash: str | None = None
        attempts = result.attempts or (result,)
        for attempt in attempts:
            digest: str | None = None
            path: Path | None = None
            if attempt.body is not None:
                digest, path = self._raw.put(attempt.body)
            records.append((attempt, digest, path))
            if attempt.body == result.body:
                final_hash = digest
        if final_hash is None and result.body is not None:
            final_hash, final_path = self._raw.put(result.body)
            records.append((result, final_hash, final_path))
        if final_hash is None:
            raise ValueError("response body is required")
        return records, final_hash

    def _insert_raw_records(
        self,
        connection: sqlite3.Connection,
        records: list[tuple[HttpResult, str | None, Path | None]],
    ) -> None:
        for attempt, digest, path in records:
            if digest is None or path is None:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO raw_responses
                    (hash, path, endpoint, status, received_at, headers_json,
                     error, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    digest,
                    path.relative_to(self.data_dir).as_posix(),
                    attempt.url,
                    attempt.status,
                    _utc_text(
                        attempt.started_at
                        + timedelta(milliseconds=attempt.elapsed_ms)
                    ),
                    json.dumps(attempt.headers, ensure_ascii=False, sort_keys=True),
                    attempt.error,
                    len(attempt.body or b""),
                ),
            )

    def _insert_observations(
        self,
        connection: sqlite3.Connection,
        result: HttpResult,
        records: list[tuple[HttpResult, str | None, Path | None]],
        run_id: str | None,
        market_run_id: str | None,
    ) -> None:
        for retry_index, (attempt, digest, _path) in enumerate(records, start=1):
            source_timestamp = (
                attempt.headers.get("last-modified")
                or attempt.headers.get("Last-Modified")
            )
            connection.execute(
                """
                INSERT INTO request_observations
                    (id, run_id, market_run_id, endpoint, started_at, elapsed_ms,
                     status, error, retry_index, response_bytes, source_timestamp,
                     raw_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _uuid(),
                    run_id,
                    market_run_id,
                    attempt.url,
                    _utc_text(attempt.started_at),
                    attempt.elapsed_ms,
                    attempt.status,
                    attempt.error,
                    retry_index,
                    len(attempt.body or b""),
                    source_timestamp,
                    digest,
                ),
            )
