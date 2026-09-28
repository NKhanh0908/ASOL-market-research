import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from ai_support import request

from casual_scout.ai.contracts import EvidenceRef
from casual_scout.ai.storage import EvaluationBusy, EvaluationStore
from casual_scout.storage import Repository


def test_additive_idempotent_migration(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    with repo._connect() as db:
        db.execute(
            "INSERT INTO runs (id, request_key, trigger, status, started_at) "
            "VALUES ('run-1', 'collect-1', 'manual', 'succeeded', '2026-09-25T00:00:00Z')"
        )
        db.execute(
            "INSERT INTO charts (id, provider, platform, country, collection, genre, depth, "
            "version, endpoint, created_at) VALUES "
            "('chart-1', 'apple', 'ios', 'vn', 'topfreeapplications', '7003', 100, 1, "
            "'url', '2026-09-25T00:00:00Z')"
        )
        db.execute(
            "INSERT INTO market_runs (id, run_id, chart_id, chart_status, "
            "enrichment_status, started_at) VALUES "
            "('mr-1', 'run-1', 'chart-1', 'complete', 'complete', '2026-09-25T00:00:00Z')"
        )
        db.execute(
            "INSERT INTO raw_responses (hash, path, endpoint, status, received_at, "
            "headers_json, size_bytes) VALUES "
            "('hash-1', 'raw/path', 'url', 200, '2026-09-25T00:00:00Z', '{}', 1)"
        )
        db.execute(
            "INSERT INTO snapshots (id, market_run_id, raw_hash, observed_at, quality, "
            "issues_json) VALUES "
            "('snap-1', 'mr-1', 'hash-1', '2026-09-25T00:00:00Z', 'complete', '[]')"
        )
        db.execute(
            "INSERT INTO daily_rank_analytics "
            "(id, date, country, app_id, current_rank, signal, signal_reasons_json, "
            "mechanic, mechanic_confidence, cross_market_count, cross_markets_json, "
            "created_at) VALUES "
            "('analytics-1', '2026-09-25', 'vn', 'app-1', 3, 'STEADY', '[]', "
            "'tap', 'high', 1, '[\"vn\"]', '2026-09-25T00:00:00Z')"
        )
        db.commit()
    with repo._connect() as db:
        before = db.execute("SELECT * FROM markets ORDER BY country").fetchall()
        snapshot = tuple(db.execute("SELECT * FROM snapshots WHERE id = 'snap-1'").fetchone())
        analytics = tuple(
            db.execute("SELECT * FROM daily_rank_analytics WHERE id = 'analytics-1'").fetchone()
        )
    repo.initialize()
    repo.initialize()
    with repo._connect() as db:
        assert db.execute("SELECT * FROM markets ORDER BY country").fetchall() == before
        assert tuple(db.execute("SELECT * FROM snapshots WHERE id = 'snap-1'").fetchone()) == snapshot
        assert tuple(
            db.execute("SELECT * FROM daily_rank_analytics WHERE id = 'analytics-1'").fetchone()
        ) == analytics
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"ai_evaluation_runs", "ai_run_evidence"} <= names
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_canonical_json_is_stable_and_rejects_nan():
    from casual_scout.ai.contracts import canonical_json

    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert canonical_json({"é": "Việt Nam"}) == '{"é":"Việt Nam"}'
    with pytest.raises(ValueError):
        canonical_json({"bad": float("nan")})


def test_contracts_are_frozen_and_preserve_unknown_cost():
    from ai_support import request

    from casual_scout.ai.contracts import EvidenceRef, ProviderReply

    evidence = EvidenceRef("e-1", "2026-09-25", "vn", "app-1")
    assert evidence.snapshot_id is None
    assert evidence.analytics_id is None
    assert evidence.metadata_version_id is None
    assert request().rerun_of is None
    assert request().markets == ("vn",)
    reply = ProviderReply(output={"recommendations": []})
    assert reply.usage is None
    assert reply.actual_cost_usd is None
    assert reply.cost_method is None
    with pytest.raises(FrozenInstanceError):
        evidence.app_id = "other"


