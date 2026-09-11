from __future__ import annotations

import os
from contextlib import closing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import psutil

from casual_scout.models import Chart

if TYPE_CHECKING:
    from casual_scout.collection.jobs import JobService
    from casual_scout.storage import Repository


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class Collector:
    def __init__(self, repo: Repository, provider: Any, jobs: JobService) -> None:
        self.repo = repo
        self.provider = provider
        self.jobs = jobs

    def execute(self, run_id: str, enrich: bool = True) -> str:
        pid = os.getpid()
        try:
            created_at = psutil.Process(pid).create_time()
        except (psutil.Error, OSError):
            created_at = datetime.now(UTC).timestamp()

        if not self.jobs.claim(run_id, pid, created_at):
            with closing(self.repo._connect()) as conn:
                r = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
                return str(r["status"]) if r else "failed"

        try:
            with closing(self.repo._connect()) as conn:
                market_runs = conn.execute(
                    """
                    SELECT mr.id, mr.chart_id, c.country, m.source_status, m.source_note
                    FROM market_runs mr
                    JOIN charts c ON c.id = mr.chart_id
                    JOIN markets m ON m.country = c.country
                    WHERE mr.run_id = ?
                    ORDER BY c.country ASC
                    """,
                    (run_id,),
                ).fetchall()

            for mr in market_runs:
                self.jobs.heartbeat(run_id)
                mr_id = str(mr["id"])
                country = str(mr["country"])
                source_status = str(mr["source_status"])
                source_note = mr["source_note"]

                if source_status == "unverified":
                    now = _utc_text(datetime.now(UTC))
                    with self.repo._write_connection() as conn:
                        conn.execute(
                            """
                            UPDATE market_runs
                            SET chart_status = 'failed', enrichment_status = 'failed',
                                error = ?, ended_at = ?
                            WHERE id = ?
                            """,
                            (source_note or "Apple source not verified", now, mr_id),
                        )
                    continue

                chart = Chart(country)
                http_result, parsed = self.provider.fetch_chart(chart)

                snapshot_id: str | None = None
                if http_result.body is not None:
                    snapshot_id = self.repo.save_snapshot(run_id, http_result, parsed)

                if enrich and parsed.quality != "invalid" and snapshot_id is not None:
                    app_ids = [entry.app_id for entry in parsed.entries]
                    now_dt = datetime.now(UTC)
                    cached = self.repo.cached_metadata(country, app_ids, now_dt)
                    missing = [aid for aid in app_ids if aid not in cached]

                    # Fetch in batches of up to 20
                    for i in range(0, len(missing), 20):
                        self.jobs.heartbeat(run_id)
                        chunk = missing[i : i + 20]
                        lookup_res, lookup_data = self.provider.fetch_metadata(country, chunk)
                        if lookup_res.body is not None and lookup_data:
                            self.repo.save_metadata(country, lookup_data, lookup_res)

                    all_versions = self.repo.cached_metadata(country, app_ids, datetime.now(UTC))
                    if all_versions:
                        self.repo.bind_metadata(snapshot_id, all_versions)

                    if len(all_versions) == len(app_ids) and len(app_ids) > 0:
                        enrich_status = "complete"
                    elif len(all_versions) > 0:
                        enrich_status = "partial"
                    else:
                        enrich_status = "failed"

                    with self.repo._write_connection() as conn:
                        conn.execute(
                            "UPDATE market_runs SET enrichment_status = ? WHERE id = ?",
                            (enrich_status, mr_id),
                        )
                elif not enrich:
                    with self.repo._write_connection() as conn:
                        conn.execute(
                            "UPDATE market_runs SET enrichment_status = 'not_requested' WHERE id = ?",
                            (mr_id,),
                        )

            # Determine final status
            with closing(self.repo._connect()) as conn:
                mrs = conn.execute(
                    "SELECT chart_status, enrichment_status FROM market_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchall()

            complete_count = sum(1 for m in mrs if m["chart_status"] == "complete")
            all_succeeded = all(
                m["chart_status"] == "complete"
                and m["enrichment_status"] in ("complete", "not_requested")
                for m in mrs
            )

            if all_succeeded and len(mrs) > 0:
                final_status = "succeeded"
            elif complete_count == 0:
                final_status = "failed"
            else:
                final_status = "partial"

            self.jobs.finish(run_id, final_status)
            return final_status

        except Exception as err:
            self.jobs.finish(run_id, "interrupted", {"error": str(err)})
            raise
