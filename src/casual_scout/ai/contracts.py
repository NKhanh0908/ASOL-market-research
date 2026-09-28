"""Data exchanged with the AI evaluation store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    analysis_date: str
    country: str
    app_id: str
    snapshot_id: str | None = None
    analytics_id: str | None = None
    metadata_version_id: str | None = None


@dataclass(frozen=True)
class EvidencePack:
    analysis_date: str
    selected_markets: tuple[str, ...]
    manifest: dict[str, Any]
    candidates: tuple[dict[str, Any], ...]
    refs: tuple[EvidenceRef, ...]
    warnings: tuple[str, ...]
    blocked_reason: str | None


@dataclass(frozen=True)
class EvaluationRequest:
    request_key: str
    analysis_date: str
    markets: tuple[str, ...]
    provider_id: str | None
    model_id: str | None
    prompt_version: str
    prompt_hash: str
    schema_version: str
    canonical_input: dict[str, Any]
    evidence: tuple[EvidenceRef, ...]
    policy: dict[str, Any]
    rerun_of: str | None = None


@dataclass(frozen=True)
class Preflight:
    request: EvaluationRequest
    estimated_cost_usd: str | None
    requires_unknown_confirmation: bool
    blocked_reason: str | None


@dataclass(frozen=True)
class ProviderReply:
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    actual_cost_usd: str | None = None
    cost_method: str | None = None


def canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