def _store(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    return repo, EvaluationStore(repo)


def test_lifecycle_replay_and_unknown_cost(tmp_path):
    _, store = _store(tmp_path)
    run = store.create(request())
    assert store.create(request())["id"] == run["id"]
    assert run["status"] == "queued"
    assert run["owner_pid"] is not None
    assert run["owner_birth"] is not None
    assert store.active()["id"] == run["id"]
    assert store.claim(run["id"], 1234, 1.0)
    assert not store.claim(run["id"], 1234, 1.0)
    stored = store.finish(run["id"], "succeeded", result={"recommendations": []})
    assert stored["result"] == {"recommendations": []}
    assert stored["actual_cost_usd"] is None
    assert stored["usage"] is None
    assert store.active() is None
    assert store.list_runs()[0] == stored
    with pytest.raises(ValueError):
        store.finish(run["id"], "failed", error_category="timeout")
    with pytest.raises(KeyError):
        store.get("missing")
    with pytest.raises(ValueError):
        store.list_runs(101)


def test_blocked_creation_and_dispatch_failure(tmp_path):
    _, store = _store(tmp_path)
    blocked = store.create(request("blocked"), blocked_reason="provider_not_configured")
    assert blocked["status"] == "blocked"
    assert blocked["provider_id"] is None
    assert blocked["owner_pid"] is None
    assert blocked["error_category"] == "provider_not_configured"
    run = store.create(request("dispatch"))
    failed = store.finish(run["id"], "failed", error_category="dispatch_failed")
    assert failed["status"] == "failed"
    assert failed["ended_at"] is not None
    assert not store.claim(blocked["id"], 1, 1.0)


def test_replay_content_and_caller_mutation(tmp_path):
    _, store = _store(tmp_path)
    original = request()
    run = store.create(original)
    original.canonical_input["messages"].append({"content": "later"})
    assert store.get(run["id"])["input"] == {"messages": [], "manifest": {}}
    with pytest.raises(ValueError):
        store.create(original)
    with pytest.raises(EvaluationBusy):
        store.create(request("other"))


def test_evidence_is_sealed_on_create_and_survives_analytics_recalculation(tmp_path):
    repo, store = _store(tmp_path)
    with repo._write_connection() as db:
        db.execute(
            "INSERT INTO daily_rank_analytics(id,date,country,app_id,current_rank,signal,"
            "signal_reasons_json,mechanic,mechanic_confidence,cross_market_count,"
            "cross_markets_json,created_at) VALUES "
            "('an-1','2026-09-25','vn','app-1',3,'STEADY','[]','tap','high',1,"
            "'[\"vn\"]','2026-09-25T00:00:00Z')"
        )
    evidence = EvidenceRef("ev-1", "2026-09-25", "vn", "app-1", analytics_id="an-1")
    item = replace(request(), evidence=(evidence,), canonical_input={"rank": 3})
    run = store.create(item)
    with repo._write_connection() as db:
        db.execute("UPDATE daily_rank_analytics SET current_rank=8 WHERE id='an-1'")
    with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO ai_run_evidence(run_id,evidence_id,analysis_date,country,app_id) "
            "VALUES (?,?,?,?,?)",
            (run["id"], "late", "2026-09-25", "vn", "app-2"),
        )
    assert store.get(run["id"])["evidence"] == [vars(evidence)]
    assert store.get(run["id"])["input"] == {"rank": 3}


def test_blocked_run_keeps_valid_evidence_sealed(tmp_path):
    repo, store = _store(tmp_path)
    evidence = EvidenceRef("blocked-evidence", "2026-09-25", "vn", "app-1")
    run = store.create(
        replace(request(), evidence=(evidence,)), blocked_reason="provider_not_configured"
    )
    assert run["status"] == "blocked"
    assert run["evidence"] == [vars(evidence)]
    with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO ai_run_evidence(run_id,evidence_id,analysis_date,country,app_id) "
            "VALUES (?,?,?,?,?)",
            (run["id"], "late", "2026-09-25", "vn", "app-2"),
        )


@pytest.mark.parametrize("cost", ["-0.01", "NaN", "Infinity", "garbage"])
def test_invalid_cost_is_rejected(tmp_path, cost):
    _, store = _store(tmp_path)
    run = store.create(request())
    store.claim(run["id"], 1, 1.0)
    with pytest.raises(ValueError):
        store.finish(run["id"], "succeeded", actual_cost_usd=cost)
    assert store.get(run["id"])["status"] == "running"


def test_secret_keys_and_unapproved_usage_are_not_persisted(tmp_path):
    _, store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.create(replace(request(), canonical_input={"nested": [{"api_key": "secret"}]}))
    run = store.create(request())
    store.claim(run["id"], 1, 1.0)
    with pytest.raises(ValueError):
        store.finish(run["id"], "succeeded", result={"authorization": "secret"})
    stored = store.finish(
        run["id"], "succeeded", result={},
        usage={"input_tokens": 2, "output_tokens": 3, "raw_response": "secret"},
    )
    assert stored["usage"] == {"input_tokens": 2, "output_tokens": 3}


