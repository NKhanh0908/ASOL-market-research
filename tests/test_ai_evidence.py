import json
from dataclasses import FrozenInstanceError
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pytest
from ai_support import seed_ai_evidence

from casual_scout.ai.contracts import canonical_json
from casual_scout.storage import Repository


_FEED = (Path(__file__).resolve().parents[1] / "docs/core/research/evidence/"
         "2026-09-10-ios-p1/vn-casual-100.json").read_bytes()


def _chart(repo, day, market, *, shift=0, feed="top-free", metadata=False,
           new_first_app_id=None):
    from casual_scout.collection.jobs import JobService
    from casual_scout.models import Chart, HttpResult
    from casual_scout.providers.apple import parse_chart

    chart = Chart(market, feed_type=feed)
    payload = json.loads(_FEED)
    if shift:
        entries = payload["feed"]["entry"]
        payload["feed"]["entry"] = entries[shift:] + entries[:shift]
    if new_first_app_id:
        payload["feed"]["entry"][0]["id"]["attributes"]["im:id"] = new_first_app_id
    body = json.dumps(payload, ensure_ascii=False).encode()
    body = body.replace(b"/vn/", f"/{market}/".encode())
    if feed == "top-grossing":
        body = body.replace(b"topfreeapplications", b"topgrossingapplications")
    jobs = JobService(repo)
    run_id = jobs.submit("manual", [market], f"ai-{day}-{market}-{feed}", [feed])
    reply = HttpResult(
        url=f"https://itunes.apple.com/{market}/rss/{chart.collection}/limit=100/genre=7003/json",
        started_at=datetime.fromisoformat(day + "T08:00:00+00:00"),
        elapsed_ms=1, status=200, body=body,
        headers={"content-type": "application/json"}, error=None,
    )
    saved = repo.save_snapshot(run_id, reply, parse_chart(body, chart))
    if metadata:
        app_id = str(payload["feed"]["entry"][0]["id"]["attributes"]["im:id"])
        values = {app_id: {"description": "Merge pieces to solve a puzzle " * 80,
                           "genres": ["Games", "Puzzle"]}}
        meta_reply = HttpResult(
            url=f"https://itunes.apple.com/lookup?id={app_id}&country={market}",
            started_at=reply.started_at, elapsed_ms=1, status=200,
            body=json.dumps(values).encode(), headers={}, error=None,
        )
        versions = repo.save_metadata(market, values, meta_reply)
        repo.bind_metadata(saved, versions)
    jobs.finish(run_id, "succeeded")
    return saved


def test_empty_evidence_is_explicitly_blocked(tmp_path):
    from casual_scout.ai.evidence import build_evidence

    repo = Repository(tmp_path)
    repo.initialize()
    pack = build_evidence(repo, "2026-09-25", ("vn",))
    assert pack.blocked_reason == "insufficient_evidence"
    assert pack.candidates == ()
    assert pack.manifest == {}


def test_real_source_pack_is_deterministic_bounded_and_read_only(tmp_path):
    from casual_scout.ai.evidence import build_evidence

    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    with repo._connect() as db:
        before = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("snapshots", "daily_rank_analytics", "raw_responses")}

    pack = build_evidence(repo, "2026-09-25", (" VN ", "vn"))
    second = build_evidence(repo, "2026-09-25", ("vn",))
    assert pack == second
    assert pack.selected_markets == ("vn",)
    assert pack.blocked_reason is None
    assert 0 < len(pack.candidates) <= 20
    assert len(canonical_json({"manifest": pack.manifest, "candidates": pack.candidates}).encode()) <= 30_000
    assert all(item["app_id"] for item in pack.candidates)
    assert all(len(item["records"]) <= 3 for item in pack.candidates)
    assert all(ob["market"] == "vn" for ob in pack.manifest.values())
    assert all(ob["metric"] in {"chart_rank", "rank_delta_1d", "rank_delta_3d",
                                  "chart_presence", "new_entry", "mechanic_inference",
                                  "description", "store_genre"}
               for ob in pack.manifest.values())
    assert all(ob.get("raw_hash") == sha256(repo._raw.root.joinpath(
        ob["raw_hash"][:2], ob["raw_hash"]).read_bytes()).hexdigest()
               for ob in pack.manifest.values() if ob.get("raw_hash"))
    assert not any(key in canonical_json({"pack": pack.manifest, "candidates": pack.candidates})
                   for key in ("opportunity_score", "PURE_ADS", "monetization_model", "revenue"))
    with repo._connect() as db:
        after = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                 for table in before}
    assert after == before
    with pytest.raises(FrozenInstanceError):
        pack.analysis_date = "other"


def test_unknown_market_rejected(tmp_path):
    from casual_scout.ai.evidence import build_evidence

    repo = Repository(tmp_path)
    repo.initialize()
    with pytest.raises(ValueError):
        build_evidence(repo, "2026-09-25", ("zz",))


