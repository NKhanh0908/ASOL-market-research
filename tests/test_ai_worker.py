"""Manual worker dispatch and conservative recovery of durable AI runs."""

import os
import threading
from types import SimpleNamespace

import psutil
from ai_support import FakeProvider, request, seed_ai_evidence

from casual_scout.ai.service import EvaluationEngine
from casual_scout.ai.settings import AISettings
from casual_scout.ai.storage import EvaluationStore
from casual_scout.ai.worker import EvaluationWorker
from casual_scout.models import Chart
from casual_scout.storage import Repository


def _store(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    return repo, EvaluationStore(repo)


def _active_run(tmp_path, *, running=False, owner_pid=None, owner_birth=None):
    repo, store = _store(tmp_path)
    run = store.create(request())
    if running:
        assert store.claim(
            run["id"], owner_pid if owner_pid is not None else os.getpid(),
            owner_birth if owner_birth is not None else psutil.Process().create_time(),
        )
    return repo, store, run


class _NoCallEngine:
    def __init__(self):
        self.calls = 0

    def run(self, run_id):
        self.calls += 1
        raise AssertionError(f"unexpected provider dispatch for {run_id}")


def test_running_run_is_readable_while_provider_waits(tmp_path):
    repo, store = _store(tmp_path)
    seed_ai_evidence(repo)
    entered = threading.Event()
    release = threading.Event()

    def hold_completion():
        entered.set()
        assert release.wait(timeout=10)

    provider = FakeProvider(estimate="0.01", on_complete=hold_completion)
    engine = EvaluationEngine(
        repo, store, AISettings(enabled=True, max_cost_per_run_usd="0.05"), provider,
    )
    run = engine.submit(engine.prepare("2026-09-25", ("vn",)))
    worker = EvaluationWorker(engine, store)
    try:
        worker.submit(run["id"])
        assert entered.wait(timeout=10)
        assert store.get(run["id"])["status"] == "running"
        assert repo.latest_complete(Chart("vn")) is not None
    finally:
        release.set()
        worker.close()
    assert store.get(run["id"])["status"] in {"succeeded", "partial"}
    assert provider.calls == 1


def test_confirmed_dead_running_owner_recovers_without_replaying_input(tmp_path):
    _, store, run = _active_run(
        tmp_path, running=True, owner_pid=2_147_483_647, owner_birth=1.0,
    )
    original_input = run["input"]
    engine = _NoCallEngine()
    worker = EvaluationWorker(engine, store)
    try:
        assert worker.recover_orphans() == 1
        failed = store.get(run["id"])
        assert failed["status"] == "failed"
        assert failed["error_category"] == "interrupted_uncertain"
        assert failed["input"] == original_input
        assert failed["result"] is None
        assert worker.recover_orphans() == 0
        assert engine.calls == 0
    finally:
        worker.close()


def test_confirmed_dead_queued_owner_failed_before_provider_call(tmp_path, monkeypatch):
    _, store = _store(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(
            "casual_scout.ai.storage.os", SimpleNamespace(getpid=lambda: 2_147_483_647),
        )
        run = store.create(request())
    engine = _NoCallEngine()
    worker = EvaluationWorker(engine, store)
    try:
        assert worker.recover_orphans() == 1
        failed = store.get(run["id"])
        assert failed["status"] == "failed"
        assert failed["error_category"] == "dispatch_failed"
        assert failed["actual_cost_usd"] is None
        assert engine.calls == 0
    finally:
        worker.close()


def test_matching_live_owner_remains_active(tmp_path):
    _, store, run = _active_run(tmp_path, running=True)
    worker = EvaluationWorker(_NoCallEngine(), store)
    try:
        assert worker.recover_orphans() == 0
        assert store.get(run["id"])["status"] == "running"
    finally:
        worker.close()


def test_reused_pid_with_different_birth_recovers(tmp_path):
    _, store, run = _active_run(
        tmp_path, running=True, owner_pid=os.getpid(),
        owner_birth=psutil.Process().create_time() - 1000,
    )
    worker = EvaluationWorker(_NoCallEngine(), store)
    try:
        assert worker.recover_orphans() == 1
        assert store.get(run["id"])["error_category"] == "interrupted_uncertain"
    finally:
        worker.close()


def test_recovery_does_not_finish_run_reowned_after_snapshot(tmp_path, monkeypatch):
    _, store, run = _active_run(tmp_path, running=True)
    read_active = store.active

    def stale_snapshot():
        snapshot = read_active()
        snapshot["owner_pid"] = 2_147_483_647
        snapshot["owner_birth"] = 1.0
        return snapshot

    monkeypatch.setattr(store, "active", stale_snapshot)
    worker = EvaluationWorker(_NoCallEngine(), store)
    try:
        assert worker.recover_orphans() == 0
        assert store.get(run["id"])["status"] == "running"
    finally:
        worker.close()


def test_access_denied_is_unknown_and_does_not_recover(tmp_path, monkeypatch):
    _, store, run = _active_run(tmp_path, running=True)
    worker = EvaluationWorker(_NoCallEngine(), store)

    def deny_lookup(pid):
        raise psutil.AccessDenied(pid=pid)

    with monkeypatch.context() as patch:
        patch.setattr("casual_scout.ai.worker.psutil.Process", deny_lookup)
        assert worker.recover_orphans() == 0
    assert store.get(run["id"])["status"] == "running"
    worker.close()


def test_queued_dispatch_failure_is_terminal_without_billing_uncertainty(tmp_path, monkeypatch):
    _, store, run = _active_run(tmp_path)
    engine = _NoCallEngine()
    worker = EvaluationWorker(engine, store)

    def fail_submit(*args, **kwargs):
        raise RuntimeError("executor rejected dispatch")

    with monkeypatch.context() as patch:
        patch.setattr(worker._executor, "submit", fail_submit)
        worker.submit(run["id"])
    failed = store.get(run["id"])
    assert failed["status"] == "failed"
    assert failed["error_category"] == "dispatch_failed"
    assert failed["actual_cost_usd"] is None
    assert engine.calls == 0
    worker.close()


def test_unexpected_task_interruption_is_inspectable_and_not_retried(tmp_path):
    _, store, run = _active_run(tmp_path)

    class InterruptedEngine:
        def __init__(self):
            self.calls = 0

        def run(self, run_id):
            self.calls += 1
            assert store.claim(run_id, os.getpid(), psutil.Process().create_time())
            raise RuntimeError("worker interrupted")

    engine = InterruptedEngine()
    worker = EvaluationWorker(engine, store)
    worker.submit(run["id"])
    worker.close()
    failed = store.get(run["id"])
    assert failed["status"] == "failed"
    assert failed["error_category"] == "interrupted_uncertain"
    assert engine.calls == 1


def test_background_base_exception_does_not_strand_live_owner(tmp_path):
    _, store, run = _active_run(tmp_path)

    class InterruptedEngine:
        def run(self, run_id):
            assert store.claim(run_id, os.getpid(), psutil.Process().create_time())
            raise SystemExit("background task stopped")

    worker = EvaluationWorker(InterruptedEngine(), store)
    worker.submit(run["id"])
    worker.close()
    failed = store.get(run["id"])
    assert failed["status"] == "failed"
    assert failed["error_category"] == "interrupted_uncertain"


def test_exception_after_another_owner_claims_does_not_fail_their_run(tmp_path):
    _, store, run = _active_run(tmp_path)

    class RacingEngine:
        def run(self, run_id):
            assert store.claim(run_id, 2_147_483_647, 1.0)
            raise RuntimeError("first handler lost the claim race")

    worker = EvaluationWorker(RacingEngine(), store)
    worker.submit(run["id"])
    worker.close()
    active = store.get(run["id"])
    assert active["status"] == "running"
    assert active["owner_pid"] == 2_147_483_647
    assert active["owner_birth"] == 1.0
