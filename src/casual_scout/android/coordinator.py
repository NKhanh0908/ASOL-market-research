from __future__ import annotations

import logging
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime

import psutil

from casual_scout.android.storage import AndroidStore
from casual_scout.collection.jobs import _is_process_alive
from casual_scout.operations.daily_scheduler import DailyScheduler

LOG = logging.getLogger(__name__)


def launch_android(job_id, data_dir):
    logs = data_dir.resolve() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"android-{job_id}.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "casual_scout.android.worker",
                "--run-id",
                job_id,
                "--data-dir",
                str(data_dir.resolve()),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    return process.pid


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
        recover_android(self.store)
        try:
            result = super().check_once()
        except Exception:
            LOG.exception("iOS scheduler tick failed")
            result = "ios_error"
        self.store.enqueue_daily(self.now())
        dispatch_pending(self.store, self.android_launcher)
        return result

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                LOG.exception("Collection coordinator tick failed")
            self._stop_event.wait(2)
