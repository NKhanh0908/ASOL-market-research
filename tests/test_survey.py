from datetime import UTC, datetime
from pathlib import Path

from casual_scout.operations.survey import (
    reconcile_slots,
    run_survey,
    survey_report,
    survey_slots,
)
from casual_scout.storage import Repository


def test_four_utc_slots():
    start = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)
    slots = survey_slots(start, end)
    assert [t.hour for t in slots] == [0, 6, 12, 18]


def test_reconcile_slots_marks_missed_and_returns_current(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()

    # Suppose system is started at 2026-09-10 12:15 UTC (inside 12:00 window, 00:00 and 06:00 missed)
    start_time = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    now_time = datetime(2026, 9, 10, 12, 15, tzinfo=UTC)

    current_slot = reconcile_slots(repo, now_time, survey_start=start_time)
    assert current_slot == datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    with repo._connect() as conn:
        missed = conn.execute(
            "SELECT slot_utc FROM survey_slots WHERE status = 'missed' ORDER BY slot_utc ASC"
        ).fetchall()
        assert len(missed) == 2
        assert "2026-09-10T00:00:00Z" in missed[0]["slot_utc"]
        assert "2026-09-10T06:00:00Z" in missed[1]["slot_utc"]


def test_reconcile_slots_outside_window_marks_all_missed(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()

    # 13:00 UTC is outside the 30-min window for 12:00 (which closed at 12:30)
    start_time = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    now_time = datetime(2026, 9, 10, 13, 0, tzinfo=UTC)

    current_slot = reconcile_slots(repo, now_time, survey_start=start_time)
    assert current_slot is None

    with repo._connect() as conn:
        missed = conn.execute(
            "SELECT slot_utc FROM survey_slots WHERE status = 'missed'"
        ).fetchall()
        assert len(missed) == 3


def test_survey_report_empty_returns_structure(tmp_path: Path):
    repo = Repository(tmp_path)
    repo.initialize()

    start = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
    report = survey_report(repo, start, end)

    assert "slots" in report
    assert "summary" in report
    assert report["summary"]["total_slots"] == 28
    assert report["summary"]["observed_count"] == 0


def test_run_survey_executes_without_enrichment(collection_fixture):
    repo, provider, _jobs, _collector = collection_fixture
    now_time = datetime(2026, 9, 10, 0, 10, tzinfo=UTC)

    run_id, status = run_survey(
        repo, provider, now=now_time, survey_start=datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    )
    assert status == "succeeded"
    assert provider.lookup_call_count == 0

    with repo._connect() as conn:
        slot = conn.execute(
            "SELECT * FROM survey_slots WHERE slot_utc = '2026-09-10T00:00:00Z'"
        ).fetchone()
        assert slot is not None
        assert slot["status"] == "observed"
        assert slot["run_id"] == run_id
