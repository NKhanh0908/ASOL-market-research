"""Provider output is bounded and every claim-bearing citation resolves."""

from copy import deepcopy
from hashlib import sha256

import pytest
from ai_support import valid_output

from casual_scout.ai.contracts import canonical_json
from casual_scout.ai.output import OUTPUT_SCHEMA, UnsupportedClaim, validate_output
from casual_scout.ai.prompt import PROMPT_VERSION, SYSTEM_PROMPT

RANK = {"id": "e1", "metric": "chart_rank", "value": 10, "market": "vn",
        "app_id": "game-1", "analysis_date": "2026-09-25", "snapshot_id": "s1"}


def manifest():
    return {"e1": dict(RANK)}


def comparable_manifest(markets=("vn",)):
    facts = {}
    for market in markets:
        current = f"{market}-current"
        prior = f"{market}-prior"
        movement = f"{market}-delta"
        facts[current] = {**RANK, "id": current, "market": market}
        facts[prior] = {**RANK, "id": prior, "market": market,
                        "value": 20, "analysis_date": "2026-09-24", "snapshot_id": "s0"}
        facts[movement] = {**RANK, "id": movement, "metric": "rank_delta_1d",
                           "market": market, "value": 10, "derived": True,
                           "source_ids": [current, prior]}
    facts["mechanic"] = {**RANK, "id": "mechanic", "metric": "mechanic_inference",
                         "value": "Sort", "derived": True, "supported": True,
                         "confidence": "medium", "keyword_evidence": "name: sort",
                         "source_ids": [f"{markets[0]}-current"]}
    return facts


def cited_card(label, markets=("vn",)):
    card = valid_output()["recommendations"][0]
    card["feasibility"] = label
    ids = [f"{market}-delta" for market in markets] + ["mechanic"]
    card["observations"] = [{"evidence_id": item} for item in ids]
    card["why_now"]["evidence_ids"] = ids
    card["assumptions"] = ["VN market only; experienced gameplay and design team"]
    card["rubric"]["differentiation"] = "Test a timed sort with reversible mistakes"
    return card


@pytest.mark.parametrize("count", [0, 1, 3])
def test_accepts_at_most_three_complete_cards(count):
    value = valid_output()
    value["recommendations"] = [deepcopy(value["recommendations"][0]) for _ in range(count)]
    assert validate_output(value, manifest()) == value


def test_four_cards_rejected():
    value = valid_output()
    value["recommendations"] *= 4
    with pytest.raises(ValueError):
        validate_output(value, manifest())


def test_unknown_citation_is_rejected():
    with pytest.raises(ValueError):
        validate_output(valid_output(), {})


@pytest.mark.parametrize("location", ["observations", "why_now"])
def test_every_citation_resolves(location):
    value = valid_output()
    if location == "observations":
        value["recommendations"][0]["observations"][0]["evidence_id"] = "absent"
    else:
        value["recommendations"][0]["why_now"]["evidence_ids"] = ["absent"]
    with pytest.raises(ValueError):
        validate_output(value, manifest())


@pytest.mark.parametrize("change", [
    lambda c: c.pop("assumptions"),
    lambda c: c["assumptions"].clear(),
    lambda c: c["team_size"].update(min=3, max=2),
    lambda c: c["timeline_weeks"].update(min=5, max=4),
    lambda c: c.update(feasibility=0.8),
    lambda c: c.update(unknown_field="x"),
    lambda c: c["observations"][0].update(value=999),
    lambda c: c["team_size"].update(min="1"),
    lambda c: c.update(concept=" "),
    lambda c: c.update(concept="x" * 201),
    lambda c: c.update(features=["x"] * 11),
    lambda c: c.update(subgenre="x" * 1501),
    lambda c: c["observations"].clear(),
    lambda c: c["why_now"]["evidence_ids"].clear(),
    lambda c: c["team_size"].update(max=101),
    lambda c: c["timeline_weeks"].update(max=261),
    lambda c: c.update(scope="full release"),
])
def test_rejects_unusable_or_fabricated_fields(change):
    value = valid_output()
    change(value["recommendations"][0])
    with pytest.raises(ValueError):
        validate_output(value, manifest())


def test_rejects_top_level_extra_and_wrong_version():
    value = valid_output()
    value["usage"] = {"input_tokens": 12}
    with pytest.raises(ValueError):
        validate_output(value, manifest())
    value.pop("usage")
    value["schema_version"] = "2"
    with pytest.raises(ValueError):
        validate_output(value, manifest())


