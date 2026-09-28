from __future__ import annotations

from casual_scout.storage.repository import Repository


def test_daily_schedule_is_initialized_and_can_be_enabled(tmp_path) -> None:
    repository = Repository(tmp_path)
    repository.initialize()

    schedule = repository.get_daily_schedule()

    assert schedule == {
        "enabled": False,
        "time": "07:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "country": None,
        "scope": "nearby-us",
        "countries": ["vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"],
        "chart_type": "top-free",
        "last_triggered_local_date": None,
    }

    updated = repository.set_daily_schedule_enabled(True)

    assert updated["enabled"] is True
    assert repository.get_daily_schedule()["enabled"] is True


def test_daily_schedule_date_can_only_be_claimed_once(tmp_path) -> None:
    repository = Repository(tmp_path)
    repository.initialize()

    assert repository.claim_daily_schedule_date("2026-09-22") is True
    assert repository.claim_daily_schedule_date("2026-09-22") is False
    assert repository.claim_daily_schedule_date("2026-09-23") is True
    assert repository.get_daily_schedule()["last_triggered_local_date"] == "2026-09-23"