def test_reported_usd_cost_is_preserved_and_raw_error_text_rejected(tmp_path):
    _, store = _store(tmp_path)
    run = store.create(request())
    store.claim(run["id"], 1, 1.0)
    with pytest.raises(ValueError):
        store.finish(
            run["id"], "failed", error_category="provider_error",
            safe_error="HTTP request to secret.example failed",
        )
    stored = store.finish(
        run["id"], "partial", result={"recommendations": []},
        usage={"total_tokens": 10}, actual_cost_usd="0.0025",
        cost_method="provider_reported_usd",
    )
    assert stored["actual_cost_usd"] == "0.0025"
    assert stored["cost_method"] == "provider_reported_usd"
    assert stored["usage"] == {"total_tokens": 10}


@pytest.mark.parametrize(
    ("cost", "method"),
    [
        ("0.0025", None),
        ("0.0025", "provider_reported"),
        (None, "provider_reported_usd"),
    ],
)
def test_cost_requires_explicit_usd_provenance_and_amount(tmp_path, cost, method):
    _, store = _store(tmp_path)
    run = store.create(request())
    store.claim(run["id"], 1, 1.0)
    with pytest.raises(ValueError):
        store.finish(
            run["id"], "succeeded", result={"recommendations": []},
            actual_cost_usd=cost, cost_method=method,
        )
    assert store.get(run["id"])["status"] == "running"
    assert store.get(run["id"])["actual_cost_usd"] is None


def test_verified_conversion_cost_is_preserved(tmp_path):
    _, store = _store(tmp_path)
    run = store.create(request())
    store.claim(run["id"], 1, 1.0)
    stored = store.finish(
        run["id"], "succeeded", result={"schema_version": "1", "recommendations": []},
        actual_cost_usd="0.01", cost_method="verified_conversion",
    )
    assert stored["actual_cost_usd"] == "0.01"
    assert stored["cost_method"] == "verified_conversion"


@pytest.mark.parametrize(
    "result",
    [
        {"candidates": [{"content": "raw provider content"}]},
        {"usageMetadata": {"promptTokenCount": 2}},
        {"recommendations": [{"why_now": {"promptFeedback": "raw"}}]},
        {"provider_payload": {"responseId": "raw"}},
    ],
)
def test_raw_provider_envelopes_are_not_persisted_as_result(tmp_path, result):
    _, store = _store(tmp_path)
    run = store.create(request())
    store.claim(run["id"], 1, 1.0)
    with pytest.raises(ValueError):
        store.finish(run["id"], "succeeded", result=result)
    assert store.get(run["id"])["status"] == "running"
    assert store.get(run["id"])["result"] is None


def test_direct_sql_immutability_and_state_transitions(tmp_path):
    repo, store = _store(tmp_path)
    run = store.create(request())
    statements = [
        ("UPDATE ai_evaluation_runs SET input_json='{}' WHERE id=?", (run["id"],)),
        ("UPDATE ai_evaluation_runs SET markets_json='[]' WHERE id=?", (run["id"],)),
        ("UPDATE ai_evaluation_runs SET provider_id='other' WHERE id=?", (run["id"],)),
        ("UPDATE ai_evaluation_runs SET prompt_version='other' WHERE id=?", (run["id"],)),
        ("UPDATE ai_evaluation_runs SET policy_json='{}' WHERE id=?", (run["id"],)),
        ("UPDATE ai_evaluation_runs SET status='succeeded' WHERE id=?", (run["id"],)),
        ("DELETE FROM ai_evaluation_runs WHERE id=?", (run["id"],)),
    ]
    for sql, params in statements:
        with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, params)
    store.claim(run["id"], 1, 1.0)
    store.finish(run["id"], "succeeded", result={})
    with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE ai_evaluation_runs SET result_json='{}' WHERE id=?", (run["id"],))


def test_evidence_sql_update_and_delete_are_rejected(tmp_path):
    repo, store = _store(tmp_path)
    run = store.create(replace(request(), evidence=(EvidenceRef("ev-1", "2026-09-25", "vn", "a"),)))
    with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE ai_run_evidence SET app_id='b' WHERE run_id=?", (run["id"],))
    with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM ai_run_evidence WHERE run_id=?", (run["id"],))


