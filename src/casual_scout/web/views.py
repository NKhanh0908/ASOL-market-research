from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from casual_scout.analysis.monetization import classify_monetization_model
from casual_scout.analysis.taxonomy import classify_app
from casual_scout.config import IOS_COLLECTION_COUNTRIES
from casual_scout.models import Chart
from casual_scout.stats.aggregator import (
    build_market_heatmap,
    compute_7day_subgenre_trends,
    compute_genre_distribution,
    compute_mechanic_distribution,
)
from casual_scout.stats.noteworthy import noteworthy_for_date, observed_charts, presence
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
) -> dict:
    country = country.lower()
    feed_type_norm = (
        "top-grossing"
        if feed_type in ("top-grossing", "topgrossingapplications", "grossing")
        else "top-free"
    )
    collection = "topgrossingapplications" if feed_type_norm == "top-grossing" else "topfreeapplications"
    markets = get_markets(repo)
    current_market = next((m for m in markets if m["country"] == country), None)
    if current_market is None:
        country = "vn"
        current_market = next((m for m in markets if m["country"] == "vn"), None)

    chart = Chart(country, feed_type=feed_type_norm)

    with closing(repo._connect()) as conn:
        snaps = conn.execute(
            """
            SELECT s.id, s.observed_at, s.quality, mr.chart_status
            FROM snapshots s
            JOIN market_runs mr ON mr.id = s.market_run_id
            JOIN charts c ON c.id = mr.chart_id
            WHERE c.country = ? AND c.collection = ?
            ORDER BY s.observed_at DESC
            LIMIT 50
            """,
            (country, collection),
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
            selected_snapshot = None

    if selected_snapshot is None and snapshots_list:
        latest = repo.latest_complete(chart)
        if latest is not None:
            selected_snapshot = latest
        elif snapshots_list:
            selected_snapshot = repo.get_snapshot(snapshots_list[0]["id"])

    entries_data = []
    counts = {
        "all": 0,
        "fast_risers": 0,
        "new_entries": 0,
        "falling": 0,
        "steady": 0,
    }

    if selected_snapshot is not None:
        selected_snapshot["observed_at_vn"] = format_vn_time(
            selected_snapshot.get("observed_at")
        )
        snap_id = selected_snapshot["id"]

        with closing(repo._connect()) as conn:
            query = """
                SELECT e.rank, e.app_id, e.name, e.store_url, e.icon_url, e.developer, e.source_genres_json,
                       mv.description, mv.genres_json, mv.average_rating, mv.rating_count,
                       mv.price, mv.currency, mv.in_app_purchases_json, mv.has_in_app_purchases,
                       dra.delta_1d, dra.delta_3d, dra.delta_7d,
                       dra.signal, dra.signal_reasons_json,
                       dra.subgenre, dra.mechanic, dra.mechanic_evidence, dra.mechanic_confidence,
                       dra.cross_market_count, dra.cross_markets_json,
                       dra.grossing_rank, dra.free_rank, dra.monetization_model, dra.monetization_efficiency_flag
                FROM entries e
                LEFT JOIN snapshot_metadata sm ON sm.snapshot_id = e.snapshot_id AND sm.app_id = e.app_id
                LEFT JOIN metadata_versions mv ON mv.id = sm.metadata_version_id
                LEFT JOIN daily_rank_analytics dra ON dra.app_id = e.app_id AND dra.country = ?
                     AND dra.date = (SELECT date FROM daily_canonical_snapshots WHERE snapshot_id = ?)
                WHERE e.snapshot_id = ?
                ORDER BY e.rank ASC
            """
            params = [country, snap_id, snap_id]
            rows = conn.execute(query, params).fetchall()

            for r in rows:
                row_dict = dict(r)

                # Fallback on the fly classification if analytics hasn't run yet
                if not row_dict.get("subgenre") or not row_dict.get("mechanic"):
                    genres: list[str] = []
                    if row_dict.get("genres_json"):
                        try:
                            genres = json.loads(row_dict["genres_json"])
                        except Exception:
                            pass
                    if not genres and row_dict.get("source_genres_json"):
                        try:
                            genres = json.loads(row_dict["source_genres_json"])
                        except Exception:
                            pass

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
                if not row_dict.get("monetization_model") or row_dict.get("monetization_model") == "UNKNOWN":
                    iap_list = []
                    if row_dict.get("in_app_purchases_json"):
                        try:
                            iap_list = json.loads(row_dict["in_app_purchases_json"])
                        except Exception:
                            pass
                    free_r = row_dict.get("free_rank") or (row_dict.get("rank") if feed_type_norm == "top-free" else None)
                    gross_r = row_dict.get("grossing_rank") or (row_dict.get("rank") if feed_type_norm == "top-grossing" else None)
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
                    except Exception:
                        row_dict["signal_reasons"] = []
                else:
                    row_dict["signal_reasons"] = []

                if row_dict.get("cross_markets_json"):
                    try:
                        parsed_cm = json.loads(row_dict["cross_markets_json"])
                        row_dict["cross_markets"] = [str(m).upper() for m in parsed_cm if m] if parsed_cm else [country.upper()]
                    except Exception:
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

    available_dates = repo.get_available_analytics_dates()
    if selected_snapshot:
        observation_day = selected_snapshot["observed_at"][:10]
        charts = observed_charts(repo, observation_day, collection)
        for entry in entries_data:
            entry.update(presence(entry["app_id"], charts))
            entry["cross_market_count"] = entry["presence_count"]
            entry["cross_markets"] = entry["presence_markets"]

    return {
        "country": country,
        "feed_type": feed_type_norm,
        "current_market": current_market,
        "markets": [m for m in markets if m['country'] in IOS_COLLECTION_COUNTRIES],
        "legacy_market": current_market if country not in IOS_COLLECTION_COUNTRIES else None,
        "snapshots": snapshots_list,
        "selected_snapshot": selected_snapshot,
        "entries": entries_data,
        "selected_signal": signal,
        "selected_date": date,
        "available_dates": available_dates,
        "counts": counts,
    }


def get_game_view(repo: Repository, app_id: str, country: str = 'vn', snapshot_id: str | None = None) -> dict:
    country = country.lower()
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

        if meta_row is None:
            meta_row = conn.execute(
                """
                SELECT * FROM metadata_versions
                WHERE provider = 'apple' AND platform = 'ios' AND country = ? AND app_id = ?
                ORDER BY fetched_at DESC LIMIT 1
                """,
                (country, app_id),
            ).fetchone()

        if meta_row is None:
            meta_row = conn.execute(
                """
                SELECT * FROM metadata_versions
                WHERE provider = 'apple' AND platform = 'ios' AND app_id = ?
                ORDER BY fetched_at DESC LIMIT 1
                """,
                (app_id,),
            ).fetchone()

        entry_row = None
        if snapshot_id:
            entry_row = conn.execute(
                "SELECT * FROM entries WHERE snapshot_id = ? AND app_id = ?",
                (snapshot_id, app_id),
            ).fetchone()

        if entry_row is None:
            entry_row = conn.execute(
                """
                SELECT e.* FROM entries e
                JOIN snapshots s ON s.id = e.snapshot_id
                JOIN market_runs mr ON mr.id = s.market_run_id
                JOIN charts c ON c.id = mr.chart_id
                WHERE e.app_id = ? AND c.country = ?
                ORDER BY s.observed_at DESC LIMIT 1
                """,
                (app_id, country),
            ).fetchone()

        if entry_row is None:
            entry_row = conn.execute(
                "SELECT * FROM entries WHERE app_id = ? ORDER BY rowid DESC LIMIT 1",
                (app_id,),
            ).fetchone()

        meta_dict = dict(meta_row) if meta_row else {}
        if meta_dict.get("fetched_at"):
            meta_dict["fetched_at_vn"] = format_vn_time(meta_dict["fetched_at"])
        if meta_dict.get("genres_json"):
            try:
                meta_dict["genres"] = json.loads(meta_dict["genres_json"])
            except Exception:
                meta_dict["genres"] = []
        else:
            meta_dict["genres"] = []

        rank_history = repo.get_app_rank_history(app_id, country, limit=14)

        latest_analytics = None
        if rank_history:
            an_row = conn.execute(
                """
                SELECT * FROM daily_rank_analytics
                WHERE app_id = ? AND country = ?
                ORDER BY date DESC LIMIT 1
                """,
                (app_id, country),
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
                except Exception:
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
        observation = conn.execute(
            """SELECT s.observed_at, c.collection FROM snapshots s
            JOIN market_runs mr ON mr.id=s.market_run_id
            JOIN charts c ON c.id=mr.chart_id WHERE s.id=?""",
            (entry_row["snapshot_id"] if entry_row else None,),
        ).fetchone()
        charts = observed_charts(repo, observation["observed_at"][:10], observation["collection"]) if observation else {}
        latest_analytics.update(presence(app_id, charts))
        latest_analytics["cross_market_count"] = latest_analytics["presence_count"]
        latest_analytics["cross_markets"] = latest_analytics["presence_markets"]
        latest_analytics["presence_day"] = observation["observed_at"][:10] if observation else None

        return {
            "app_id": app_id,
            "country": country,
            "snapshot_id": snapshot_id,
            "entry": dict(entry_row) if entry_row else {},
            "metadata": meta_dict,
            "rank_history": rank_history,
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
            SELECT mr.*, c.country, m.name as market_name, m.name as country_name, s.id as snapshot_id, s.quality
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
) -> dict[str, Any]:
    available_dates = repo.get_available_analytics_dates()
    if not date_str:
        date_str = available_dates[0] if available_dates else datetime.now(UTC).strftime("%Y-%m-%d")

    all_markets = get_markets(repo)
    markets = [m for m in all_markets if m['country'] in IOS_COLLECTION_COUNTRIES]
    country = country.lower()
    legacy_market = next((m for m in all_markets
                          if m['country'] == country and country not in IOS_COLLECTION_COUNTRIES), None)
    scope = IOS_COLLECTION_COUNTRIES if country == 'all' else (country,)
    scope_params = ','.join('?' for _ in scope)
    shortlist_service = ShortlistService(repo)
    shortlist_items = shortlist_service.list_shortlists()
    shortlisted_ids = {it["app_id"] for it in shortlist_items}

    with closing(repo._connect()) as conn:
        if country.lower() == "all":
            rows = conn.execute(
                f"""
                SELECT dra.*,
                       COALESCE(
                           (SELECT name FROM metadata_versions mv WHERE mv.app_id = dra.app_id AND mv.country = dra.country ORDER BY fetched_at DESC LIMIT 1),
                           (SELECT name FROM entries e WHERE e.app_id = dra.app_id LIMIT 1),
                           dra.app_id
                       ) AS title,
                       COALESCE(
                           (SELECT developer FROM metadata_versions mv WHERE mv.app_id = dra.app_id AND mv.country = dra.country ORDER BY fetched_at DESC LIMIT 1),
                           ''
                       ) AS developer,
                       (SELECT icon_url FROM entries e WHERE e.app_id = dra.app_id LIMIT 1) AS icon_url
                FROM daily_rank_analytics dra
                WHERE dra.date = ? AND dra.country IN ({scope_params})
                ORDER BY dra.current_rank ASC
                """,
                (date_str, *scope),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT dra.*,
                       COALESCE(
                           (SELECT name FROM metadata_versions mv WHERE mv.app_id = dra.app_id AND mv.country = dra.country ORDER BY fetched_at DESC LIMIT 1),
                           (SELECT name FROM entries e WHERE e.app_id = dra.app_id LIMIT 1),
                           dra.app_id
                       ) AS title,
                       COALESCE(
                           (SELECT developer FROM metadata_versions mv WHERE mv.app_id = dra.app_id AND mv.country = dra.country ORDER BY fetched_at DESC LIMIT 1),
                           ''
                       ) AS developer,
                       (SELECT icon_url FROM entries e WHERE e.app_id = dra.app_id LIMIT 1) AS icon_url
                FROM daily_rank_analytics dra
                WHERE dra.date = ? AND dra.country = ?
                ORDER BY dra.current_rank ASC
                """,
                (date_str, country.lower()),
            ).fetchall()

        records = []
        records_by_country: dict[str, list[dict]] = {}
        for r in rows:
            d = dict(r)
            d["signal_reasons"] = json.loads(d["signal_reasons_json"]) if d.get("signal_reasons_json") else []
            d["cross_markets"] = json.loads(d["cross_markets_json"]) if d.get("cross_markets_json") else []
            records.append(d)
            c = d["country"]
            if c not in records_by_country:
                records_by_country[c] = []
            records_by_country[c].append(d)

        hist_rows = conn.execute(
            f"""
            SELECT date, subgenre
            FROM daily_rank_analytics
            WHERE date <= ? AND country IN ({scope_params})
            ORDER BY date DESC
            LIMIT 7700
            """,
            (date_str, *scope),
        ).fetchall()
        history_records = [dict(hr) for hr in hist_rows]
        latest_collection = conn.execute(
            """
            SELECT r.id, r.status, r.started_at, r.ended_at, SUM(mr.valid_count) AS valid_count
            FROM runs r
            JOIN market_runs mr ON mr.run_id = r.id
            JOIN charts c ON c.id = mr.chart_id
            WHERE c.country = 'vn'
            GROUP BY r.id
            ORDER BY r.started_at DESC
            LIMIT 1
            """
        ).fetchone()

    genre_dist = compute_genre_distribution(records)
    mech_dist = compute_mechanic_distribution(records)
    heatmap = build_market_heatmap(records_by_country)
    trends = compute_7day_subgenre_trends(history_records)
    radar_items = noteworthy_for_date(
        repo, records, date_str, shortlisted_ids,
        markets=(*IOS_COLLECTION_COUNTRIES, country) if legacy_market else IOS_COLLECTION_COUNTRIES,
    )

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
            "valid_count": int(latest_collection["valid_count"] or 0)
            if latest_collection
            else 0,
        },
    }


def get_shortlist_view(repo: Repository, status: str | None = None, priority: str | None = None) -> dict[str, Any]:
    service = ShortlistService(repo)
    items = service.list_shortlists(status=status, priority=priority)
    return {
        "items": items,
        "filter_status": status,
        "filter_priority": priority,
    }
