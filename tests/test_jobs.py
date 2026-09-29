import os
from pathlib import Path

import pytest

from casual_scout.collection.jobs import CollectionBusyError, JobService
from casual_scout.storage import Repository


def test_submit_creates_queued_run(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)

    run_id = jobs.submit("manual", ["vn", "us"], "request-1")
    assert run_id is not None

    with repo._connect() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        assert run["trigger"] == "manual"
        assert run["status"] == "queued"
        assert run["request_key"] == "request-1"

        market_runs = conn.execute(
            "SELECT * FROM market_runs WHERE run_id = ?", (run_id,)
        ).fetchall()
        assert len(market_runs) == 2


def test_submit_duplicate_request_key_returns_existing_run(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)

    run1 = jobs.submit("manual", ["vn"], "req-key")
    run2 = jobs.submit("manual", ["vn"], "req-key")
    assert run1 == run2


def test_submit_while_active_run_returns_active_run(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)

    run1 = jobs.submit("manual", ["vn"], "req-key-1")
    with pytest.raises(CollectionBusyError):
        jobs.submit("manual", ["us"], "req-key-2")
    assert jobs.submit("manual", ["vn"], "req-key-3") == run1


def test_claim_and_heartbeat_and_finish(tmp_path: Path):
    import psutil
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)

    run_id = jobs.submit("manual", ["vn"], "req-key")
    pid = os.getpid()
    created_at = psutil.Process(pid).create_time()

    claimed = jobs.claim(run_id, pid, created_at)
    assert claimed is True

    with repo._connect() as conn:
        run = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        assert run["status"] == "running"
        lock = conn.execute("SELECT * FROM collector_lock WHERE id = 1").fetchone()
        assert lock["run_id"] == run_id
        assert lock["pid"] == pid

    jobs.heartbeat(run_id)

    jobs.finish(run_id, "succeeded")
    with repo._connect() as conn:
        run = conn.execute("SELECT status, ended_at FROM runs WHERE id = ?", (run_id,)).fetchone()
        assert run["status"] == "succeeded"
        assert run["ended_at"] is not None
        lock = conn.execute("SELECT * FROM collector_lock WHERE id = 1").fetchone()
        assert lock is None


def test_concurrent_claim_fails_for_second_process(tmp_path: Path):
    import psutil
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)

    run_id = jobs.submit("manual", ["vn"], "req-key")
    pid = os.getpid()
    created_at = psutil.Process(pid).create_time()

    assert jobs.claim(run_id, pid, created_at) is True
    assert jobs.claim(run_id, pid + 100, created_at) is False


def test_recover_dead_processes(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)

    run_id = jobs.submit("manual", ["vn"], "req-key")
    # Simulate a dead process (PID 99999999 which does not exist)
    dead_pid = 9999999
    dead_created = 1000000.0

    claimed = jobs.claim(run_id, dead_pid, dead_created)
    assert claimed is True

    recovered = jobs.recover_dead_processes()
    assert run_id in recovered

    with repo._connect() as conn:
        run = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        assert run["status"] == "interrupted"
        lock = conn.execute("SELECT * FROM collector_lock WHERE id = 1").fetchone()
        assert lock is None