def test_selected_market_and_missing_baseline_do_not_fabricate_movement(tmp_path):
    from casual_scout.ai.evidence import build_evidence
    from casual_scout.analysis.service import AnalysisService

    repo = Repository(tmp_path)
    repo.initialize()
    _chart(repo, "2026-09-24", "vn")
    _chart(repo, "2026-09-25", "vn", shift=1)
    _chart(repo, "2026-09-25", "th")
    _chart(repo, "2026-09-25", "us")
    _chart(repo, "2026-09-25", "sg", feed="top-grossing")
    AnalysisService(repo).analyze_date("2026-09-25", ["vn", "th", "us", "sg"])

    vn = build_evidence(repo, "2026-09-25", ("vn",))
    multi = build_evidence(repo, "2026-09-25", ("vn", "th", "sg"))
    assert vn.blocked_reason is None
    assert all(ob["market"] == "vn" for ob in vn.manifest.values())
    assert all(ob["market"] != "sg" for ob in multi.manifest.values())
    assert not any(ob["metric"] in ("new_entry", "rank_delta_1d") and ob["market"] == "th"
                   for ob in multi.manifest.values())
    assert any("th" in warning and "comparison" in warning for warning in multi.warnings), multi.warnings
    assert any("sg" in warning and "selected market" in warning for warning in multi.warnings)


def test_corrupt_chart_raw_excludes_evidence_and_bound_metadata_is_verified(tmp_path):
    from casual_scout.ai.evidence import build_evidence
    from casual_scout.analysis.service import AnalysisService

    repo = Repository(tmp_path)
    repo.initialize()
    _chart(repo, "2026-09-24", "vn")
    current = _chart(repo, "2026-09-25", "vn", metadata=True)
    AnalysisService(repo).analyze_date("2026-09-25", ["vn"])
    pack = build_evidence(repo, "2026-09-25", ("vn",))
    descriptions = [ob for ob in pack.manifest.values() if ob["metric"] == "description"]
    assert descriptions
    assert descriptions[0]["value"].startswith("Untrusted store description: ")
    assert len(descriptions[0]["value"].removeprefix("Untrusted store description: ")) == 800
    assert descriptions[0]["metadata_version_id"]
    assert any(ref.metadata_version_id == descriptions[0]["metadata_version_id"] for ref in pack.refs)
    assert any(ob["metric"] == "store_genre" and ob["value"] == "Puzzle"
               and ob["metadata_version_id"] == descriptions[0]["metadata_version_id"]
               for ob in pack.manifest.values())

    digest = repo.get_snapshot(current)["raw_hash"]
    (repo._raw.root / digest[:2] / digest).write_bytes(b"corrupt")
    broken = build_evidence(repo, "2026-09-25", ("vn",))
    assert broken.blocked_reason == "insufficient_evidence"
    assert broken.manifest == {}
    assert any("raw missing or corrupt" in warning for warning in broken.warnings)


def test_matching_rank_from_different_canonical_chart_is_marked_stale(tmp_path):
    from casual_scout.ai.evidence import build_evidence
    from casual_scout.analysis.service import AnalysisService

    repo = Repository(tmp_path)
    repo.initialize()
    _chart(repo, "2026-09-24", "vn")
    _chart(repo, "2026-09-25", "vn")
    grossing = _chart(repo, "2026-09-25", "vn", feed="top-grossing")
    repo.save_canonical_snapshot("2026-09-25", "vn", grossing, "2026-09-25T08:00:00Z")
    AnalysisService(repo).analyze_date("2026-09-25", ["vn"])

    pack = build_evidence(repo, "2026-09-25", ("vn",))
    assert pack.blocked_reason is None
    assert all(record["analytics_stale"] for candidate in pack.candidates
               for record in candidate["records"])
    assert any("analytics" in warning and "stale" in warning for warning in pack.warnings)


def test_rebuilt_rank_and_pack_do_not_follow_later_analytics_changes(tmp_path):
    from casual_scout.ai.evidence import build_evidence

    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    original = build_evidence(repo, "2026-09-25", ("vn",))
    first = original.candidates[0]
    with repo._write_connection() as db:
        db.execute("UPDATE daily_rank_analytics SET current_rank=99 WHERE date=? AND country=? AND app_id=?",
                   ("2026-09-25", "vn", first["app_id"]))
    rebuilt = build_evidence(repo, "2026-09-25", ("vn",))
    assert original.candidates[0]["records"][0]["analytics_stale"] is False
    matching = next(c for c in rebuilt.candidates if c["app_id"] == first["app_id"])
    assert matching["records"][0]["analytics_stale"] is True
    assert matching["records"][0]["current_rank"] == first["records"][0]["current_rank"]
    assert any("analytics" in warning for warning in rebuilt.warnings)
    assert {source_id for ob in rebuilt.manifest.values() for source_id in ob.get("source_ids", [])} <= set(rebuilt.manifest)


