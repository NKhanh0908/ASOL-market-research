"""Bounded, source-linked market context for one explicit AI evaluation."""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import date, timedelta

from casual_scout.ai.contracts import EvidencePack, EvidenceRef, canonical_json
from casual_scout.stats.noteworthy import rank_noteworthy
from casual_scout.storage import Repository

_MAX_BYTES = 30_000
_MAX_CANDIDATES = 20
_MAX_MARKETS_PER_APP = 3
_MAX_DESCRIPTION = 800


def _verified_raw(repo: Repository, digest: str) -> bool:
    """Use only the content-addressed body named by a persisted SHA-256 digest."""
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return False
    try:
        body = (repo._raw.root / digest[:2] / digest).read_bytes()
    except OSError:
        return False
    return hashlib.sha256(body).hexdigest() == digest


def _selected_charts(repo: Repository, days: tuple[str, ...], markets: tuple[str, ...],
                     warnings: list[str]) -> dict[str, dict[str, dict]]:
    selected: dict[str, dict[str, dict]] = {day: {} for day in days}
    if not markets:
        return selected
    slots = ",".join("?" for _ in markets)
    with closing(repo._connect()) as db:
        rows = db.execute(
            f"""SELECT s.id, s.raw_hash, s.observed_at, c.country,
                       substr(s.observed_at,1,10) AS day
                FROM snapshots s
                JOIN market_runs mr ON mr.id=s.market_run_id
                JOIN charts c ON c.id=mr.chart_id
                LEFT JOIN daily_canonical_snapshots d ON d.snapshot_id=s.id AND d.date=substr(s.observed_at,1,10)
                WHERE substr(s.observed_at,1,10) IN (?,?,?)
                  AND c.country IN ({slots}) AND s.quality='complete'
                  AND c.provider='apple' AND c.platform='ios'
                  AND c.genre='7003' AND c.depth=100
                  AND c.collection='topfreeapplications'
                ORDER BY (d.snapshot_id IS NOT NULL) DESC, s.observed_at DESC, s.id DESC""",
            (*days, *markets),
        ).fetchall()
        for row in rows:
            day, market = row["day"], row["country"]
            if market in selected[day]:
                continue
            # A corrupt preferred chart cannot be silently replaced by a different run.
            if not _verified_raw(repo, row["raw_hash"]):
                selected[day][market] = {"invalid": True}
                warnings.append(f"{day}/{market}: referenced chart raw missing or corrupt")
                continue
            entries = db.execute(
                "SELECT app_id, rank, name, source_genres_json FROM entries WHERE snapshot_id=? ORDER BY rank",
                (row["id"],),
            ).fetchall()
            selected[day][market] = {
                "id": row["id"], "raw_hash": row["raw_hash"],
                "observed_at": row["observed_at"],
                "entries": {str(entry["app_id"]): {
                    "rank": entry["rank"], "name": entry["name"],
                    "genres": json.loads(entry["source_genres_json"]),
                } for entry in entries},
            }
    for day in days:
        selected[day] = {m: c for m, c in selected[day].items() if not c.get("invalid")}
    return selected


def _size(pack: EvidencePack) -> int:
    return len(canonical_json({
        "analysis_date": pack.analysis_date,
        "selected_markets": pack.selected_markets,
        "manifest": pack.manifest,
        "candidates": pack.candidates,
        "warnings": pack.warnings,
    }).encode("utf-8"))


