from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import psutil

from casual_scout.models import Chart

if TYPE_CHECKING:
    from casual_scout.storage import Repository


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _is_process_alive(pid: int, created_at: float | None = None) -> bool:
    try:
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False
        return not (created_at is not None and abs(proc.create_time() - created_at) > 1.0)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


class JobService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def submit(self, trigger: str, countries: list[str], request_key: str) -> str:
        if not countries:
            raise ValueError("countries list must not be empty")

        now_dt = datetime.now(UTC)
        now = _utc_text(now_dt)

        with self.repo._write_connection() as conn:
            existing_key = conn.execute(
                "SELECT id FROM runs WHERE request_key = ?", (request_key,)
            ).fetchone()
            if existing_key is not None:
                return str(existing_key["id"])

            active_run = conn.execute(
                "SELECT id FROM runs WHERE status IN ('queued', 'running') ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if active_run is not None:
                return str(active_run["id"])

            run_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO runs (id, request_key, "trigger", status, started_at, summary_json)
                VALUES (?, ?, ?, 'queued', ?, '{}')
                """,
                (run_id, request_key, trigger, now),
            )

            for country in countries:
                chart = Chart(country.lower())
                chart_endpoint = (
                    f"https://itunes.apple.com/{chart.country}/rss/{chart.collection}/"
                    f"limit={chart.depth}/genre={chart.genre}/json"
                )
                chart_id = self.repo._ensure_chart(conn, chart, chart_endpoint)
                self.repo._ensure_market_run(conn, run_id, chart_id, now_dt)

            return run_id

    def claim(self, run_id: str, pid: int, process_created_at: float) -> bool:
        now = _utc_text(datetime.now(UTC))
        with self.repo._write_connection() as conn:
            run = conn.execute(
                "SELECT id, status FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run is None or run["status"] not in ("queued", "running"):
                return False

            lock = conn.execute("SELECT * FROM collector_lock WHERE id = 1").fetchone()
            if lock is not None:
                lock_pid = int(lock["pid"])
                lock_created = float(lock["process_created_at"])
                lock_run_id = str(lock["run_id"])

                if _is_process_alive(lock_pid, lock_created):
                    if lock_run_id != run_id or lock_pid != pid:
                        return False
                else:
                    # Process is dead, clear lock and mark previous run interrupted
                    if lock_run_id != run_id:
                        conn.execute(
                            "UPDATE runs SET status = 'interrupted', ended_at = ? WHERE id = ? AND status = 'running'",
                            (now, lock_run_id),
                        )
                    conn.execute("DELETE FROM collector_lock WHERE id = 1")

            conn.execute(
                """
                INSERT OR REPLACE INTO collector_lock
                    (id, run_id, pid, process_created_at, acquired_at, heartbeat_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (run_id, pid, process_created_at, now, now),
            )
            conn.execute(
                "UPDATE runs SET status = 'running' WHERE id = ?", (run_id,)
            )
            return True

    def heartbeat(self, run_id: str) -> None:
        now = _utc_text(datetime.now(UTC))
        with self.repo._write_connection() as conn:
            conn.execute(
                "UPDATE collector_lock SET heartbeat_at = ? WHERE run_id = ?",
                (now, run_id),
            )

    def finish(self, run_id: str, status: str, summary: dict | None = None) -> None:
        now = _utc_text(datetime.now(UTC))
        summary_json = json.dumps(summary or {}, ensure_ascii=False)
        with self.repo._write_connection() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, ended_at = ?, summary_json = ?
                WHERE id = ?
                """,
                (status, now, summary_json, run_id),
            )
            conn.execute("DELETE FROM collector_lock WHERE run_id = ?", (run_id,))

    def recover_dead_processes(self) -> list[str]:
        recovered: list[str] = []
        now = _utc_text(datetime.now(UTC))
        with self.repo._write_connection() as conn:
            lock = conn.execute("SELECT * FROM collector_lock WHERE id = 1").fetchone()
            if lock is not None:
                lock_pid = int(lock["pid"])
                lock_created = float(lock["process_created_at"])
                lock_run_id = str(lock["run_id"])

                if not _is_process_alive(lock_pid, lock_created):
                    conn.execute(
                        "UPDATE runs SET status = 'interrupted', ended_at = ? WHERE id = ? AND status = 'running'",
                        (now, lock_run_id),
                    )
                    conn.execute("DELETE FROM collector_lock WHERE id = 1")
                    recovered.append(lock_run_id)

            running_runs = conn.execute(
                "SELECT id FROM runs WHERE status = 'running'"
            ).fetchall()
            for r in running_runs:
                r_id = str(r["id"])
                if lock is None or str(lock["run_id"]) != r_id:
                    conn.execute(
                        "UPDATE runs SET status = 'interrupted', ended_at = ? WHERE id = ?",
                        (now, r_id),
                    )
                    if r_id not in recovered:
                        recovered.append(r_id)

        return recovered
