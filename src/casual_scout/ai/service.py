"""Explicit preflight, durable reservation, and one-call AI execution."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

import psutil

from casual_scout.ai.contracts import EvaluationRequest, Preflight, ProviderReply, canonical_json
from casual_scout.ai.evidence import build_evidence
from casual_scout.ai.output import OUTPUT_SCHEMA, UnsupportedClaim, validate_output
from casual_scout.ai.prompt import PROMPT_VERSION, QUALITATIVE_RUBRIC, SYSTEM_PROMPT
from casual_scout.ai.provider import Provider, ProviderFailure, ProviderQuota, ProviderTimeout
from casual_scout.ai.settings import AISettings
from casual_scout.ai.storage import EvaluationStore
from casual_scout.storage import Repository


class ConfirmationRequired(ValueError):
    """An unknown monetary amount needs explicit per-request consent."""


def _local_day() -> str:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()


def _amount(value: str | None, *, positive: bool = False) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or (amount <= 0 if positive else amount < 0):
        return None
    return amount


def _settings_policy(settings: AISettings) -> dict:
    return {
        "enabled": settings.enabled,
        "max_cost_per_run_usd": settings.max_cost_per_run_usd,
        "max_output_tokens": settings.max_output_tokens,
        "timeout_seconds": settings.timeout_seconds,
        "allow_unknown_cost_confirmation": settings.allow_unknown_cost_confirmation,
        "cost_mode": settings.cost_mode,
        "free_tier_confirmed": settings.free_tier_confirmed,
        "max_runs_per_day": settings.max_runs_per_day,
    }


class EvaluationEngine:
    def __init__(self, repo: Repository, store: EvaluationStore,
                 settings: AISettings, provider: Provider | None) -> None:
        self.repo = repo
        self.store = store
        self.settings = settings
        self.provider = provider

    def prepare(self, day: str, markets: tuple[str, ...]) -> Preflight:
        """Build read-only evidence and a new, fully frozen request candidate."""
        pack = build_evidence(self.repo, day, markets)
        settings = self.settings
        reservation_day = _local_day() if settings.cost_mode == "free_tier" else None
        remaining = (max(0, 5 - self.store.free_tier_attempts(reservation_day))
                     if reservation_day else None)
        user_evidence_json = canonical_json({
            "analysis_date": pack.analysis_date,
            "selected_markets": pack.selected_markets,
            "manifest": pack.manifest,
            "candidates": pack.candidates,
            "warnings": pack.warnings,
            "qualitative_rubric": QUALITATIVE_RUBRIC,
        })
        canonical_input = {
            "system_prompt": SYSTEM_PROMPT,
            "user_evidence_json": user_evidence_json,
            "manifest": pack.manifest,
            "output_schema": OUTPUT_SCHEMA,
            "max_output_tokens": settings.max_output_tokens,
        }
        policy = _settings_policy(settings)
        policy.update({
            "estimated_cost_usd": None,
            "warnings": list(pack.warnings),
            "requires_unknown_confirmation": False,
            "manual_confirmation_required": settings.cost_mode == "free_tier",
            "monetary_upper_bound_guaranteed": False,
        })
        if reservation_day:
            policy["reservation_day"] = reservation_day
            policy["attempts_remaining"] = remaining

        blocked = None
        estimate = None
        requires_confirmation = False
        if not settings.enabled:
            blocked = "disabled"
        elif self.provider is None:
            blocked = "provider_not_configured"
        elif (type(settings.max_output_tokens) is not int or settings.max_output_tokens <= 0
              or type(settings.timeout_seconds) is not int or settings.timeout_seconds <= 0):
            blocked = "invalid_settings"
        elif settings.cost_mode == "metered":
            if _amount(settings.max_cost_per_run_usd, positive=True) is None:
                blocked = "budget_missing"
        elif settings.cost_mode == "free_tier":
            if (not settings.free_tier_confirmed or type(settings.max_runs_per_day) is not int
                    or settings.max_runs_per_day != 5 or settings.max_output_tokens > 2000):
                blocked = "invalid_free_tier_policy"
        else:
            blocked = "invalid_settings"

        if blocked is None and pack.blocked_reason:
            blocked = pack.blocked_reason
        if blocked is None and remaining == 0:
            blocked = "daily_limit_reached"
        if blocked is None:
            try:
                estimate = self.provider.estimate_cost(deepcopy(canonical_input))
            except Exception:  # noqa: BLE001 - provider boundary must not leak raw exceptions
                blocked = "provider_failure"
            if blocked is None and estimate is not None:
                value = _amount(estimate)
                if value is None:
                    estimate = None
                    blocked = "provider_failure"
                elif (settings.cost_mode == "metered"
                      and value > _amount(settings.max_cost_per_run_usd, positive=True)):
                    blocked = "budget_exceeded"
            elif blocked is None:
                if not settings.allow_unknown_cost_confirmation:
                    blocked = "unknown_cost_confirmation_disabled"
                else:
                    requires_confirmation = True

        policy["estimated_cost_usd"] = estimate
        policy["requires_unknown_confirmation"] = requires_confirmation
        request = EvaluationRequest(
            request_key=str(uuid4()), analysis_date=pack.analysis_date,
            markets=pack.selected_markets,
            provider_id=self.provider.provider_id if self.provider else None,
            model_id=self.provider.model_id if self.provider else None,
            prompt_version=PROMPT_VERSION,
            prompt_hash=sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            schema_version="1", canonical_input=canonical_input,
            evidence=pack.refs, policy=policy,
        )
        return Preflight(request, estimate, requires_confirmation, blocked)

    def submit(self, preflight: Preflight, confirm_unknown: bool = False) -> dict:
        """Persist blocked or queued state; the caller dispatches run explicitly."""
        request = preflight.request
        blocked = preflight.blocked_reason
        if blocked is None and request.policy.get("cost_mode") == "free_tier" \
                and request.policy.get("reservation_day") != _local_day():
            blocked = "configuration_changed"
        if blocked is None and (
            preflight.requires_unknown_confirmation
            or request.policy.get("manual_confirmation_required")
        ) and not confirm_unknown:
            raise ConfirmationRequired(
                "Confirm this manual evaluation; actual cost cannot be guaranteed from an estimate."
            )
        return self.store.create(request, blocked_reason=blocked)

    def _matches_frozen_configuration(self, run: dict) -> bool:
        if self.provider is None or (self.provider.provider_id, self.provider.model_id) != (
            run["provider_id"], run["model_id"]
        ):
            return False
        policy = run["policy"]
        if any(policy.get(key) != value for key, value in _settings_policy(self.settings).items()):
            return False
        return policy.get("cost_mode") != "free_tier" or policy.get("reservation_day") == _local_day()

    def run(self, run_id: str) -> dict:
        """Claim once, release SQLite writer, call provider once, then finish."""
        if not self.store.claim(run_id, os.getpid(), psutil.Process().create_time()):
            return self.store.get(run_id)
        run = self.store.get(run_id)
        if not self._matches_frozen_configuration(run):
            return self.store.finish(run_id, "failed", error_category="configuration_changed")
        try:
            reply = self.provider.complete(deepcopy(run["input"]))
        except ProviderTimeout:
            return self.store.finish(run_id, "failed", error_category="timeout_uncertain")
        except ProviderQuota as exc:
            return self.store.finish(run_id, "failed", usage=exc.usage,
                                     error_category="provider_quota")
        except ProviderFailure as exc:
            return self.store.finish(run_id, "failed", usage=exc.usage,
                                     error_category="provider_failure")
        except Exception:  # noqa: BLE001 - provider boundary must not leak raw exceptions
            return self.store.finish(run_id, "failed", error_category="provider_failure")

        if not isinstance(reply, ProviderReply):
            return self.store.finish(run_id, "failed", error_category="provider_failure")
        if reply.usage is not None and not isinstance(reply.usage, dict):
            return self.store.finish(run_id, "failed", error_category="provider_failure")
        if (reply.actual_cost_usd is None) != (reply.cost_method is None) or (
            reply.actual_cost_usd is not None and (
                _amount(reply.actual_cost_usd) is None or reply.cost_method not in {
                    "provider_reported_usd", "verified_conversion"
                }
            )
        ):
            return self.store.finish(run_id, "failed", usage=reply.usage,
                                     error_category="provider_failure")
        provenance = {"usage": reply.usage, "actual_cost_usd": reply.actual_cost_usd,
                      "cost_method": reply.cost_method}
        try:
            result = validate_output(reply.output, run["input"]["manifest"])
        except UnsupportedClaim:
            return self.store.finish(run_id, "failed", error_category="unsupported_claim",
                                     **provenance)
        except (ValueError, TypeError):
            return self.store.finish(run_id, "failed", error_category="invalid_output",
                                     **provenance)
        return self.store.finish(
            run_id, "partial" if run["policy"]["warnings"] else "succeeded",
            result=result, **provenance,
        )
