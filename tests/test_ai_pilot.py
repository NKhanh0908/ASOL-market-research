"""Contract checks for synthetic, offline P4 human-review pilot packs."""

import json
from pathlib import Path

import pytest


CASES_PATH = Path(__file__).parent / "fixtures" / "ai" / "pilot-cases.json"
CASE_IDS = {
    "empty_scope", "vn_no_baseline", "vn_1d_rise", "multi_market_rise",
    "newly_crawled_market", "partial_source", "unknown_mechanic",
    "conflicting_mechanics", "adversarial_description", "no_credible_recommendation",
}


def _cases():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_pilot_covers_ten_distinct_review_scenarios():
    cases = _cases()
    assert len(cases) == 10
    assert {case["case_id"] for case in cases} == CASE_IDS
    assert all(case["human_review_required"] is True for case in cases)
    assert all(isinstance(case["forbidden_claims"], list) and case["forbidden_claims"]
               for case in cases)
    assert all(0 <= case["expected_max_recommendations"] <= 3 for case in cases)
    assert {case["case_id"] for case in cases if case["expected_max_recommendations"] == 0} == {
        "empty_scope", "no_credible_recommendation",
    }


@pytest.mark.parametrize("case_id", sorted(CASE_IDS))
def test_pilot_pack_uses_source_shaped_evidence_with_closed_ids(case_id):
    case = next(item for item in _cases() if item["case_id"] == case_id)
    pack = case["input"]
    assert pack["analysis_date"] == "2026-09-25"
    assert isinstance(pack["selected_markets"], list)
    assert isinstance(pack["warnings"], list)
    assert isinstance(pack["candidates"], list)
    manifest = pack["manifest"]
    assert isinstance(manifest, dict)
    assert set(case["expected_evidence_ids"]) <= set(manifest)
    assert len(json.dumps(pack, ensure_ascii=False).encode("utf-8")) < 10_000
    if pack["blocked_reason"]:
        assert pack["blocked_reason"] == "insufficient_evidence"
        assert not manifest and not pack["candidates"]
    else:
        assert pack["candidates"] and manifest

    for evidence_id, observation in manifest.items():
        assert observation["id"] == evidence_id
        assert observation["market"] in pack["selected_markets"]
        assert observation["app_id"]
        assert observation["analysis_date"] <= pack["analysis_date"]
        assert observation["metric"] in {
            "chart_rank", "rank_delta_1d", "rank_delta_3d", "chart_presence",
            "new_entry", "store_genre", "description", "mechanic_inference",
        }
        assert set(observation.get("source_ids", [])) <= set(manifest)
        if observation["metric"] == "chart_rank":
            assert observation["collection"] == "top-free"
            assert observation["platform"] == "ios"
            assert observation["snapshot_id"] and observation["raw_hash"]

    for candidate in pack["candidates"]:
        assert candidate["app_id"] and candidate["name"]
        assert candidate["records"]
        assert set(candidate["evidence_ids"]) <= set(manifest)
        for record in candidate["records"]:
            assert record["market"] in pack["selected_markets"]
            assert record["current_rank"] > 0
            assert isinstance(record["analytics_stale"], bool)
            assert set(record["evidence_ids"]) <= set(candidate["evidence_ids"])


def test_pilot_scenarios_contain_the_evidence_needed_for_their_review_questions():
    cases = {case["case_id"]: case for case in _cases()}

    def metrics(case_id):
        return {item["metric"] for item in cases[case_id]["input"]["manifest"].values()}

    assert "rank_delta_1d" not in metrics("vn_no_baseline")
    assert "rank_delta_1d" in metrics("vn_1d_rise")
    assert set(cases["multi_market_rise"]["input"]["selected_markets"]) == {"vn", "th"}
    assert "rank_delta_1d" not in metrics("newly_crawled_market")
    assert cases["partial_source"]["input"]["warnings"]
    assert "mechanic_inference" not in metrics("unknown_mechanic")
    assert sum(item["metric"] == "mechanic_inference" for item in
               cases["conflicting_mechanics"]["input"]["manifest"].values()) == 2
    assert any("ignore previous instructions" in item["value"].lower()
               if item["metric"] == "description" else False
               for item in cases["adversarial_description"]["input"]["manifest"].values())