def test_missing_bound_metadata_raw_removes_only_metadata_observations(tmp_path):
    from casual_scout.ai.evidence import build_evidence
    from casual_scout.analysis.service import AnalysisService

    repo = Repository(tmp_path)
    repo.initialize()
    _chart(repo, "2026-09-24", "vn")
    _chart(repo, "2026-09-25", "vn", metadata=True)
    AnalysisService(repo).analyze_date("2026-09-25", ["vn"])
    good = build_evidence(repo, "2026-09-25", ("vn",))
    metadata_ob = next(ob for ob in good.manifest.values() if ob["metric"] == "description")
    digest = metadata_ob["raw_hash"]
    (repo._raw.root / digest[:2] / digest).write_bytes(b"corrupt")

    pack = build_evidence(repo, "2026-09-25", ("vn",))
    assert pack.blocked_reason is None
    assert not any(ob["metric"] in ("description", "store_genre") for ob in pack.manifest.values())
    assert not any(ob["metric"] == "mechanic_inference" and ob["app_id"] == metadata_ob["app_id"]
                   for ob in pack.manifest.values())
    assert any(ob["metric"] == "chart_rank" for ob in pack.manifest.values())
    assert any("metadata raw missing or corrupt" in warning for warning in pack.warnings)


def test_partial_chart_is_not_a_market_observation(tmp_path):
    from casual_scout.ai.evidence import build_evidence
    from test_analysis_service import _create_snapshot_with_entries

    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    _create_snapshot_with_entries(
        repo, "partial-th", "partial-th-chart", "th", "2026-09-25",
        "2026-09-25T09:00:00Z", [("partial-app", 1, "Partial App")],
        quality="partial",
    )

    pack = build_evidence(repo, "2026-09-25", ("vn", "th"))
    assert pack.blocked_reason is None
    assert all(ob["market"] == "vn" for ob in pack.manifest.values())
    assert any("th" in warning and "selected market" in warning for warning in pack.warnings)


def test_new_entry_uses_complete_previous_chart_as_absence_evidence(tmp_path):
    from casual_scout.ai.evidence import build_evidence
    from casual_scout.analysis.service import AnalysisService

    repo = Repository(tmp_path)
    repo.initialize()
    _chart(repo, "2026-09-24", "vn")
    _chart(repo, "2026-09-25", "vn", new_first_app_id="new-verified-app")
    AnalysisService(repo).analyze_date("2026-09-25", ["vn"])
    pack = build_evidence(repo, "2026-09-25", ("vn",))

    candidate = next(c for c in pack.candidates if c["app_id"] == "new-verified-app")
    assert candidate["records"][0]["new_entry"] is True
    new_ob = next(pack.manifest[eid] for eid in candidate["evidence_ids"]
                  if pack.manifest[eid]["metric"] == "new_entry")
    absence = next(pack.manifest[eid] for eid in new_ob["source_ids"]
                   if pack.manifest[eid]["metric"] == "chart_presence")
    assert absence["value"] is False
    assert absence["complete_chart"] is True
    assert absence["analysis_date"] == "2026-09-24"


def test_rejected_candidate_does_not_leave_warnings_over_byte_bound(tmp_path, monkeypatch):
    from casual_scout.ai import evidence

    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    baseline = evidence.build_evidence(repo, "2026-09-25", ("vn",))
    first, second = baseline.candidates[:2]
    with repo._write_connection() as db:
        db.execute("UPDATE daily_rank_analytics SET current_rank=99 WHERE date=? AND country=? AND app_id=?",
                   ("2026-09-25", "vn", second["app_id"]))

    first_ids = set(first["evidence_ids"])
    for evidence_id in tuple(first_ids):
        first_ids.update(baseline.manifest[evidence_id].get("source_ids", []))
    first_manifest = {key: value for key, value in baseline.manifest.items() if key in first_ids}
    first_size = len(canonical_json({
        "analysis_date": "2026-09-25", "selected_markets": ("vn",),
        "manifest": first_manifest, "candidates": (first,), "warnings": baseline.warnings,
    }).encode("utf-8"))
    monkeypatch.setattr(evidence, "_MAX_BYTES", first_size + 1)

    pack = evidence.build_evidence(repo, "2026-09-25", ("vn",))
    assert [candidate["app_id"] for candidate in pack.candidates] == [first["app_id"]]
    assert len(canonical_json({
        "analysis_date": pack.analysis_date, "selected_markets": pack.selected_markets,
        "manifest": pack.manifest, "candidates": pack.candidates, "warnings": pack.warnings,
    }).encode("utf-8")) <= first_size + 1
    assert not any(second["app_id"] in warning for warning in pack.warnings)
