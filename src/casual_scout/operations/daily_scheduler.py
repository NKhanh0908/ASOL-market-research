from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from casual_scout.collection.jobs import JobService

_VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
_CHECK_INTERVAL_SECONDS = 30.0


class DailyScheduler:
    """Small in-process scheduler for the fixed daily Vietnam collection."""

    def __init__(
        self,
        repository,
        launch: Callable[[str, Path], int],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.launch = launch
        self.now = now or (lambda: datetime.now(UTC))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="casual-scout-daily-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=_CHECK_INTERVAL_SECONDS + 1)
        self._thread = None

    def check_once(self) -> str:
        schedule = self.repository.get_daily_schedule()
        if not schedule["enabled"]:
            return "disabled"

        now_local = self.now().astimezone(_VIETNAM)
        if (now_local.hour, now_local.minute) != (7, 0):
            return "not_due"

        if self._has_active_run():
            return "active_run"

        local_date = now_local.date().isoformat()
        if not self.repository.claim_daily_schedule_date(local_date):
            return "already_triggered"

        run_id = JobService(self.repository).submit(
            "daily",
            [str(schedule["country"])],
            f"daily-{schedule['country']}-{local_date}",
            chart_types=[str(schedule["chart_type"])],
        )
        self.launch(run_id, self.repository.data_dir)
        return run_id

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(_CHECK_INTERVAL_SECONDS)

    def _has_active_run(self) -> bool:
        with closing(self.repository._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM runs WHERE status IN ('queued', 'running') LIMIT 1"
            ).fetchone()
        return row is not None
