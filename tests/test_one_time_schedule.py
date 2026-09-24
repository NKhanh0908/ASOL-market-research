from __future__ import annotations

from datetime import UTC, datetime

from casual_scout.operations.daily_scheduler import DailyScheduler
from casual_scout.storage import Repository


def test_one_time_schedule_is_persisted_and_claimed_only_once(tmp_path) -> None:
    repository = Repository(tmp_path)
    repository.initialize()
    due_at = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)

    schedule = repository.schedule_one_time_collection(due_at, "2026-09-24T15:00")

    assert schedule["status"] == "pending"
    assert schedule["scheduled_for_local"] == "2026-09-24T15:00"
    assert repository.claim_due_one_time_collection(due_at) is not None
    assert repository.claim_due_one_time_collection(due_at) is None
    assert repository.get_one_time_collection()["status"] == "triggered"


def test_scheduler_launches_one_time_ios_collection_at_due_time(tmp_path) -> None:
    repository = Repository(tmp_path)
    repository.initialize()
    due_at = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
    repository.schedule_one_time_collection(due_at, "2026-09-24T15:00")
    launched: list[str] = []
    scheduler = DailyScheduler(
        repository,
        launch=lambda run_id, _data_dir: launched.append(run_id) or 42,
        now=lambda: due_at,
    )

    run_id = scheduler.check_once()

    assert run_id == launched[0]
    assert repository.get_one_time_collection()["run_id"] == run_id
    assert scheduler.check_once() == "disabled"
