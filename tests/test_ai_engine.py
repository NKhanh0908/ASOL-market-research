"""Guarded manual AI evaluations with real synthetic evidence and SQLite state."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from ai_support import FakeProvider, seed_ai_evidence, valid_output

from casual_scout.ai.contracts import ProviderReply
from casual_scout.ai.prompt import QUALITATIVE_RUBRIC, SYSTEM_PROMPT
from casual_scout.ai.provider import ProviderFailure, ProviderQuota, ProviderTimeout
from casual_scout.ai.service import ConfirmationRequired, EvaluationEngine
from casual_scout.ai.settings import AISettings, load_ai_settings
from casual_scout.ai.storage import EvaluationStore
from casual_scout.storage import Repository


def engine(tmp_path, *, settings=None, provider=None, seeded=True):
    repo = Repository(tmp_path)
    repo.initialize()
    if seeded:
        seed_ai_evidence(repo)
    store = EvaluationStore(repo)
    provider = provider if provider is not None else FakeProvider(estimate="0.01")
    settings = settings if settings is not None else AISettings(
        enabled=True, max_cost_per_run_usd="0.05"
    )
    return EvaluationEngine(repo, store, settings, provider), store, provider


def test_prepare_freezes_exact_evidence_prompt_and_policy(tmp_path):
    evaluator, _, _ = engine(tmp_path)
    first = evaluator.prepare("2026-09-25", ("vn",))
    second = evaluator.prepare("2026-09-25", ("vn",))
    assert first.request.request_key != second.request.request_key
    frozen = first.request.canonical_input
    assert frozen["system_prompt"] == SYSTEM_PROMPT
    assert json.loads(frozen["user_evidence_json"])["qualitative_rubric"] == QUALITATIVE_RUBRIC
    assert frozen["max_output_tokens"] == 2000
    assert frozen["manifest"]
    assert frozen["output_schema"]["type"] == "object"
    assert first.request.policy["estimated_cost_usd"] == "0.01"
    assert first.request.policy["max_cost_per_run_usd"] == "0.05"


def test_estimator_cannot_mutate_persisted_prompt_evidence_or_token_bound(tmp_path):
    class MutatingEstimator(FakeProvider):
        def estimate_cost(self, canonical_input):
            canonical_input["system_prompt"] = "injected instruction"
            canonical_input["manifest"].clear()
            canonical_input["max_output_tokens"] = 999999
            return "0.01"

    evaluator, _, _ = engine(tmp_path, provider=MutatingEstimator())
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    run = evaluator.submit(preflight)
    assert preflight.request.canonical_input["system_prompt"] == SYSTEM_PROMPT
    assert preflight.request.canonical_input["manifest"]
    assert run["input"]["system_prompt"] == SYSTEM_PROMPT
    assert run["input"]["manifest"]
    assert run["input"]["max_output_tokens"] == 2000


def test_completion_cannot_fabricate_manifest_id_for_its_own_validation(tmp_path):
    class MutatingCompletion(FakeProvider):
        def complete(self, canonical_input):
            self.calls += 1
            source = next(iter(canonical_input["manifest"].values())).copy()
            source["id"] = "fabricated-id"
            canonical_input["manifest"]["fabricated-id"] = source
            output = valid_output()
            card = output["recommendations"][0]
            card["why_now"]["evidence_ids"] = ["fabricated-id"]
            card["observations"] = [{"evidence_id": "fabricated-id"}]
            return ProviderReply(output=output)

    evaluator, store, provider = engine(tmp_path, provider=MutatingCompletion(estimate="0.01"))
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    failed = evaluator.run(run["id"])
    assert failed["error_category"] == "invalid_output"
    assert failed["result"] is None
    assert "fabricated-id" not in store.get(run["id"])["input"]["manifest"]
    assert provider.calls == 1


@pytest.mark.parametrize("settings,provider,seeded,category", [
    (AISettings(), FakeProvider(estimate="0.01"), True, "disabled"),
    (AISettings(enabled=True, max_cost_per_run_usd="0.05"), None, True, "provider_not_configured"),
    (AISettings(enabled=True), FakeProvider(estimate="0.01"), True, "budget_missing"),
    (AISettings(enabled=True, max_cost_per_run_usd="0.01"), FakeProvider(estimate="0.02"), True, "budget_exceeded"),
    (AISettings(enabled=True, max_cost_per_run_usd="0.05"), FakeProvider(estimate="0.01"), False, "insufficient_evidence"),
])
def test_preflight_blocks_without_model_call(tmp_path, settings, provider, seeded, category):
    evaluator, store, _ = engine(tmp_path, settings=settings, provider=provider, seeded=seeded)
    evaluator.provider = provider
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    assert preflight.blocked_reason == category
    run = evaluator.submit(preflight)
    assert run["status"] == "blocked"
    assert run["error_category"] == category
    assert store.get(run["id"])["status"] == "blocked"
    assert provider is None or provider.calls == 0


def test_unknown_cost_requires_both_policy_and_explicit_confirmation(tmp_path):
    provider = FakeProvider()
    evaluator, store, _ = engine(tmp_path, provider=provider, settings=AISettings(
        enabled=True, max_cost_per_run_usd="0.05", allow_unknown_cost_confirmation=True,
    ))
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    assert preflight.requires_unknown_confirmation
    assert preflight.estimated_cost_usd is None
    with pytest.raises(ConfirmationRequired):
        evaluator.submit(preflight)
    assert store.list_runs() == []
    assert provider.calls == 0
    queued = evaluator.submit(preflight, confirm_unknown=True)
    assert queued["status"] == "queued"
    assert queued["policy"]["monetary_upper_bound_guaranteed"] is False


def test_unknown_cost_without_policy_is_blocked(tmp_path):
    evaluator, _, _ = engine(tmp_path, provider=FakeProvider(), settings=AISettings(
        enabled=True, max_cost_per_run_usd="0.05",
    ))
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    assert preflight.blocked_reason == "unknown_cost_confirmation_disabled"
    assert evaluator.submit(preflight)["status"] == "blocked"


def test_submit_replays_and_run_claims_once(tmp_path):
    evaluator, store, provider = engine(tmp_path)
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    first = evaluator.submit(preflight)
    assert evaluator.submit(preflight)["id"] == first["id"]
    assert len(store.list_runs()) == 1
    done = evaluator.run(first["id"])
    assert done["status"] in {"succeeded", "partial"}
    assert done["result"] == {"schema_version": "1", "recommendations": []}
    assert evaluator.run(first["id"])["id"] == first["id"]
    assert provider.calls == 1
    assert provider.inputs == [first["input"]]


def test_provider_can_write_during_complete_without_engine_writer(tmp_path):
    evaluator, store, provider = engine(tmp_path)
    # A second writer, rather than a read, proves the network interval is unlocked.
    def separate_write():
        with store.repo._write_connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS ai_engine_probe (id INTEGER)")
            db.execute("INSERT INTO ai_engine_probe VALUES (1)")
    provider.on_complete = separate_write
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    assert evaluator.run(run["id"])["status"] in {"succeeded", "partial"}
    with store.repo._connect() as db:
        assert db.execute("SELECT count(*) FROM ai_engine_probe").fetchone()[0] == 1


@pytest.mark.parametrize("error,category,usage", [
    (ProviderTimeout(), "timeout_uncertain", None),
    (ProviderQuota({"input_tokens": 7}), "provider_quota", {"input_tokens": 7}),
    (ProviderFailure({"output_tokens": 3}), "provider_failure", {"output_tokens": 3}),
])
def test_provider_errors_are_terminal_safe_and_never_retried(tmp_path, error, category, usage):
    provider = FakeProvider(estimate="0.01", error=error)
    evaluator, _, _ = engine(tmp_path, provider=provider)
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    failed = evaluator.run(run["id"])
    assert failed["status"] == "failed"
    assert failed["error_category"] == category
    assert failed["usage"] == usage
    assert failed["actual_cost_usd"] is None
    assert failed["safe_error"]
    assert evaluator.run(run["id"])["status"] == "failed"
    assert provider.calls == 1


def test_invalid_output_preserves_verified_usage_and_cost_without_raw_output(tmp_path):
    provider = FakeProvider(estimate="0.01", reply=ProviderReply(
        output={"secret": "never persist"}, usage={"input_tokens": 12},
        actual_cost_usd="0.004", cost_method="provider_reported_usd",
    ))
    evaluator, store, _ = engine(tmp_path, provider=provider)
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    failed = evaluator.run(run["id"])
    assert failed["error_category"] == "invalid_output"
    assert failed["result"] is None
    assert failed["usage"] == {"input_tokens": 12}
    assert failed["actual_cost_usd"] == "0.004"
    assert "never persist" not in str(store.get(run["id"]))


def test_unsupported_claim_is_terminal_and_collector_data_remains_readable(tmp_path):
    evaluator, store, provider = engine(tmp_path)
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    evidence_id = next(iter(preflight.request.canonical_input["manifest"]))
    output = valid_output()
    card = output["recommendations"][0]
    card["why_now"]["evidence_ids"] = [evidence_id]
    card["observations"] = [{"evidence_id": evidence_id}]
    card["why_now"]["inference"] = "This proves 100000 downloads."
    provider.reply = ProviderReply(output=output, usage={"input_tokens": 3})
    run = evaluator.submit(preflight)
    failed = evaluator.run(run["id"])
    assert failed["error_category"] == "unsupported_claim"
    assert failed["result"] is None
    assert failed["usage"] == {"input_tokens": 3}
    with store.repo._connect() as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 2


def test_runtime_config_change_fails_before_provider_call(tmp_path):
    evaluator, _, provider = engine(tmp_path)
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    evaluator.settings = replace(evaluator.settings, max_output_tokens=1000)
    failed = evaluator.run(run["id"])
    assert failed["error_category"] == "configuration_changed"
    assert provider.calls == 0


def test_runtime_provider_identity_change_fails_before_call(tmp_path):
    evaluator, _, provider = engine(tmp_path)
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    provider.model_id = "different-model"
    assert evaluator.run(run["id"])["error_category"] == "configuration_changed"
    assert provider.calls == 0


def test_free_tier_daily_limit_is_durable_and_sixth_blocked(tmp_path):
    settings = AISettings(enabled=True, cost_mode="free_tier", free_tier_confirmed=True,
                          max_runs_per_day=5, allow_unknown_cost_confirmation=True)
    evaluator, store, provider = engine(tmp_path, settings=settings, provider=FakeProvider())
    day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    for n in range(5):
        preflight = evaluator.prepare("2026-09-25", ("vn",))
        assert preflight.request.policy["reservation_day"] == day
        assert preflight.request.policy["attempts_remaining"] == 5 - n
        run = evaluator.submit(preflight, confirm_unknown=True)
        assert run["status"] == "queued"
        evaluator.run(run["id"])
    assert EvaluationStore(store.repo).free_tier_attempts(day) == 5
    sixth = evaluator.prepare("2026-09-25", ("vn",))
    assert sixth.blocked_reason == "daily_limit_reached"
    assert evaluator.submit(sixth)["status"] == "blocked"
    assert provider.calls == 5


def test_free_tier_known_estimate_still_requires_manual_confirmation(tmp_path):
    settings = AISettings(enabled=True, cost_mode="free_tier", free_tier_confirmed=True)
    evaluator, store, provider = engine(tmp_path, settings=settings,
                                         provider=FakeProvider(estimate="0"))
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    assert preflight.blocked_reason is None
    with pytest.raises(ConfirmationRequired):
        evaluator.submit(preflight)
    assert store.list_runs() == []
    assert provider.calls == 0
    run = evaluator.submit(preflight, confirm_unknown=True)
    assert run["policy"]["monetary_upper_bound_guaranteed"] is False


def test_malformed_provider_reply_ends_safely_without_retry(tmp_path):
    evaluator, _, provider = engine(tmp_path)
    provider.reply = None
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)))
    failed = evaluator.run(run["id"])
    assert failed["status"] == "failed"
    assert failed["error_category"] == "provider_failure"
    assert evaluator.run(run["id"])["status"] == "failed"
    assert provider.calls == 1


def test_free_tier_guardrails_and_day_rollover(tmp_path, monkeypatch):
    from casual_scout.ai import service

    bad = AISettings(enabled=True, cost_mode="free_tier", free_tier_confirmed=True,
                     max_runs_per_day=4, allow_unknown_cost_confirmation=True)
    evaluator, _, _ = engine(tmp_path, settings=bad, provider=FakeProvider())
    assert evaluator.prepare("2026-09-25", ("vn",)).blocked_reason == "invalid_free_tier_policy"
    evaluator.settings = replace(bad, max_runs_per_day=5)
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    current = service.datetime
    class Tomorrow(current):
        @classmethod
        def now(cls, tz=None):
            return current.now(tz) + timedelta(days=1)
    monkeypatch.setattr(service, "datetime", Tomorrow)
    assert evaluator.submit(preflight, confirm_unknown=True)["error_category"] == "configuration_changed"


def test_queued_free_tier_run_does_not_cross_local_day(tmp_path, monkeypatch):
    from casual_scout.ai import service

    settings = AISettings(enabled=True, cost_mode="free_tier", free_tier_confirmed=True,
                          allow_unknown_cost_confirmation=True)
    evaluator, _, provider = engine(tmp_path, settings=settings, provider=FakeProvider())
    run = evaluator.submit(evaluator.prepare("2026-09-25", ("vn",)), confirm_unknown=True)
    current = service.datetime
    class Tomorrow(current):
        @classmethod
        def now(cls, tz=None):
            return current.now(tz) + timedelta(days=1)
    monkeypatch.setattr(service, "datetime", Tomorrow)
    assert evaluator.run(run["id"])["error_category"] == "configuration_changed"
    assert provider.calls == 0


@pytest.mark.parametrize("changes", [
    {"free_tier_confirmed": False},
    {"max_output_tokens": 2001},
    {"max_output_tokens": 0},
    {"allow_unknown_cost_confirmation": False},
])
def test_free_tier_rejects_unapproved_policy_or_unknown_cost(tmp_path, changes):
    settings = replace(AISettings(enabled=True, cost_mode="free_tier", free_tier_confirmed=True,
                                  allow_unknown_cost_confirmation=True), **changes)
    evaluator, _, provider = engine(tmp_path, settings=settings, provider=FakeProvider())
    preflight = evaluator.prepare("2026-09-25", ("vn",))
    assert preflight.blocked_reason is not None
    assert evaluator.submit(preflight)["status"] == "blocked"
    assert provider.calls == 0


def test_load_settings_is_disabled_by_default_and_parses_free_tier(monkeypatch):
    for name in (
        "CASUAL_SCOUT_AI_ENABLED", "CASUAL_SCOUT_AI_MAX_COST_USD",
        "CASUAL_SCOUT_AI_MAX_OUTPUT_TOKENS", "CASUAL_SCOUT_AI_TIMEOUT_SECONDS",
        "CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST", "CASUAL_SCOUT_AI_COST_MODE",
        "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED", "CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert load_ai_settings() == AISettings()
    monkeypatch.setenv("CASUAL_SCOUT_AI_ENABLED", "true")
    monkeypatch.setenv("CASUAL_SCOUT_AI_COST_MODE", "free_tier")
    monkeypatch.setenv("CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY", "5")
    assert load_ai_settings().cost_mode == "free_tier"
    assert load_ai_settings().free_tier_confirmed is True
