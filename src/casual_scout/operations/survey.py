from __future__ import annotations

import math
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from casual_scout.collection.jobs import JobService
from casual_scout.collection.service import Collector
from casual_scout.config import Settings
from casual_scout.providers.apple import AppleProvider

if TYPE_CHECKING:
    from casual_scout.storage import Repository

_SURVEY_MARKETS = ["vn", "us", "bn", "kh", "id", "la", "my", "mm", "ph", "sg", "th"]
_WINDOW_SECONDS = 1800  # 30 minutes


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def survey_slots(start: datetime, end: datetime) -> list[datetime]:
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)

    # Align start to 00:00 UTC
    cur = datetime(start_utc.year, start_utc.month, start_utc.day, 0, 0, tzinfo=UTC)
    slots = []
    while cur < end_utc:
        for hour in (0, 6, 12, 18):
            slot = datetime(cur.year, cur.month, cur.day, hour, 0, tzinfo=UTC)
            if start_utc <= slot < end_utc:
                slots.append(slot)
        cur += timedelta(days=1)
    return sorted(slots)


def reconcile_slots(
    repo: Repository, now: datetime, survey_start: datetime | None = None
) -> datetime | None:
    now_utc = now.astimezone(UTC)
    start_utc = survey_start.astimezone(UTC) if survey_start else now_utc - timedelta(days=7)
    start_day = datetime(start_utc.year, start_utc.month, start_utc.day, 0, 0, tzinfo=UTC)

    all_slots = survey_slots(start_day, now_utc + timedelta(hours=6))
    current_active_slot: datetime | None = None

    now_text = _utc_text(now_utc)

    with repo._write_connection() as conn:
        for slot in all_slots:
            if slot > now_utc:
                continue
            slot_utc_text = _utc_text(slot)
            diff_sec = (now_utc - slot).total_seconds()

            existing = conn.execute(
                "SELECT status FROM survey_slots WHERE slot_utc = ?", (slot_utc_text,)
            ).fetchone()

            if 0 <= diff_sec <= _WINDOW_SECONDS:
                # Within active 30 min window
                if existing is None or existing["status"] == "pending":
                    current_active_slot = slot
            elif diff_sec > _WINDOW_SECONDS and existing is None:
                conn.execute(
                    """
                    INSERT INTO survey_slots (slot_utc, status, run_id, recorded_at, note)
                    VALUES (?, 'missed', NULL, ?, 'Window elapsed')
                    """,
                    (slot_utc_text, now_text),
                )

    return current_active_slot


def run_survey(
    repo: Repository,
    provider: Any | None = None,
    now: datetime | None = None,
    survey_start: datetime | None = None,
) -> tuple[str | None, str]:
    now_dt = now or datetime.now(UTC)
    slot = reconcile_slots(repo, now_dt, survey_start)
    if slot is None:
        return None, "no_active_slot"

    slot_utc_str = _utc_text(slot)
    if provider is None:
        settings = Settings(repo.data_dir)
        provider = AppleProvider(settings)

    jobs = JobService(repo)
    req_key = f"survey-{slot_utc_str}"
    run_id = jobs.submit("survey", _SURVEY_MARKETS, req_key)

    collector = Collector(repo, provider, jobs)
    status = collector.execute(run_id, enrich=False)

    now_text = _utc_text(datetime.now(UTC))
    with repo._write_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO survey_slots (slot_utc, status, run_id, recorded_at, note)
            VALUES (?, 'observed', ?, ?, NULL)
            """,
            (slot_utc_str, run_id, now_text),
        )

    return run_id, status


def _nearest_rank_percentile(sorted_data: list[int], percentile: float) -> int | None:
    if not sorted_data:
        return None
    k = math.ceil(len(sorted_data) * percentile)
    idx = max(0, min(k - 1, len(sorted_data) - 1))
    return sorted_data[idx]


def survey_report(repo: Repository, start: datetime, end: datetime) -> dict:
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    expected_slots = survey_slots(start_utc, end_utc)

    with closing(repo._connect()) as conn:
        slot_rows = conn.execute(
            """
            SELECT slot_utc, status, run_id, recorded_at, note
            FROM survey_slots
            WHERE slot_utc >= ? AND slot_utc < ?
            ORDER BY slot_utc ASC
            """,
            (_utc_text(start_utc), _utc_text(end_utc)),
        ).fetchall()

        obs_rows = conn.execute(
            """
            SELECT ro.elapsed_ms, ro.status, ro.error, ro.retry_index
            FROM request_observations ro
            JOIN runs r ON r.id = ro.run_id
            WHERE r.trigger = 'survey' AND ro.started_at >= ? AND ro.started_at < ?
            """,
            (_utc_text(start_utc), _utc_text(end_utc)),
        ).fetchall()

    slots_map = {r["slot_utc"]: dict(r) for r in slot_rows}
    slots_detail = []
    observed_count = 0
    missed_count = 0

    for slot in expected_slots:
        stext = _utc_text(slot)
        if stext in slots_map:
            info = slots_map[stext]
            if info["status"] == "observed":
                observed_count += 1
            elif info["status"] == "missed":
                missed_count += 1
            slots_detail.append(info)
        else:
            missed_count += 1
            slots_detail.append({"slot_utc": stext, "status": "missed", "note": "Unrecorded"})

    latencies = sorted(r["elapsed_ms"] for r in obs_rows if r["elapsed_ms"] is not None)
    error_count = sum(1 for r in obs_rows if r["status"] is None or r["status"] != 200 or r["error"])

    median_lat = _nearest_rank_percentile(latencies, 0.50)
    p95_lat = _nearest_rank_percentile(latencies, 0.95)

    return {
        "summary": {
            "total_slots": len(expected_slots),
            "observed_count": observed_count,
            "missed_count": missed_count,
            "sample_count": len(latencies),
            "error_count": error_count,
            "median_latency_ms": median_lat,
            "p95_latency_ms": p95_lat,
        },
        "slots": slots_detail,
    }