@pytest.mark.parametrize("label,markets", [("medium", ("vn",)),
                                            ("high", ("vn", "th")),
                                            ("low", ("vn",))])
def test_feasibility_with_cited_movement_and_supported_mechanic(label, markets):
    card = cited_card(label, markets)
    value = {"schema_version": "1", "recommendations": [card]}
    assert validate_output(value, comparable_manifest(markets)) == value


@pytest.mark.parametrize("label", ["high", "medium", "low"])
def test_higher_labels_need_actual_cited_comparison_and_mechanic(label):
    value = valid_output()
    value["recommendations"][0]["feasibility"] = label
    with pytest.raises(ValueError):
        validate_output(value, manifest())


def test_high_requires_movement_in_two_cited_markets():
    value = {"schema_version": "1", "recommendations": [cited_card("high")]}
    with pytest.raises(ValueError):
        validate_output(value, comparable_manifest(("vn", "th")))


def test_medium_rejects_text_only_comparison_and_unsupported_mechanic():
    facts = comparable_manifest()
    facts["vn-delta"]["value"] = "improved"
    value = {"schema_version": "1", "recommendations": [cited_card("medium")]}
    with pytest.raises(ValueError):
        validate_output(value, facts)
    facts = comparable_manifest()
    facts["mechanic"]["supported"] = False
    with pytest.raises(ValueError):
        validate_output(value, facts)


@pytest.mark.parametrize("metric,prior_date", [
    ("rank_delta_1d", "2026-09-23"),
    ("rank_delta_3d", "2026-09-24"),
    ("rank_delta_1d", "2026-09-xx"),
    ("rank_delta_1d", "20260924"),
])
def test_comparable_movement_requires_exact_iso_day_interval(metric, prior_date):
    value = {"schema_version": "1", "recommendations": [cited_card("medium")]}
    facts = comparable_manifest()
    facts["vn-delta"]["metric"] = metric
    facts["vn-prior"]["analysis_date"] = prior_date
    with pytest.raises(ValueError):
        validate_output(value, facts)


def test_three_day_movement_accepts_exact_three_day_prior_rank():
    value = {"schema_version": "1", "recommendations": [cited_card("medium")]}
    facts = comparable_manifest()
    facts["vn-delta"]["metric"] = "rank_delta_3d"
    facts["vn-prior"]["analysis_date"] = "2026-09-22"
    assert validate_output(value, facts) == value


def test_cited_source_closure_is_required_but_unrelated_manifest_is_ignored():
    value = {"schema_version": "1", "recommendations": [cited_card("medium")]}
    facts = comparable_manifest()
    facts["unrelated"] = {"metric": "nonsense"}
    assert validate_output(value, facts) == value
    facts.pop("vn-prior")
    with pytest.raises(ValueError):
        validate_output(value, facts)


@pytest.mark.parametrize("claim", [
    "Revenue rose 30% because this game ranked tenth.",
    "The game had 50,000 downloads last week.",
    "CPI is $0.20 in VN.",
    "Ranking proves players prefer sorting games.",
    "Doanh thu đạt 100 triệu đồng nhờ đứng hạng mười.",
    "Trò chơi có 50.000 lượt tải trong tuần trước.",
    "Tỷ lệ giữ chân đạt 60% tại Việt Nam.",
    "Thứ hạng chứng minh người chơi thích trò này.",
])
def test_unsupported_narrative_claim_is_separately_categorized(claim):
    value = valid_output()
    value["recommendations"][0]["why_now"]["inference"] = claim
    with pytest.raises(UnsupportedClaim, match="unsupported_claim"):
        validate_output(value, manifest())


def test_prompt_and_schema_expose_frozen_contract():
    assert PROMPT_VERSION == "p4-evidence-v1"
    assert "Use Vietnamese for explanations." in SYSTEM_PROMPT
    assert OUTPUT_SCHEMA["properties"]["schema_version"]["const"] == "1"
    assert OUTPUT_SCHEMA["properties"]["recommendations"]["maxItems"] == 3
    assert sha256(canonical_json(OUTPUT_SCHEMA).encode("utf-8")).hexdigest() == (
        "a086c410323a1bb9d6e81bfb5414326a44f0b258bdf0b62821426060f86dac38"
    )
    assert sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest() == (
        "5462c4b97ec97a9b8860db266b00b4d13ae4f418713a3d690a38a7acd5dd4035"
    )
