from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

import psutil

from casual_scout.android.storage import AndroidStore
from casual_scout.collection.jobs import JobService
from casual_scout.storage import Repository

BATCH_SIZE = 5
LOG = logging.getLogger(__name__)


def collect(store, job_id, provider_factory=None):
    if provider_factory is None:
        from contextlib import closing

        from casual_scout.collection.platforms import execute_run

        with closing(store.repo._connect()) as db:
            rows = db.execute(
                "SELECT DISTINCT c.platform FROM market_runs m JOIN charts c ON c.id=m.chart_id WHERE m.run_id=?",
                (job_id,),
            ).fetchall()
        if len(rows) != 1 or rows[0]["platform"] != "android":
            raise ValueError("Archived Android jobs are read-only; submit a new core HTTP run")
        return execute_run(store.repo, job_id)
    jobs = JobService(store.repo)
    pid = os.getpid()
    created = psutil.Process(pid).create_time()
    if not jobs.claim(job_id, pid, created):
        store.finish(job_id, "failed", "Không lấy được khóa collector; chưa crawl.")
        return "failed"
    store.started(job_id, pid, created)
    deadline = time.monotonic() + 900
    try:
        with provider_factory(
            store.repo.data_dir.resolve() / "android-evidence" / job_id
        ) as provider:
            for feed in ("top-free", "top-grossing"):
                store.phase(job_id, feed)
                try:
                    entries, evidence = provider.chart(feed)
                    store.save_chart(job_id, feed, entries, evidence)
                except Exception as error:
                    LOG.exception("Android chart failed: %s", feed)
                    store.add_error(job_id, f"{feed}: {type(error).__name__}: {str(error)[:500]}")
                jobs.heartbeat(job_id)
            entries = store.view(job_id)["entries"]
            store.phase(job_id, "metadata")
            for start in range(0, len(entries), BATCH_SIZE):
                if time.monotonic() > deadline:
                    store.add_error(job_id, "Đã hết ngân sách 15 phút; giữ các batch hoàn tất.")
                    break
                results = []
                for row in entries[start : start + BATCH_SIZE]:
                    if time.monotonic() > deadline:
                        store.add_error(job_id, "Dừng metadata do hết ngân sách thời gian.")
                        break
                    try:
                        result = store.cached_metadata(row["package"]) or provider.metadata(
                            row["package"]
                        )
                    except Exception as error:
                        LOG.exception("Android metadata failed: %s", row["package"])
                        result = {
                            "package": row["package"],
                            "metadata_status": "failed",
                            "metadata_error": f"{type(error).__name__}: {str(error)[:500]}",
                        }
                    results.append(result)
                    jobs.heartbeat(job_id)
                if results:
                    store.save_batch(job_id, results)
        view = store.view(job_id)
        if not view["entries"]:
            status = "failed"
        elif view["job"]["errors"] or any(
            r["metadata_status"] not in ("complete", "cached") for r in view["entries"]
        ):
            status = "partial"
        else:
            status = "succeeded"
        store.finish(job_id, status)
        return status
    except Exception as error:
        LOG.exception("Android run failed")
        status = "partial" if store.view(job_id)["entries"] else "failed"
        store.finish(job_id, status, f"{type(error).__name__}: {str(error)[:500]}")
        return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Internal Android worker")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Repository(args.data_dir)
    repo.initialize()
    store = AndroidStore(repo)
    store.initialize()
    status = collect(store, args.run_id)
    print(f"Android {args.run_id}: {status}", flush=True)
    raise SystemExit(0 if status in ("succeeded", "partial") else 1)