def build_evidence(repo: Repository, analysis_date: str,
                   markets: tuple[str, ...]) -> EvidencePack:
    target = date.fromisoformat(analysis_date)
    chosen = tuple(sorted({market.strip().lower() for market in markets}))
    with closing(repo._connect()) as db:
        known = {row[0] for row in db.execute("SELECT country FROM markets")}
    if any(market not in known for market in chosen):
        raise ValueError("unknown market code")
    warnings: list[str] = []
    empty = EvidencePack(analysis_date, chosen, {}, (), (), (), "insufficient_evidence")
    if not chosen:
        return empty

    days = tuple((target - timedelta(days=offset)).isoformat() for offset in (0, 1, 3))
    charts = _selected_charts(repo, days, chosen, warnings)
    current, prior, older = (charts[day] for day in days)
    for market in chosen:
        if market not in current:
            warnings.append(f"{analysis_date}/{market}: selected market has no verified complete chart")
    if not current:
        return EvidencePack(analysis_date, chosen, {}, (), (), tuple(warnings), "insufficient_evidence")
    for day, set_ in ((days[1], prior), (days[2], older)):
        for market in current:
            if market not in set_:
                warnings.append(f"{day}/{market}: no verified complete comparison chart")

    ranks = [{m: {app: e["rank"] for app, e in chart["entries"].items()}
              for m, chart in set_.items()} for set_ in (current, prior, older)]
    records = []
    for market, chart in current.items():
        pinned = repo.get_canonical_snapshot(analysis_date, market)
        lineage_stale = pinned is not None and pinned["snapshot_id"] != chart["id"]
        for analytic in repo.get_daily_analytics(analysis_date, market):
            app_id = str(analytic["app_id"])
            source = chart["entries"].get(app_id)
            if source is None:
                continue
            row = dict(analytic)
            row["current_rank"] = source["rank"]
            row["analytics_stale"] = lineage_stale or analytic["current_rank"] != source["rank"]
            records.append(row)
    if not records:
        return EvidencePack(analysis_date, chosen, {}, (), (), tuple(warnings), "insufficient_evidence")
    ordered = rank_noteworthy(records, *ranks)
    by_app: dict[str, list[dict]] = {}
    for record in records:
        by_app.setdefault(str(record["app_id"]), []).append(record)

    manifest: dict[str, dict] = {}
    candidates: list[dict] = []
    refs: dict[str, EvidenceRef] = {}

    def add(observation: dict, *, analytics_id: str | None = None,
            metadata_version_id: str | None = None) -> str:
        evidence_id = observation["id"]
        manifest[evidence_id] = observation
        refs[evidence_id] = EvidenceRef(evidence_id, analysis_date,
            observation["market"], observation["app_id"],
            snapshot_id=observation.get("snapshot_id"), analytics_id=analytics_id,
            metadata_version_id=metadata_version_id)
        return evidence_id

    def rank_observation(market: str, chart: dict, app_id: str, day: str) -> str:
        evidence_id = f"{chart['id']}:{app_id}:rank"
        if evidence_id not in manifest:
            add({"id": evidence_id, "metric": "chart_rank", "value": chart["entries"][app_id]["rank"],
                 "unit": "position", "platform": "ios", "market": market,
                 "collection": "top-free", "analysis_date": day,
                 "observed_at": chart["observed_at"], "snapshot_id": chart["id"],
                 "app_id": app_id, "raw_hash": chart["raw_hash"]})
        return evidence_id

    for ordered_row in ordered:
        app_id = str(ordered_row["app_id"])
        candidate_manifest_before = set(manifest)
        candidate_refs_before = set(refs)
        candidate_warnings_before = len(warnings)
        item_records: list[dict] = []
        item_ids: list[str] = []
        remaining_description = _MAX_DESCRIPTION
        same_app = sorted(by_app[app_id], key=lambda r: (r["current_rank"], r["country"]))
        for row in same_app[:_MAX_MARKETS_PER_APP]:
            market = row["country"]
            chart = current[market]
            source = chart["entries"][app_id]
            rank_id = rank_observation(market, chart, app_id, analysis_date)
            ids = [rank_id]
            record = {"market": market, "current_rank": source["rank"],
                      "analytics_stale": row["analytics_stale"], "evidence_ids": ids}
            if row["analytics_stale"]:
                warnings.append(f"{analysis_date}/{market}/{app_id}: analytics lineage or rank stale; rebuilt from chart")
            for offset, baseline in ((1, prior), (3, older)):
                old_chart = baseline.get(market)
                if old_chart is None:
                    continue
                old_entry = old_chart["entries"].get(app_id)
                if old_entry is not None:
                    old_id = rank_observation(market, old_chart, app_id, days[1 if offset == 1 else 2])
                    metric = f"rank_delta_{offset}d"
                    delta_id = f"{chart['id']}:{app_id}:{metric}"
                    value = old_entry["rank"] - source["rank"]
                    ids.append(add({"id": delta_id, "metric": metric, "derived": True,
                        "value": value, "unit": "positions", "market": market, "app_id": app_id,
                        "analysis_date": analysis_date, "snapshot_id": chart["id"],
                        "raw_hash": chart["raw_hash"], "source_ids": [rank_id, old_id],
                        "observed_markets": sorted(current),
                        "comparable_markets": sorted(current.keys() & baseline.keys())}))
                    record[metric] = value
                elif offset == 1:
                    absent_id = f"{old_chart['id']}:{app_id}:absence"
                    ids.append(add({"id": absent_id, "metric": "chart_presence", "derived": True,
                        "value": False, "unit": "present", "market": market, "app_id": app_id,
                        "analysis_date": days[1], "snapshot_id": old_chart["id"],
                        "raw_hash": old_chart["raw_hash"], "source_ids": [],
                        "observed_markets": [market], "comparable_markets": [market],
                        "complete_chart": True}))
                    new_id = f"{chart['id']}:{app_id}:new"
                    ids.append(add({"id": new_id, "metric": "new_entry", "derived": True,
                        "value": True, "unit": "boolean", "market": market, "app_id": app_id,
                        "analysis_date": analysis_date, "snapshot_id": chart["id"],
                        "raw_hash": chart["raw_hash"], "source_ids": [rank_id, absent_id],
                        "observed_markets": sorted(current),
                        "comparable_markets": sorted(current.keys() & prior.keys())}))
                    record["new_entry"] = True
            with closing(repo._connect()) as db:
                meta = db.execute("""SELECT mv.id, mv.description, mv.genres_json,
                           mv.primary_genre, mv.raw_hash FROM snapshot_metadata sm
                    JOIN metadata_versions mv ON mv.id=sm.metadata_version_id
                    WHERE sm.snapshot_id=? AND sm.app_id=? AND mv.status='complete'
                      AND mv.country=? AND mv.provider='apple' AND mv.platform='ios'""",
                    (chart["id"], app_id, market)).fetchone()
            metadata_verified = meta is not None and _verified_raw(repo, meta["raw_hash"])
            description_id = None
            if meta is not None:
                if metadata_verified:
                    genres = json.loads(meta["genres_json"] or "[]")
                    genre = next((g for g in genres if isinstance(g, str)
                                  and g not in ("Games", "Casual")), meta["primary_genre"])
                    if genre:
                        genre_id = f"{chart['id']}:{app_id}:genre"
                        ids.append(add({"id": genre_id, "metric": "store_genre", "value": genre,
                            "market": market, "app_id": app_id, "analysis_date": analysis_date,
                            "snapshot_id": chart["id"], "raw_hash": meta["raw_hash"],
                            "metadata_version_id": meta["id"]}, metadata_version_id=meta["id"]))
                    description = (meta["description"] or "")[:remaining_description]
                    if description:
                        remaining_description -= len(description)
                        desc_id = f"{chart['id']}:{app_id}:description"
                        ids.append(add({"id": desc_id, "metric": "description",
                            "value": "Untrusted store description: " + description,
                            "market": market, "app_id": app_id, "analysis_date": analysis_date,
                            "snapshot_id": chart["id"], "raw_hash": meta["raw_hash"],
                            "metadata_version_id": meta["id"]}, metadata_version_id=meta["id"]))
                        description_id = desc_id
                else:
                    warnings.append(f"{analysis_date}/{market}/{app_id}: bound metadata raw missing or corrupt")
            # P3 taxonomy is an inference only when its keyword source is verified.
            mechanic = row.get("mechanic")
            confidence = row.get("mechanic_confidence")
            keyword = row.get("mechanic_evidence")
            uses_description = bool(keyword and "desc:" in keyword)
            if (not row["analytics_stale"] and mechanic and mechanic != "Other"
                    and confidence in ("medium", "high") and keyword
                    and (not uses_description or description_id is not None)):
                mech_id = f"{chart['id']}:{app_id}:mechanic"
                sources = [rank_id, description_id] if uses_description else [rank_id]
                ids.append(add({"id": mech_id, "metric": "mechanic_inference", "derived": True,
                    "value": mechanic, "confidence": confidence, "keyword_evidence": keyword,
                    "supported": True, "market": market, "app_id": app_id,
                    "analysis_date": analysis_date, "snapshot_id": chart["id"],
                    "raw_hash": chart["raw_hash"], "source_ids": sources},
                    analytics_id=row["id"]))
                record["mechanic"] = mechanic
            item_ids.extend(ids)
            item_records.append(record)
        if not item_records:
            continue
        present = sorted(m for m, chart in current.items() if app_id in chart["entries"])
        rank_ids = [rank_observation(m, current[m], app_id, analysis_date) for m in present]
        presence_id = f"{analysis_date}:{app_id}:presence"
        item_ids.append(add({"id": presence_id, "metric": "chart_presence", "derived": True,
            "value": len(present), "unit": "markets", "market": present[0], "app_id": app_id,
            "analysis_date": analysis_date, "snapshot_id": current[present[0]]["id"],
            "raw_hash": current[present[0]]["raw_hash"], "source_ids": rank_ids,
            "observed_markets": sorted(current), "comparable_markets": sorted(current.keys() & prior.keys()),
            "presence_markets": present}))
        candidate = {"app_id": app_id, "name": current[item_records[0]["market"]]["entries"][app_id]["name"],
                     "records": item_records, "evidence_ids": sorted(set(item_ids))}
        candidates.append(candidate)
        trial = EvidencePack(analysis_date, chosen, dict(manifest), tuple(candidates),
                             tuple(refs.values()), tuple(warnings), None)
        if _size(trial) > _MAX_BYTES:
            candidates.pop()
            for key in set(manifest) - candidate_manifest_before:
                manifest.pop(key)
            for key in set(refs) - candidate_refs_before:
                refs.pop(key)
            del warnings[candidate_warnings_before:]
            break
        if len(candidates) >= _MAX_CANDIDATES:
            break
    if not candidates:
        return EvidencePack(analysis_date, chosen, {}, (), (), tuple(warnings), "insufficient_evidence")
    return EvidencePack(analysis_date, chosen, manifest, tuple(candidates),
                        tuple(refs.values()), tuple(warnings), None)
