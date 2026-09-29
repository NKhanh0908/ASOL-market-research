"""HTTP Android collection; all storage writes stay on the coordinating thread."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import closing
from datetime import UTC, datetime

import psutil

from casual_scout.models import Chart


class AndroidCollector:
    def __init__(self, repo, provider, jobs):
        self.repo, self.provider, self.jobs = repo, provider, jobs
        self.heartbeat_interval = 5

    def _wait(self, pool, run_id, function, *args):
        future = pool.submit(function, *args)
        while True:
            try:
                return future.result(timeout=self.heartbeat_interval)
            except TimeoutError:
                if future.done():
                    return future.result()
                self.jobs.heartbeat(run_id)

    def execute(self, run_id, enrich=True, on_progress=None):
        pid = os.getpid()
        try:
            created = psutil.Process(pid).create_time()
        except (psutil.Error, OSError):
            created = datetime.now(UTC).timestamp()
        if not self.jobs.claim(run_id, pid, created):
            with closing(self.repo._connect()) as conn:
                row = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
                return str(row["status"]) if row else "failed"
        try:
            with closing(self.repo._connect()) as conn:
                markets = conn.execute(
                    """SELECT mr.id, c.provider, c.platform, c.country,
                    c.collection, c.genre, c.depth, c.version FROM market_runs mr
                    JOIN charts c ON c.id=mr.chart_id WHERE mr.run_id=?
                    ORDER BY c.country,c.collection""",
                    (run_id,),
                ).fetchall()
            with ThreadPoolExecutor(max_workers=1) as pool:
                for index, market in enumerate(markets, 1):
                    self.jobs.heartbeat(run_id)
                    if on_progress:
                        on_progress(
                            f"[{index}/{len(markets)}] {market['country'].upper()} {market['collection']}: loading Google Play"
                        )
                    chart = Chart(
                        country=market["country"],
                        provider=market["provider"],
                        platform=market["platform"],
                        genre=market["genre"],
                        depth=market["depth"],
                        version=market["version"],
                        feed_type=market["collection"],
                    )
                    try:
                        result, parsed = self._wait(pool, run_id, self.provider.fetch_chart, chart)
                    except Exception as error:  # noqa: BLE001 - provider failures must preserve other charts.
                        with self.repo._write_connection() as conn:
                            conn.execute(
                                "UPDATE market_runs SET chart_status='failed', enrichment_status=?, error=?, ended_at=? WHERE id=?",
                                (
                                    "failed" if enrich else "not_requested",
                                    str(error),
                                    datetime.now(UTC).isoformat(),
                                    market["id"],
                                ),
                            )
                        continue
                    snapshot = (
                        self.repo.save_snapshot(run_id, result, parsed)
                        if result.body is not None
                        else None
                    )
                    if snapshot is None:
                        self._record_bodyless(result, run_id, market["id"], "chart")
                        with self.repo._write_connection() as conn:
                            conn.execute(
                                "UPDATE market_runs SET chart_status='failed', error=? WHERE id=?",
                                (result.error or "empty chart response", market["id"]),
                            )
                    status = "not_requested" if not enrich else "failed"
                    if enrich and snapshot and parsed.quality != "invalid":
                        packages = [entry.app_id for entry in parsed.entries]
                        cached = self.repo.cached_metadata(
                            chart.country,
                            packages,
                            datetime.now(UTC),
                            provider="google",
                            platform="android",
                        )
                        self.repo.bind_metadata(snapshot, cached)
                        missing = [package for package in packages if package not in cached]
                        if on_progress:
                            on_progress(
                                f"  {len(parsed.entries)} ranks; {len(cached)} cached, {len(missing)} details needed"
                            )
                        for offset in range(0, len(missing), 10):
                            batch = missing[offset : offset + 10]
                            try:
                                if hasattr(self.provider, "iter_metadata"):
                                    stream = self.provider.iter_metadata(chart.country, batch)
                                    sentinel = object()
                                    while True:
                                        item = self._wait(pool, run_id, next, stream, sentinel)
                                        if item is sentinel:
                                            break
                                        self._save_metadata(
                                            snapshot, chart.country, item, run_id, market["id"]
                                        )
                                        self.jobs.heartbeat(run_id)
                                else:
                                    items = self._wait(
                                        pool,
                                        run_id,
                                        self.provider.fetch_metadata,
                                        chart.country,
                                        batch,
                                    )
                                    for item in items:
                                        self._save_metadata(
                                            snapshot, chart.country, item, run_id, market["id"]
                                        )
                                        self.jobs.heartbeat(run_id)
                            except Exception as error:  # noqa: BLE001 - provider failures must preserve other charts.
                                with self.repo._write_connection() as conn:
                                    conn.execute(
                                        "UPDATE market_runs SET error=? WHERE id=?",
                                        (str(error), market["id"]),
                                    )
                            self.jobs.heartbeat(run_id)
                        bound = self.repo.get_snapshot_metadata(snapshot)
                        count = sum(
                            1
                            for package in packages
                            if bound.get(package, {}).get("status") == "complete"
                        )
                        status = "complete" if packages and count == len(packages) else "partial"
                    with self.repo._write_connection() as conn:
                        conn.execute(
                            "UPDATE market_runs SET enrichment_status=? WHERE id=?",
                            (status, market["id"]),
                        )
                    self.jobs.heartbeat(run_id)
            with closing(self.repo._connect()) as conn:
                rows = conn.execute(
                    "SELECT chart_status,enrichment_status,valid_count FROM market_runs WHERE run_id=?",
                    (run_id,),
                ).fetchall()
            all_complete = rows and all(
                row["chart_status"] == "complete"
                and row["enrichment_status"] in ("complete", "not_requested")
                for row in rows
            )
            status = (
                "succeeded"
                if all_complete
                else ("partial" if any(row["valid_count"] > 0 for row in rows) else "failed")
            )
            self.jobs.finish(run_id, status)
            return status
        except BaseException as error:
            self.jobs.finish(run_id, "interrupted", {"error": str(error)})
            raise

    def _save_metadata(self, snapshot, country, item, run_id, market_run_id):
        result, values = item
        if result.body is not None and values:
            versions = self.repo.save_metadata(
                country, values, result, provider="google", platform="android"
            )
            self.repo.bind_metadata(snapshot, versions)

        if result.body is None:
            self._record_bodyless(result, run_id, market_run_id, "metadata")

    def _record_bodyless(self, result, run_id, market_run_id, kind):
        records = []
        for attempt in (*result.attempts, result):
            if attempt.body is not None:
                digest, path = self.repo._raw.put(attempt.body)
            else:
                digest, path = None, None
            records.append((attempt, digest, path))
        with self.repo._write_connection() as conn:
            self.repo._insert_raw_records(conn, records)
            self.repo._insert_observations(conn, result, records, run_id, market_run_id)
            conn.execute(
                "UPDATE market_runs SET error=COALESCE(error || '; ', '') || ? WHERE id=?",
                (result.error or f"empty {kind} response", market_run_id),
            )
