from __future__ import annotations

import logging
from contextlib import closing
from datetime import UTC, datetime

import psutil

from casual_scout.android.storage import AndroidStore
from casual_scout.collection.jobs import JobService, _is_process_alive
from casual_scout.operations.daily_scheduler import DailyScheduler

LOG = logging.getLogger(__name__)


def launch_android(job_id, data_dir):
    """Compatibility launcher for new core Android runs; archives remain read-only."""
    from casual_scout.collection.processes import launch_pipeline
    from casual_scout.storage import Repository

    repo = Repository(data_dir)
    with closing(repo._connect()) as db:
        rows = db.execute(
            "SELECT DISTINCT c.platform FROM market_runs m JOIN charts c ON c.id=m.chart_id WHERE m.run_id=?",
            (job_id,),
        ).fetchall()
    if len(rows) != 1 or rows[0]["platform"] != "android":
        raise ValueError("Archived Android jobs are read-only")
    return launch_pipeline(job_id, data_dir)


def dispatch_pending(store, launcher=launch_android):
    job_id = store.dispatch()
    if not job_id:
        return None
    try:
        pid = launcher(job_id, store.repo.data_dir)
        if pid is not None:
            store.record_process(job_id, pid, psutil.Process(pid).create_time())
    except Exception as error:
        LOG.exception("Android worker launch failed")
        store.finish(job_id, "failed", f"Không khởi động được worker: {error}")
    return job_id


def recover_android(store):
    with closing(store.repo._connect()) as db:
        rows = db.execute(
            "SELECT * FROM android_jobs WHERE status IN ('queued','running')"
        ).fetchall()
    for row in rows:
        if row["pid"] is not None:
            dead = not _is_process_alive(row["pid"], row["process_created"])
        else:
            age = (datetime.now(UTC) - datetime.fromisoformat(row["dispatched_at"])).total_seconds()
            dead = age > 120
        if dead:
            store.finish(
                row["id"],
                "interrupted",
                "Worker đã dừng; các batch đã lưu vẫn còn. Bấm crawl để thử lại.",
            )


class AndroidCoordinator(DailyScheduler):
    """Keep iOS daily + one-time behavior; dispatch queued Android after iOS."""

    def __init__(self, repository, launch, now=None, android_launcher=launch_android):
        super().__init__(repository, launch, now)
        self.store = AndroidStore(repository)
        self.android_launcher = android_launcher

    def check_once(self):
        JobService(self.repository).recover_dead_processes()
        recover_android(self.store)
        try:
            result = super().check_once()
        except Exception:
            LOG.exception("iOS scheduler tick failed")
            result = "ios_error"
        now = self.now()
        today_utc = now.astimezone(UTC).date().isoformat()
        if getattr(self, "_last_retention_date_utc", None) != today_utc:
            try:
                from casual_scout.operations.retention import RetentionService

                RetentionService(self.repository.data_dir).apply_retention()
                self._last_retention_date_utc = today_utc
            except Exception:
                LOG.exception("Daily retention sweep failed")

        from zoneinfo import ZoneInfo

        local_date = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        jobs = JobService(self.repository)
        run_id = jobs.submit_scheduled_android(local_date, now)
        if run_id:
            jobs.launch(run_id, self.android_launcher)
        return result

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                LOG.exception("Collection coordinator tick failed")
            self._stop_event.wait(2)
