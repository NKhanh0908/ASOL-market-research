"""Platform validation, provider factory, and unified core worker dispatch."""
from __future__ import annotations

from contextlib import closing
from typing import TYPE_CHECKING, Callable
import httpx

from casual_scout.android.collector import AndroidCollector
from casual_scout.collection.jobs import JobService
from casual_scout.collection.service import Collector
from casual_scout.config import Settings
from casual_scout.providers.apple import AppleProvider
from casual_scout.providers.google import GooglePlayProvider
from casual_scout.providers.google_http import GoogleHttpClient

if TYPE_CHECKING:
    from casual_scout.storage import Repository


def selected_platforms(value: str) -> tuple[str, ...]:
    """Resolve CLI/API platform input to a sequence of platform identifiers."""
    val = value.lower().strip()
    if val == "all":
        return ("ios", "android")
    if val in ("ios", "android"):
        return (val,)
    raise ValueError(f"unsupported platform: {value}")


def execute_run(
    repo: Repository,
    run_id: str,
    *,
    enrich: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Execute a queued core run by dispatching to the platform-specific collector."""
    with closing(repo._connect()) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT c.platform
            FROM market_runs mr
            JOIN charts c ON c.id = mr.chart_id
            WHERE mr.run_id = ?
            """,
            (run_id,),
        ).fetchall()

    if not rows:
        raise ValueError(f"no charts found for run: {run_id}")
    if len(rows) > 1:
        raise ValueError(f"mixed-platform runs are not supported: {run_id}")

    platform = str(rows[0]["platform"]).lower()
    jobs = JobService(repo)

    if platform == "android":
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=10)
        with httpx.Client(timeout=15.0, limits=limits) as http_client:
            http_transport = GoogleHttpClient(http_client)
            provider = GooglePlayProvider(http_transport)
            collector = AndroidCollector(repo, provider, jobs)
            return collector.execute(run_id, enrich=enrich, on_progress=on_progress)
    elif platform == "ios":
        settings = Settings(repo.data_dir)
        provider = AppleProvider(settings)
        collector = Collector(repo, provider, jobs)
        return collector.execute(run_id, enrich=enrich, on_progress=on_progress)
    else:
        raise ValueError(f"unsupported platform in run {run_id}: {platform}")


def collect_platform(
    repo: Repository,
    platform: str,
    countries: list[str],
    feeds: list[str],
    request_key: str,
    *,
    enrich: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[str, str]:
    """Submit and immediately execute collection for a single platform."""
    jobs = JobService(repo)
    run_id = jobs.submit(
        "manual",
        countries,
        request_key,
        chart_types=feeds,
        platform=platform,
    )
    status = execute_run(repo, run_id, enrich=enrich, on_progress=on_progress)
    return run_id, status
