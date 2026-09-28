"""Strict structured output and conservative citation and narrative gates."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True,
                                        min_length=1, max_length=1500)]
Concept = Annotated[str, StringConstraints(strict=True, strip_whitespace=True,
                                           min_length=1, max_length=200)]
EvidenceIds = Annotated[list[Text], Field(min_length=1, max_length=10)]
TextList = Annotated[list[Text], Field(min_length=1, max_length=10)]


class UnsupportedClaim(ValueError):
    """A narrative claim needs human review before it can be shown as evidence-based."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Range(StrictModel):
    min: Annotated[int, Field(strict=True, ge=1)]
    max: Annotated[int, Field(strict=True, ge=1)]

    @model_validator(mode="after")
    def ordered(self) -> Range:
        if self.min > self.max:
            raise ValueError("range minimum exceeds maximum")
        return self


class TeamRange(Range):
    max: Annotated[int, Field(strict=True, ge=1, le=100)]


class WeekRange(Range):
    max: Annotated[int, Field(strict=True, ge=1, le=260)]


class Rationale(StrictModel):
    inference: Text
    evidence_ids: EvidenceIds


class Observation(StrictModel):
    evidence_id: Text


class Rubric(StrictModel):
    evidence_strength: Text
    market_signal: Text
    differentiation: Text
    delivery_risk: Text


class Recommendation(StrictModel):
    concept: Concept
    subgenre: Text
    mechanic: Text
    why_now: Rationale
    observations: Annotated[list[Observation], Field(min_length=1, max_length=10)]
    scope: Literal["prototype", "mvp"]
    features: TextList
    assumptions: TextList
    roles: TextList
    team_size: TeamRange
    timeline_weeks: WeekRange
    feasibility: Literal["high", "medium", "low", "insufficient evidence"]
    rubric: Rubric
    risks: TextList
    unknowns: TextList
    validation_questions: TextList


class Output(StrictModel):
    schema_version: Literal["1"]
    recommendations: Annotated[list[Recommendation], Field(max_length=3)]


OUTPUT_SCHEMA: dict = Output.model_json_schema()

_METRICS = {"chart_rank", "rank_delta_1d", "rank_delta_3d", "chart_presence",
            "new_entry", "mechanic_inference", "description", "store_genre"}
_MOVEMENT = {"rank_delta_1d", "rank_delta_3d"}
_UNSUPPORTED_TOPIC = re.compile(
    r"\b(?:revenue|downloads?|installs?|CPI|retention|IAP|ad\s*/?\s*IAP|"
    r"player preferences?|players? prefer|doanh\s+thu|lượt\s+tải|tải\s+xuống|"
    r"giữ\s+chân|chi\s+phí\s+mỗi\s+lượt\s+cài\s+đặt)\b", re.IGNORECASE,
)
_NUMBER = re.compile(r"(?:\$\s*)?\b\d+(?:[.,]\d+)*(?:\s*%)?\b")
_UNCERTAINTY = re.compile(
    r"\b(?:unknown|uncertain|unmeasured|no data|not proven|does not|cannot|"
    r"hypothesis|hypothesize|test|validate|whether|chưa rõ|không rõ|"
    r"không có dữ liệu|không chứng minh|cần kiểm chứng)\b",
    re.IGNORECASE,
)
_CAUSAL_ASSERTION = re.compile(
    r"\b(?:rank(?:ing)?\s+(?:proves|shows|demonstrates)|"
    r"growth\s+(?:because|due to)|because\s+of\s+(?:rank|growth)|"
    r"(?:thứ|xếp)\s+hạng\s+chứng\s+minh|tăng\s+trưởng\s+nhờ)\b",
    re.IGNORECASE,
)


