"""Android collector implementation using HTTP Google Play provider and core storage."""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import os
from typing import TYPE_CHECKING, Any, Callable

import psutil

from casual_scout.models import Chart

if TYPE_CHECKING:
    from casual_scout.collection.jobs import JobService
    from casual_scout.providers.google import GooglePlayProvider
    from casual_scout.storage import Repository


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class AndroidCollector:
    """Core collector for Google Play Store Android charts and apps."""

    def __init__(
        self,
        repo: Repository,
        provider: GooglePlayProvider,
        jobs: JobService,
    ) -> None:
        self.repo = repo
        self.provider = provider
        self.jobs = jobs

    def execute(
        self,
        run_id: str,
        enrich: bool = True,
        on_progress: Callable[[str], None] | None = None,
    ) -> str:
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
                    SELECT mr.id, mr.chart_id, c.provider, c.platform, c.country,
                           c.collection, c.genre, c.depth, c.version
                    FROM market_runs mr
                    JOIN charts c ON c.id = mr.chart_id
                    WHERE mr.run_id = ?
                    ORDER BY c.country ASC, c.collection ASC
                    """,
                    (run_id,),
                ).fetchall()

            total_mr = len(market_runs)
            for idx, mr in enumerate(market_runs, 1):
                self.jobs.heartbeat(run_id)
                mr_id = str(mr["id"])
                country = str(mr["country"])
                feed_type = str(mr["collection"])
                feed_label = "Top Grossing" if "grossing" in feed_type.lower() else "Top Free"

                if on_progress:
                    on_progress(f"[{idx}/{total_mr}] 🤖 {country.upper()} — {feed_label} Casual: Đang tải bảng xếp hạng Google Play...")

                chart = Chart(
                    country=country,
                    provider="google",
                    platform="android",
                    genre="GAME_CASUAL",
                    depth=int(mr["depth"]),
                    version=int(mr["version"]),
                    feed_type=feed_type,
                )

                http_result, parsed = self.provider.fetch_chart(chart)

                snapshot_id: str | None = None
                if http_result.body is not None:
                    snapshot_id = self.repo.save_snapshot(run_id, http_result, parsed)

                if on_progress:
                    on_progress(f"    ✓ Nhận {len(parsed.entries)} game (chất lượng: {parsed.quality})")

                if enrich and parsed.quality != "invalid" and snapshot_id is not None:
                    packages = [entry.app_id for entry in parsed.entries]
                    now_dt = datetime.now(UTC)

                    cached = self.repo.cached_metadata(
                        country, packages, now_dt, provider="google", platform="android"
                    )
                    missing = [p for p in packages if p not in cached]

                    if cached:
                        self.repo.bind_metadata(snapshot_id, cached)

                    if missing:
                        if on_progress:
                            on_progress(
                                f"    ⏳ Làm giàu metadata & số lượt tải ({len(missing)} game mới, {len(cached)} từ cache)..."
                            )
                        # Fetch and save metadata batch by batch
                        for meta_res, meta_data in self.provider.fetch_metadata(country, missing):
                            if meta_res.body is not None and meta_data:
                                new_versions = self.repo.save_metadata(
                                    country,
                                    meta_data,
                                    meta_res,
                                    provider="google",
                                    platform="android",
                                )
                                self.repo.bind_metadata(snapshot_id, new_versions)
                            self.jobs.heartbeat(run_id)
                    else:
                        if on_progress:
                            on_progress("    ✓ Toàn bộ metadata đã có trong cache")

                    # Calculate enrichment status
                    bound_meta = self.repo.get_snapshot_metadata(snapshot_id)
                    complete_meta_count = sum(1 for v in bound_meta.values() if v.get("status") == "complete")
                    if complete_meta_count == len(packages) and len(packages) > 0:
                        enrich_status = "complete"
                    elif complete_meta_count > 0:
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

                if on_progress:
                    on_progress(f"    ✓ Hoàn tất {country.upper()} ({feed_label})")

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
