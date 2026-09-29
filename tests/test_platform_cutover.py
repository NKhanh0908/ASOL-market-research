from datetime import UTC, datetime

import pytest

from casual_scout.collection.jobs import JobService
from casual_scout.storage import Repository


def test_scope_and_launch_claim(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)
    run = jobs.submit("manual", ["vn"], "key", platform="android")
    with pytest.raises(ValueError):
        jobs.submit("manual", ["us"], "key", platform="android")
    assert jobs.claim_launch(run)
    assert not jobs.claim_launch(run)


def test_android_schedule_atomic(tmp_path):
    from casual_scout.android.storage import AndroidStore

    repo = Repository(tmp_path)
    repo.initialize()
    store = AndroidStore(repo)
    store.initialize()
    store.set_schedule(True)
    jobs = JobService(repo)
    now = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    run = jobs.submit_scheduled_android("2026-09-29", now)
    assert run
    assert jobs.submit_scheduled_android("2026-09-29", now) is None
    with repo._connect() as db:
        assert (
            db.execute("SELECT count(*) FROM market_runs WHERE run_id=?", (run,)).fetchone()[0]
            == 18
        )


def test_abandoned_launch_recovered_before_new_submit(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)
    old = jobs.submit("manual", ["vn"], "old", platform="android")
    assert jobs.claim_launch(old)
    with repo._write_connection() as db:
        db.execute("UPDATE runs SET launch_claimed_at='2000-01-01T00:00:00Z' WHERE id=?", (old,))
    new = jobs.submit("manual", ["us"], "new", platform="android")
    assert new != old
    with repo._connect() as db:
        assert (
            db.execute("SELECT status FROM runs WHERE id=?", (old,)).fetchone()[0] == "interrupted"
        )


def test_http_dispatch_and_app_do_not_import_selenium(tmp_path, monkeypatch):
    import builtins

    from casual_scout.collection import platforms
    from casual_scout.config import Settings
    from casual_scout.web.app import create_app
    from tests.test_android_core_collection import Fake

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "selenium" or name.startswith("selenium."):
            raise AssertionError("browser dependency remains in runtime")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(platforms, "GooglePlayProvider", lambda transport: Fake())
    repo = Repository(tmp_path)
    repo.initialize()
    run = JobService(repo).submit(
        "manual", ["vn"], "guard", ["top-free", "top-grossing"], platform="android"
    )
    assert platforms.execute_run(repo, run) == "partial"
    assert create_app(Settings(tmp_path))
