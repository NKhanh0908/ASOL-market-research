from __future__ import annotations

from datetime import UTC, datetime

from casual_scout.operations.daily_scheduler import DailyScheduler
from casual_scout.storage import Repository


def test_daily_scheduler_launches_once_at_seven_am_vietnam_time(tmp_path) -> None:
    repository = Repository(tmp_path)
    repository.initialize()
    repository.set_daily_schedule_enabled(True)
    launched: list[str] = []
    scheduler = DailyScheduler(
        repository,
        launch=lambda run_id, _data_dir: launched.append(run_id) or 123,
        now=lambda: datetime(2026, 9, 22, 0, 0, tzinfo=UTC),
    )

    run_id = scheduler.check_once()
    assert run_id == launched[0]
    assert len(launched) == 1
    assert scheduler.check_once() == "active_run"
    assert len(launched) == 1


def test_daily_scheduler_does_not_backfill_or_overlap_an_active_run(tmp_path) -> None:
    repository = Repository(tmp_path)
    repository.initialize()
    repository.set_daily_schedule_enabled(True)
    launched: list[str] = []

    late_scheduler = DailyScheduler(
        repository,
        launch=lambda run_id, _data_dir: launched.append(run_id) or 123,
        now=lambda: datetime(2026, 9, 22, 0, 1, tzinfo=UTC),
    )
    assert late_scheduler.check_once() == "not_due"

    with repository._write_connection() as connection:
        connection.execute(
            """
            INSERT INTO runs (id, request_key, "trigger", status, started_at, summary_json)
            VALUES ('active-run', 'active-run-key', 'manual', 'running', '2026-09-21T00:00:00Z', '{}')
            """
        )
    due_scheduler = DailyScheduler(
        repository,
        launch=lambda run_id, _data_dir: launched.append(run_id) or 123,
        now=lambda: datetime(2026, 9, 22, 0, 0, tzinfo=UTC),
    )

    assert due_scheduler.check_once() == "active_run"
    assert launched == []
    assert repository.get_daily_schedule()["last_triggered_local_date"] is None