def _walk_text(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_text(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_text(item)


def _review_narrative(card: dict) -> None:
    for statement in _walk_text(card):
        if _CAUSAL_ASSERTION.search(statement):
            raise UnsupportedClaim("unsupported_claim: unverified causal assertion")
        if _UNSUPPORTED_TOPIC.search(statement) and (
            _NUMBER.search(statement) or not _UNCERTAINTY.search(statement)
        ):
            raise UnsupportedClaim("unsupported_claim: unverified market metric")


def _cited_subgraph(ids: set[str], manifest: dict) -> dict[str, dict]:
    reachable: dict[str, dict] = {}
    pending = list(ids)
    while pending:
        evidence_id = pending.pop()
        if evidence_id in reachable:
            continue
        item = manifest.get(evidence_id)
        if not isinstance(item, dict) or item.get("id") != evidence_id:
            raise ValueError("unknown or malformed cited evidence ID")
        if (item.get("metric") not in _METRICS or "value" not in item
                or not all(isinstance(item.get(key), str) and item[key]
                           for key in ("market", "app_id", "analysis_date"))):
            raise ValueError("malformed cited evidence")
        sources = item.get("source_ids", [])
        if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
            raise ValueError("malformed evidence source IDs")
        if item.get("derived") and item["metric"] in (_MOVEMENT | {"mechanic_inference"}) \
                and not sources:
            raise ValueError("derived evidence has no source")
        reachable[evidence_id] = item
        pending.extend(sources)
    return reachable


def _comparable_movement(item: dict, reachable: dict[str, dict]) -> bool:
    if item.get("metric") not in _MOVEMENT or item.get("derived") is not True:
        return False
    sources = item.get("source_ids", [])
    if len(sources) != 2 or len(set(sources)) != 2:
        return False
    ranks = [reachable[source] for source in sources]
    if any(rank["metric"] != "chart_rank" or isinstance(rank["value"], bool)
           or not isinstance(rank["value"], int)
           or rank["market"] != item["market"] or rank["app_id"] != item["app_id"]
           for rank in ranks):
        return False
    current = next((rank for rank in ranks if rank["analysis_date"] == item["analysis_date"]), None)
    prior = next((rank for rank in ranks if rank is not current), None)
    if current is None or prior is None:
        return False
    try:
        current_day = date.fromisoformat(current["analysis_date"])
        prior_day = date.fromisoformat(prior["analysis_date"])
    except ValueError:
        return False
    if (current_day.isoformat() != current["analysis_date"]
            or prior_day.isoformat() != prior["analysis_date"]):
        return False
    interval = 1 if item["metric"] == "rank_delta_1d" else 3
    return ((current_day - prior_day).days == interval
            and isinstance(item["value"], int) and not isinstance(item["value"], bool)
            and item["value"] == prior["value"] - current["value"])


def _supported_mechanic(item: dict) -> bool:
    return (item.get("metric") == "mechanic_inference" and item.get("derived") is True
            and item.get("supported") is True and isinstance(item.get("value"), str)
            and bool(item["value"].strip()) and isinstance(item.get("keyword_evidence"), str)
            and bool(item["keyword_evidence"].strip()) and bool(item.get("source_ids")))


def validate_output(value: dict, manifest: dict) -> dict:
    """Return schema-normalized output or raise ValueError; never alter feasibility."""
    parsed = Output.model_validate(value)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a dictionary")  # noqa: TRY004 - public contract
    result = parsed.model_dump(mode="json")
    for card in result["recommendations"]:
        cited = {observation["evidence_id"] for observation in card["observations"]}
        cited.update(card["why_now"]["evidence_ids"])
        reachable = _cited_subgraph(cited, manifest)
        _review_narrative(card)
        if card["feasibility"] == "insufficient evidence":
            continue
        movement_markets = {reachable[evidence_id]["market"] for evidence_id in cited
                            if _comparable_movement(reachable[evidence_id], reachable)}
        mechanic = any(_supported_mechanic(reachable[evidence_id]) for evidence_id in cited)
        needed = 2 if card["feasibility"] == "high" else 1
        if len(movement_markets) < needed or not mechanic:
            raise ValueError("feasibility lacks cited comparable movement or supported mechanic")
    return result