def test_initialize_seals_preexisting_ai_runs(tmp_path):
    repo, store = _store(tmp_path)
    run = store.create(request())
    with repo._connect() as db:
        db.execute("DROP TRIGGER ai_seal_no_delete")
        db.execute("DELETE FROM ai_run_evidence_seals WHERE run_id=?", (run["id"],))
        db.commit()
    repo.initialize()
    with repo._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO ai_run_evidence(run_id,evidence_id,analysis_date,country,app_id) "
            "VALUES (?,?,?,?,?)",
            (run["id"], "late", "2026-09-25", "vn", "app-2"),
        )


def test_free_tier_reservation_is_durable_and_replay_does_not_spend_again(tmp_path):
    _, store = _store(tmp_path)
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    policy = {"cost_mode": "free_tier", "max_runs_per_day": 5, "reservation_day": today}
    first = None
    for n in range(5):
        run = store.create(replace(request(f"free-{n}"), policy=policy))
        if first is None:
            first = run
        store.finish(run["id"], "failed", error_category="dispatch_failed")
    new_store = EvaluationStore(store.repo)
    assert new_store.free_tier_attempts(today) == 5
    assert new_store.create(replace(request("free-0"), policy=policy))["id"] == first["id"]
    assert new_store.create(replace(request("free-5"), policy=policy))["status"] == "blocked"
    assert new_store.create(replace(request("free-6"), policy=policy))["status"] == "blocked"
    assert new_store.free_tier_attempts(today) == 5
    assert new_store.get(new_store.list_runs()[0]["id"])["error_category"] == "daily_limit_reached"


def test_free_tier_replay_is_valid_after_midnight(tmp_path, monkeypatch):
    from casual_scout.ai import storage

    _, store = _store(tmp_path)
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    item = replace(request(), policy={
        "cost_mode": "free_tier", "max_runs_per_day": 5, "reservation_day": today,
    })
    run = store.create(item)
    real_datetime = storage.datetime

    class Tomorrow(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(storage, "datetime", Tomorrow)
    assert store.create(item)["id"] == run["id"]


def test_free_tier_guardrails_reject_false_dates_and_missing_limits(tmp_path):
    _, store = _store(tmp_path)
    for policy in (
        {"cost_mode": "free_tier", "max_runs_per_day": 5, "reservation_day": "2000-01-01"},
        {"cost_mode": "free_tier", "reservation_day": "2000-01-01"},
        {"cost_mode": "free_tier", "max_runs_per_day": 6},
    ):
        with pytest.raises(ValueError):
            store.create(replace(request(), policy=policy))


def test_blocked_free_tier_record_does_not_use_a_daily_slot(tmp_path):
    _, store = _store(tmp_path)
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    policy = {"cost_mode": "free_tier", "max_runs_per_day": 5, "reservation_day": today}
    blocked = store.create(
        replace(request("blocked"), policy=policy), blocked_reason="provider_not_configured"
    )
    assert blocked["status"] == "blocked"
    assert store.free_tier_attempts(today) == 0
    assert store.create(replace(request("first"), policy=policy))["status"] == "queued"
    assert store.free_tier_attempts(today) == 1


def test_concurrent_final_free_tier_slot_is_reserved_once(tmp_path):
    _, store = _store(tmp_path)
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    policy = {"cost_mode": "free_tier", "max_runs_per_day": 5, "reservation_day": today}
    for n in range(4):
        run = store.create(replace(request(f"prior-{n}"), policy=policy))
        store.finish(run["id"], "failed", error_category="dispatch_failed")
    barrier = Barrier(2)

    def create(key):
        barrier.wait()
        return EvaluationStore(store.repo).create(replace(request(key), policy=policy))["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(create, ["last-a", "last-b"]))
    assert sorted(statuses) == ["blocked", "queued"]
    assert store.free_tier_attempts(today) == 5


def test_concurrent_replay_has_one_row_and_distinct_requests_conflict(tmp_path):
    _, store = _store(tmp_path)
    barrier = Barrier(2)

    def create(key):
        barrier.wait()
        try:
            return EvaluationStore(store.repo).create(request(key))["id"]
        except EvaluationBusy:
            return "busy"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, ["same", "same"]))
    assert outcomes[0] == outcomes[1]
    assert len(store.list_runs()) == 1
    with pytest.raises(EvaluationBusy):
        store.create(request("different"))
