from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from datetime import date as calendar_date
from typing import Any
from zoneinfo import ZoneInfo

from casual_scout.analysis.monetization import (
    classify_android_monetization,
    classify_monetization_model,
)
from casual_scout.analysis.taxonomy import classify_app
from casual_scout.config import IOS_COLLECTION_COUNTRIES
from casual_scout.stats.aggregator import (
    build_market_heatmap,
    compute_7day_subgenre_trends,
    compute_genre_distribution,
    compute_mechanic_distribution,
)
from casual_scout.stats.noteworthy import noteworthy_for_date, observed_charts, presence
from casual_scout.stats.radar import rank_opportunities
from casual_scout.stats.shortlist import ShortlistService
from casual_scout.storage import Repository

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def format_vn_time(utc_iso: str | None) -> str:
    if not utc_iso:
        return "—"
    try:
        dt = datetime.fromisoformat(utc_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        vn_dt = dt.astimezone(_VN_TZ)
        return vn_dt.strftime("%Y-%m-%d %H:%M:%S (UTC+7)")
    except (ValueError, TypeError, OSError):
        return utc_iso


def get_markets(repo: Repository) -> list[dict]:
    with closing(repo._connect()) as conn:
        rows = conn.execute(
            "SELECT country, name, market_group, source_status, source_note FROM markets ORDER BY country ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_data_view(
    repo: Repository,
    country: str = "vn",
    feed_type: str = "top-free",
    snapshot_id: str | None = None,
    signal: str | None = None,
    date: str | None = None,
    *,
    platform: str = "ios",
) -> dict:
    if platform not in ("ios", "android"):
        raise ValueError("unsupported platform")
    if date:
        calendar_date.fromisoformat(date)
    country = country.lower()
    feed_type_norm = (
        "top-grossing"
        if feed_type in ("top-grossing", "topgrossingapplications", "grossing")
        else "top-free"
    )
    if platform == "android":
        collection = feed_type_norm
    else:
        collection = (
            "topgrossingapplications" if feed_type_norm == "top-grossing" else "topfreeapplications"
        )

    markets = get_markets(repo)
    current_market = next((m for m in markets if m["country"] == country), None)
    if current_market is None:
        country = "vn"
        current_market = next((m for m in markets if m["country"] == "vn"), None)

    with closing(repo._connect()) as conn:
        snaps = conn.execute(
            """
            SELECT s.id, s.observed_at, s.quality, mr.chart_status
            FROM snapshots s
            JOIN market_runs mr ON mr.id = s.market_run_id
            JOIN charts c ON c.id = mr.chart_id
            WHERE c.country = ? AND c.platform = ? AND c.collection = ?
              AND (? IS NULL OR substr(s.observed_at,1,10) = ?)
            ORDER BY s.observed_at DESC
            LIMIT 50
            """,
            (country, platform, collection, date, date),
        ).fetchall()
        snapshots_list = [
            {
                "id": str(r["id"]),
                "observed_at": str(r["observed_at"]),
                "observed_at_vn": format_vn_time(str(r["observed_at"])),
                "quality": str(r["quality"]),
            }
            for r in snaps
        ]

    selected_snapshot = None
    if snapshot_id:
        try:
            selected_snapshot = repo.get_snapshot(snapshot_id)
        except (KeyError, ValueError):
            raise KeyError(snapshot_id) from None
        identity = selected_snapshot["chart"]
        if (identity["platform"], identity["country"], identity["collection"]) != (
            platform,
            country,
            collection,
        ):
            raise ValueError("snapshot does not match selected platform, market and feed")

    if selected_snapshot is None and snapshots_list:
        eligible = [s for s in snapshots_list if not date or s["observed_at"][:10] == date]
        if eligible:
            preferred = next((s for s in eligible if s["quality"] == "complete"), eligible[0])
            selected_snapshot = repo.get_snapshot(preferred["id"])

    entries_data = []
    counts = {
        "all": 0,
        "fast_risers": 0,
        "new_entries": 0,
        "falling": 0,
        "steady": 0,
    }

    if selected_snapshot is not None:
        selected_snapshot["observed_at_vn"] = format_vn_time(selected_snapshot.get("observed_at"))
        snap_id = selected_snapshot["id"]

        with closing(repo._connect()) as conn:
            query = """
                SELECT e.rank, e.app_id, e.name, e.store_url, e.icon_url, e.developer, e.source_genres_json,
                       mv.description, mv.genres_json, mv.average_rating, mv.rating_count,
                       mv.price, mv.currency, mv.in_app_purchases_json, mv.has_in_app_purchases,
                       mv.installs, mv.min_installs, mv.has_ads, mv.has_iap,
                       dra.delta_1d, dra.delta_3d, dra.delta_7d,
                       dra.signal, dra.signal_reasons_json,
                       dra.subgenre, dra.mechanic, dra.mechanic_evidence, dra.mechanic_confidence,
                       dra.cross_market_count, dra.cross_markets_json,
                       dra.grossing_rank, dra.free_rank, dra.monetization_model, dra.monetization_efficiency_flag
                FROM entries e
                LEFT JOIN snapshot_metadata sm ON sm.snapshot_id = e.snapshot_id AND sm.app_id = e.app_id
                LEFT JOIN metadata_versions mv ON mv.id = sm.metadata_version_id
                LEFT JOIN daily_rank_analytics dra ON dra.app_id = e.app_id AND dra.country = ? AND dra.platform = ?
                     AND dra.date = ?
                WHERE e.snapshot_id = ?
                ORDER BY e.rank ASC
            """
            params = [country, platform, selected_snapshot["observed_at"][:10], snap_id]
            rows = conn.execute(query, params).fetchall()

            for r in rows:
                row_dict = dict(r)

                # Fallback on the fly classification if analytics hasn't run yet
                if not row_dict.get("subgenre") or not row_dict.get("mechanic"):
                    genres: list[str] = []
                    if row_dict.get("genres_json"):
                        try:
                            genres = json.loads(row_dict["genres_json"])
                        except (json.JSONDecodeError, TypeError):
                            genres = []
                    if not genres and row_dict.get("source_genres_json"):
                        try:
                            genres = json.loads(row_dict["source_genres_json"])
                        except (json.JSONDecodeError, TypeError):
                            genres = []

                    classified = classify_app(
                        genres,
                        row_dict.get("name") or "",
                        row_dict.get("description") or "",
                    )
                    if not row_dict.get("subgenre"):
                        row_dict["subgenre"] = classified["subgenre"]
                    if not row_dict.get("mechanic"):
                        row_dict["mechanic"] = classified["mechanic"]
                        row_dict["mechanic_confidence"] = classified["confidence"]
                        row_dict["mechanic_evidence"] = classified["evidence"]

                if not row_dict.get("mechanic_confidence"):
                    row_dict["mechanic_confidence"] = "low"

                if row_dict.get("cross_market_count") is None:
                    row_dict["cross_market_count"] = 1
                    row_dict["cross_markets"] = [country]

                # Monetization model fallback
                if (
                    not row_dict.get("monetization_model")
                    or row_dict.get("monetization_model") == "UNKNOWN"
                ):
                    iap_list = []
                    if row_dict.get("in_app_purchases_json"):
                        try:
                            iap_list = json.loads(row_dict["in_app_purchases_json"])
                        except (json.JSONDecodeError, TypeError):
                            iap_list = []
                    free_r = row_dict.get("free_rank") or (
                        row_dict.get("rank") if feed_type_norm == "top-free" else None
                    )
                    gross_r = row_dict.get("grossing_rank") or (
                        row_dict.get("rank") if feed_type_norm == "top-grossing" else None
                    )
                    if platform == "android":
                        has_ads = (
                            bool(row_dict.get("has_ads"))
                            if row_dict.get("has_ads") is not None
                            else None
                        )
                        has_iap = (
                            bool(row_dict.get("has_iap"))
                            if row_dict.get("has_iap") is not None
                            else None
                        )
                        row_dict["monetization_model"] = classify_android_monetization(
                            price=row_dict.get("price"),
                            has_ads=has_ads,
                            has_iap=has_iap,
                            grossing_rank=gross_r,
                        )
                    else:
                        row_dict["monetization_model"] = classify_monetization_model(
                            price=row_dict.get("price"),
                            iap_list=iap_list,
                            free_rank=free_r,
                            grossing_rank=gross_r,
                        )

                sig = row_dict.get("signal") or "STEADY"
                row_dict["signal"] = sig
                counts["all"] += 1
                if sig == "FAST_RISER":
                    counts["fast_risers"] += 1
                elif sig == "NEW_ENTRY":
                    counts["new_entries"] += 1
                elif sig == "FALLING":
                    counts["falling"] += 1
                elif sig == "STEADY":
                    counts["steady"] += 1

                if signal:
                    sig_filter = signal.upper()
                    if sig_filter == "FAST_RISERS" and sig != "FAST_RISER":
                        continue
                    if sig_filter == "NEW_ENTRIES" and sig != "NEW_ENTRY":
                        continue
                    if sig_filter == "FALLING" and sig != "FALLING":
                        continue
                    if sig_filter == "STEADY" and sig != "STEADY":
                        continue

                if row_dict.get("signal_reasons_json"):
                    try:
                        row_dict["signal_reasons"] = json.loads(row_dict["signal_reasons_json"])
                    except (json.JSONDecodeError, TypeError):
                        row_dict["signal_reasons"] = []
                else:
                    row_dict["signal_reasons"] = []

                if row_dict.get("cross_markets_json"):
                    try:
                        parsed_cm = json.loads(row_dict["cross_markets_json"])
                        row_dict["cross_markets"] = (
                            [str(m).upper() for m in parsed_cm if m]
                            if parsed_cm
                            else [country.upper()]
                        )
                    except (json.JSONDecodeError, TypeError):
                        row_dict["cross_markets"] = [country.upper()]
                else:
                    row_dict["cross_markets"] = [country.upper()]

                if not row_dict["cross_markets"]:
                    row_dict["cross_markets"] = [country.upper()]

                # Format rating display
                avg_r = row_dict.get("average_rating")
                r_cnt = row_dict.get("rating_count")
                if avg_r is not None:
                    cnt_part = f" ({r_cnt:,})" if r_cnt else ""
                    row_dict["rating_display"] = f"★ {avg_r:.1f}{cnt_part}"
                else:
                    row_dict["rating_display"] = "—"

                entries_data.append(row_dict)

    available_dates = repo.get_available_analytics_dates(platform=platform)
    if selected_snapshot:
        observation_day = selected_snapshot["observed_at"][:10]
        charts = observed_charts(repo, observation_day, collection, platform=platform)
        for entry in entries_data:
            entry.update(presence(entry["app_id"], charts))
            entry["cross_market_count"] = entry["presence_count"]
            entry["cross_markets"] = entry["presence_markets"]

    return {
        "country": country,
        "feed_type": feed_type_norm,
        "current_market": current_market,
        "markets": [m for m in markets if m["country"] in IOS_COLLECTION_COUNTRIES],
        "legacy_market": current_market if country not in IOS_COLLECTION_COUNTRIES else None,
        "snapshots": snapshots_list,
        "selected_snapshot": selected_snapshot,
        "entries": entries_data,
        "selected_signal": signal,
        "selected_date": date,
        "available_dates": available_dates,
        "counts": counts,
        "platform": platform,
    }


def get_game_view(
    repo: Repository,
    app_id: str,
    country: str = "vn",
    snapshot_id: str | None = None,
    *,
    platform: str | None = None,
) -> dict:
    country = country.lower()
    if not platform:
        platform = "android" if ("." in app_id and not app_id.isdigit()) else "ios"
    if platform not in ("ios", "android"):
        raise ValueError("unsupported platform")
    if snapshot_id:
        snapshot = repo.get_snapshot(snapshot_id)
        identity = snapshot["chart"]
        if (identity["platform"], identity["country"]) != (platform, country):
            raise ValueError("snapshot does not match game scope")

    with closing(repo._connect()) as conn:
        meta_row = None
        if snapshot_id:
            meta_row = conn.execute(
                """
                SELECT mv.* FROM metadata_versions mv
                JOIN snapshot_metadata sm ON sm.metadata_version_id = mv.id
                WHERE sm.snapshot_id = ? AND mv.app_id = ?
                """,
                (snapshot_id, app_id),
            ).fetchone()

        entry_row = None
        if snapshot_id:
            entry_row = conn.execute(
                "SELECT * FROM entries WHERE snapshot_id = ? AND app_id = ?",
                (snapshot_id, app_id),
            ).fetchone()

        if entry_row is None and not snapshot_id:
            entry_row = conn.execute(
                """
                SELECT e.* FROM entries e
                JOIN snapshots s ON s.id = e.snapshot_id
                JOIN market_runs mr ON mr.id = s.market_run_id
                JOIN charts c ON c.id = mr.chart_id
                WHERE e.app_id = ? AND c.country = ? AND c.platform = ?
                ORDER BY s.observed_at DESC LIMIT 1
                """,
                (app_id, country, platform),
            ).fetchone()

        if entry_row is not None and not snapshot_id:
            meta_row = conn.execute(
                """SELECT mv.* FROM snapshot_metadata sm
                JOIN metadata_versions mv ON mv.id=sm.metadata_version_id
                WHERE sm.snapshot_id=? AND sm.app_id=?""",
                (entry_row["snapshot_id"], app_id),
            ).fetchone()

        if entry_row is None and meta_row is None:
            return None
        entry_row = dict(entry_row) if entry_row else None

        meta_dict = dict(meta_row) if meta_row else {}
        if meta_dict.get("fetched_at"):
            meta_dict["fetched_at_vn"] = format_vn_time(meta_dict["fetched_at"])
        if meta_dict.get("genres_json"):
            try:
                meta_dict["genres"] = json.loads(meta_dict["genres_json"])
            except (json.JSONDecodeError, TypeError):
                meta_dict["genres"] = []
        else:
            meta_dict["genres"] = []

        observation = conn.execute(
            """SELECT s.observed_at, c.collection FROM snapshots s
            JOIN market_runs mr ON mr.id=s.market_run_id
            JOIN charts c ON c.id=mr.chart_id WHERE s.id=?""",
            (entry_row["snapshot_id"] if entry_row else snapshot_id,),
        ).fetchone()
        end_day = (
            calendar_date.fromisoformat(observation["observed_at"][:10])
            if observation
            else datetime.now(UTC).date()
        )
        first_day = end_day - timedelta(days=13)
        rank_history = [
            dict(row)
            for row in conn.execute(
                """SELECT * FROM daily_rank_analytics WHERE app_id=? AND country=? AND platform=?
               AND date BETWEEN ? AND ? ORDER BY date DESC LIMIT 14""",
                (app_id, country, platform, first_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        ]

        latest_analytics = None
        if rank_history:
            an_row = conn.execute(
                """
                SELECT * FROM daily_rank_analytics
                WHERE app_id = ? AND country = ? AND platform = ? AND date = ?
                ORDER BY date DESC LIMIT 1
                """,
                (app_id, country, platform, end_day.isoformat()),
            ).fetchone()
            if an_row:
                latest_analytics = dict(an_row)
                latest_analytics["signal_reasons"] = (
                    json.loads(latest_analytics["signal_reasons_json"])
                    if latest_analytics.get("signal_reasons_json")
                    else []
                )
                latest_analytics["cross_markets"] = (
                    json.loads(latest_analytics["cross_markets_json"])
                    if latest_analytics.get("cross_markets_json")
                    else []
                )

        if not latest_analytics:
            title = meta_dict.get("name") or (entry_row["name"] if entry_row else app_id)
            desc = meta_dict.get("description") or ""
            genres = meta_dict.get("genres") or []
            if not genres and entry_row and entry_row.get("source_genres_json"):
                try:
                    genres = json.loads(entry_row["source_genres_json"])
                except (json.JSONDecodeError, TypeError):
                    genres = []

            classified = classify_app(genres, title, desc)
            latest_analytics = {
                "subgenre": classified["subgenre"],
                "mechanic": classified["mechanic"],
                "mechanic_confidence": classified["confidence"],
                "mechanic_evidence": classified["evidence"],
                "signal": "STEADY",
                "signal_reasons": [],
            }
        charts = (
            observed_charts(
                repo, observation["observed_at"][:10], observation["collection"], platform=platform
            )
            if observation
            else {}
        )
        latest_analytics.update(presence(app_id, charts))
        latest_analytics["cross_market_count"] = latest_analytics["presence_count"]
        latest_analytics["cross_markets"] = latest_analytics["presence_markets"]
        latest_analytics["presence_day"] = observation["observed_at"][:10] if observation else None

        history_rows = conn.execute(
            """SELECT substr(s.observed_at,1,10) AS day, c.collection, e.rank
            FROM entries e JOIN snapshots s ON s.id=e.snapshot_id
            JOIN market_runs mr ON mr.id=s.market_run_id JOIN charts c ON c.id=mr.chart_id
            WHERE e.app_id=? AND c.platform=? AND c.country=?
              AND substr(s.observed_at,1,10) BETWEEN ? AND ?
              AND s.quality IN ('complete','partial')
            ORDER BY s.observed_at ASC, s.id ASC""",
            (app_id, platform, country, first_day.isoformat(), end_day.isoformat()),
        ).fetchall()
        daily_ranks = {}
        for row in history_rows:
            key = "grossing_rank" if "grossing" in row["collection"] else "free_rank"
            daily_ranks.setdefault(row["day"], {})[key] = row["rank"]
        chart_history = [
            {
                "date": (first_day + timedelta(days=n)).isoformat(),
                "free_rank": None,
                "grossing_rank": None,
            }
            for n in range(14)
        ]
        for row in chart_history:
            row.update(daily_ranks.get(row["date"], {}))

        return {
            "app_id": app_id,
            "country": country,
            "platform": platform,
            "feed_type": "top-grossing"
            if observation and "grossing" in observation["collection"]
            else "top-free",
            "snapshot_id": snapshot_id,
            "entry": dict(entry_row) if entry_row else {},
            "metadata": meta_dict,
            "rank_history": rank_history,
            "chart_history": chart_history,
            "analytics": latest_analytics,
        }


def get_runs_view(repo: Repository, trigger: str | None = None, limit: int = 50) -> dict:
    with closing(repo._connect()) as conn:
        query = """
            SELECT r.id, r.request_key, r.trigger, r.status, r.started_at, r.ended_at,
                   r.summary_json,
                   COUNT(mr.id) as total_markets,
                   SUM(CASE WHEN mr.chart_status = 'complete' THEN 1 ELSE 0 END) as complete_markets,
                   SUM(mr.valid_count) as total_valid_entries
            FROM runs r
            LEFT JOIN market_runs mr ON mr.run_id = r.id
        """
        params = []
        if trigger:
            query += " WHERE r.trigger = ?"
            params.append(trigger)
        query += " GROUP BY r.id ORDER BY r.started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        runs_list = []
        for r in rows:
            d = dict(r)
            d["started_at_vn"] = format_vn_time(d["started_at"])
            d["ended_at_vn"] = format_vn_time(d.get("ended_at"))
            runs_list.append(d)

        return {"runs": runs_list, "filter_trigger": trigger}


def get_run_detail_view(repo: Repository, run_id: str) -> dict | None:
    with closing(repo._connect()) as conn:
        run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not run_row:
            return None
        run_dict = dict(run_row)
        run_dict["started_at_vn"] = format_vn_time(run_dict["started_at"])
        run_dict["ended_at_vn"] = format_vn_time(run_dict.get("ended_at"))

        mr_rows = conn.execute(
            """
            SELECT mr.*, c.country, c.platform, c.collection, m.name as market_name, m.name as country_name, s.id as snapshot_id, s.quality
            FROM market_runs mr
            JOIN charts c ON c.id = mr.chart_id
            JOIN markets m ON m.country = c.country
            LEFT JOIN snapshots s ON s.market_run_id = mr.id
            WHERE mr.run_id = ?
            ORDER BY c.country ASC
            """,
            (run_id,),
        ).fetchall()

        market_runs = []
        for r in mr_rows:
            mr_d = dict(r)
            mr_d["started_at_vn"] = format_vn_time(mr_d.get("started_at"))
            mr_d["ended_at_vn"] = format_vn_time(mr_d.get("ended_at"))
            market_runs.append(mr_d)

        run_dict["market_runs"] = market_runs
        return {"run": run_dict, "market_runs": market_runs}


def get_dashboard_view(
    repo: Repository,
    date_str: str | None = None,
    country: str = "all",
    *,
    platform: str = "ios",
) -> dict[str, Any]:
    available_dates = repo.get_available_analytics_dates(platform=platform)
    if not date_str:
        date_str = available_dates[0] if available_dates else datetime.now(UTC).strftime("%Y-%m-%d")

    all_markets = get_markets(repo)
    markets = [m for m in all_markets if m["country"] in IOS_COLLECTION_COUNTRIES]
    country = country.lower()
    legacy_market = next(
        (
            m
            for m in all_markets
            if m["country"] == country and country not in IOS_COLLECTION_COUNTRIES
        ),
        None,
    )
    scope = IOS_COLLECTION_COUNTRIES if country == "all" else (country,)
    scope_params = ",".join("?" for _ in scope)
    shortlist_service = ShortlistService(repo)
    shortlist_items = shortlist_service.list_shortlists()
    shortlisted_ids = {it["app_id"] for it in shortlist_items}

    with closing(repo._connect()) as conn:
        rows = conn.execute(
            f"""
            SELECT dra.*, COALESCE(mv.name,e.name,dra.app_id) AS title,
                   COALESCE(mv.developer,e.developer,'') AS developer, e.icon_url
            FROM daily_rank_analytics dra
            LEFT JOIN snapshots selected ON selected.id = COALESCE(
                (SELECT pcs.snapshot_id FROM platform_canonical_snapshots pcs
                 WHERE pcs.date=dra.date AND pcs.platform=dra.platform AND pcs.country=dra.country
                   AND pcs.feed_type=CASE WHEN dra.free_rank IS NULL AND dra.grossing_rank IS NOT NULL
                                         THEN 'top-grossing' ELSE 'top-free' END),
                (SELECT s.id FROM snapshots s
                 JOIN market_runs mr ON mr.id=s.market_run_id JOIN charts c ON c.id=mr.chart_id
                 JOIN entries candidate ON candidate.snapshot_id=s.id AND candidate.app_id=dra.app_id
                 WHERE c.platform=dra.platform AND c.country=dra.country
                   AND substr(s.observed_at,1,10)=dra.date AND s.quality IN ('complete','partial')
                 ORDER BY (s.quality='complete') DESC,s.observed_at DESC,s.id DESC LIMIT 1)
            )
            LEFT JOIN entries e ON e.snapshot_id=selected.id AND e.app_id=dra.app_id
            LEFT JOIN snapshot_metadata sm ON sm.snapshot_id=selected.id AND sm.app_id=dra.app_id
            LEFT JOIN metadata_versions mv ON mv.id=sm.metadata_version_id
            WHERE dra.date = ? AND dra.platform = ? AND dra.country IN ({scope_params})
            ORDER BY dra.current_rank ASC
            """,
            (date_str, platform, *scope),
        ).fetchall()

        records = []
        records_by_country: dict[str, list[dict]] = {}
        for r in rows:
            d = dict(r)
            d["signal_reasons"] = (
                json.loads(d["signal_reasons_json"]) if d.get("signal_reasons_json") else []
            )
            d["cross_markets"] = (
                json.loads(d["cross_markets_json"]) if d.get("cross_markets_json") else []
            )
            records.append(d)
            c = d["country"]
            if c not in records_by_country:
                records_by_country[c] = []
            records_by_country[c].append(d)

        hist_rows = conn.execute(
            f"""
            SELECT date, subgenre
            FROM daily_rank_analytics
            WHERE date <= ? AND platform = ? AND country IN ({scope_params})
            ORDER BY date DESC
            LIMIT 7700
            """,
            (date_str, platform, *scope),
        ).fetchall()
        history_records = [dict(hr) for hr in hist_rows]
        latest_collection = conn.execute(
            """
            SELECT r.id, r.status, r.started_at, r.ended_at, SUM(mr.valid_count) AS valid_count
            FROM runs r
            JOIN market_runs mr ON mr.run_id = r.id
            JOIN charts c ON c.id = mr.chart_id
            WHERE c.country = 'vn' AND c.platform = ?
            GROUP BY r.id
            ORDER BY r.started_at DESC
            LIMIT 1
            """,
            (platform,),
        ).fetchone()

    genre_dist = compute_genre_distribution(records)
    mech_dist = compute_mechanic_distribution(records)
    heatmap = build_market_heatmap(records_by_country)
    trends = compute_7day_subgenre_trends(history_records)
    radar_items = noteworthy_for_date(
        repo,
        records,
        date_str,
        shortlisted_ids,
        markets=(*IOS_COLLECTION_COUNTRIES, country) if legacy_market else IOS_COLLECTION_COUNTRIES,
        platform=platform,
    )
    if platform == "android":
        discovery = {row["app_id"]: row for row in radar_items}
        scored = rank_opportunities(records)
        for row in scored:
            details = discovery.get(row["app_id"], {})
            row.update(
                {
                    key: value
                    for key, value in details.items()
                    if key.startswith(
                        (
                            "presence_",
                            "observed_",
                            "noteworthy",
                            "rising_",
                            "new_entry_",
                            "comparable_",
                            "comparison_",
                        )
                    )
                }
            )
        radar_items = scored

    top_genre = None
    if genre_dist.get("breakdown"):
        top_genre = next(iter(genre_dist["breakdown"].keys()), None)

    # Compute monetization distribution
    monetization_counts: dict[str, int] = {}
    for r in records:
        model = r.get("monetization_model") or "PURE_ADS"
        monetization_counts[model] = monetization_counts.get(model, 0) + 1
    total_m = sum(monetization_counts.values()) or 1
    sorted_m = dict(sorted(monetization_counts.items(), key=lambda item: item[1], reverse=True))
    monetization_dist = {
        "breakdown": sorted_m,
        "percentages": {k: round((v / total_m) * 100, 1) for k, v in sorted_m.items()},
    }

    summary = {
        "total_games": len(records),
        "noteworthy_count": sum(r["noteworthy"] for r in radar_items),
        "fast_risers_count": sum(bool(r["rising_markets"]) for r in radar_items),
        "top_subgenre": top_genre,
        "genre_distribution": genre_dist,
        "mechanic_distribution": mech_dist,
        "monetization_distribution": monetization_dist,
    }

    return {
        "selected_date": date_str,
        "selected_country": country,
        "platform": platform,
        "legacy_market": legacy_market,
        "available_dates": available_dates or [date_str],
        "markets": markets,
        "summary": summary,
        "heatmap": heatmap,
        "trends": trends,
        "radar_items": radar_items[:50],
        "collection_status": {
            "run_id": str(latest_collection["id"]) if latest_collection else None,
            "status": str(latest_collection["status"]) if latest_collection else "not_started",
            "started_at_vn": format_vn_time(str(latest_collection["started_at"]))
            if latest_collection
            else "Chưa có lần crawl",
            "ended_at_vn": format_vn_time(str(latest_collection["ended_at"]))
            if latest_collection and latest_collection["ended_at"]
            else None,
            "valid_count": int(latest_collection["valid_count"] or 0) if latest_collection else 0,
        },
    }


def get_shortlist_view(
    repo: Repository, status: str | None = None, priority: str | None = None
) -> dict[str, Any]:
    service = ShortlistService(repo)
    items = service.list_shortlists(status=status, priority=priority)
    return {
        "items": items,
        "filter_status": status,
        "filter_priority": priority,
    }
