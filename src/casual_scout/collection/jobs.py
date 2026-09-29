from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import psutil

from casual_scout.config import IOS_COLLECTION_COUNTRIES
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


class CollectionBusyError(RuntimeError):
    """Another collection scope currently owns the collector."""


class JobService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        with repo._write_connection() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
            if "launch_claimed_at" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN launch_claimed_at TEXT")

    def claim_launch(self, run_id: str) -> bool:
        with self.repo._write_connection() as conn:
            return (
                conn.execute(
                    "UPDATE runs SET launch_claimed_at=? WHERE id=? AND status='queued' AND launch_claimed_at IS NULL",
                    (_utc_text(datetime.now(UTC)), run_id),
                ).rowcount
                == 1
            )

    def launch(self, run_id, launcher):
        if not self.claim_launch(run_id):
            return False
        try:
            launcher(run_id, self.repo.data_dir)
        except Exception:
            self.finish(run_id, "failed", {"error": "Worker launch failed"})
            with self.repo._write_connection() as conn:
                conn.execute("UPDATE runs SET launch_claimed_at=NULL WHERE id=?", (run_id,))
            raise
        return True

    def submit_scheduled_android(self, local_date: str, now: datetime) -> str | None:
        from zoneinfo import ZoneInfo

        local = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        if (local.hour, local.minute) != (7, 0) or local.date().isoformat() != local_date:
            return None
        with self.repo._write_connection() as conn:
            if conn.execute(
                "SELECT 1 FROM runs WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone():
                return None
            claim = conn.execute(
                "UPDATE android_schedule SET last_date=? WHERE id=1 AND enabled=1 AND (last_date IS NULL OR last_date<>?)",
                (local_date, local_date),
            )
            if claim.rowcount != 1:
                return None
            run_id = str(uuid4())
            conn.execute(
                """INSERT INTO runs(id,request_key,"trigger",status,started_at,summary_json) VALUES(?,?,?,'queued',?,'{}')""",
                (run_id, f"daily-android-{local_date}", "daily", _utc_text(now)),
            )
            from casual_scout.providers.google import chart_url

            for country in ("vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"):
                for feed in ("top-free", "top-grossing"):
                    chart = Chart(
                        country,
                        provider="google",
                        platform="android",
                        genre="GAME_CASUAL",
                        feed_type=feed,
                    )
                    chart_id = self.repo._ensure_chart(conn, chart, chart_url(chart))
                    self.repo._ensure_market_run(conn, run_id, chart_id, now)
            return run_id

    def submit_scheduled_ios(self, kind: str, value: str, now: datetime) -> str | None:
        """Claim a schedule and create its own run in one transaction.

        Unlike manual submit, never return another platform's active run.
        """
        stamp = _utc_text(now)
        with self.repo._write_connection() as conn:
            if conn.execute(
                "SELECT 1 FROM runs WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone():
                return None
            if kind == "daily":
                claimed = conn.execute(
                    """UPDATE daily_schedule SET last_triggered_local_date=?,updated_at=?
                    WHERE id=1 AND enabled=1 AND (last_triggered_local_date IS NULL OR last_triggered_local_date<>?)""",
                    (value, stamp, value),
                )
                request_key = f"daily-ios-{value}"
            elif kind == "one-time":
                row = conn.execute(
                    "SELECT * FROM one_time_collection_schedule WHERE id=1 AND status='pending'"
                ).fetchone()
                if not row or row["scheduled_for_utc"] != value:
                    return None
                due = datetime.fromisoformat(value)
                if due > now:
                    return None
                if now - due > timedelta(minutes=1):
                    conn.execute(
                        "UPDATE one_time_collection_schedule SET status='missed',updated_at=? WHERE id=1",
                        (stamp,),
                    )
                    return None
                claimed = conn.execute(
                    "UPDATE one_time_collection_schedule SET status='triggered',triggered_at=?,updated_at=? WHERE id=1 AND status='pending'",
                    (stamp, stamp),
                )
                request_key = f"one-time-ios-{value}"
            else:
                raise ValueError("unknown schedule kind")
            if claimed.rowcount != 1:
                return None
            run_id = str(uuid4())
            conn.execute(
                """INSERT INTO runs(id,request_key,"trigger",status,started_at,summary_json)
                VALUES(?,?,?,'queued',?,'{}')""",
                (run_id, request_key, "daily" if kind == "daily" else "manual", stamp),
            )
            for country in IOS_COLLECTION_COUNTRIES:
                chart = Chart(country, feed_type="top-free")
                endpoint = f"https://itunes.apple.com/{country}/rss/{chart.collection}/limit={chart.depth}/genre={chart.genre}/json"
                chart_id = self.repo._ensure_chart(conn, chart, endpoint)
                self.repo._ensure_market_run(conn, run_id, chart_id, now)
            if kind == "one-time":
                conn.execute(
                    "UPDATE one_time_collection_schedule SET run_id=? WHERE id=1", (run_id,)
                )
            return run_id

    def submit(
        self,
        trigger: str,
        countries: list[str],
        request_key: str,
        chart_types: list[str] | None = None,
        *,
        platform: str = "ios",
    ) -> str:
        if platform not in ("ios", "android"):
            raise ValueError("unsupported platform")
        countries = list(dict.fromkeys(c.strip().lower() for c in countries))
        if platform == "android" and not set(countries) <= {
            "vn",
            "th",
            "id",
            "my",
            "ph",
            "sg",
            "la",
            "kh",
            "us",
        }:
            raise ValueError("unsupported Android market")
        if chart_types and not set(chart_types) <= {"top-free", "top-grossing"}:
            raise ValueError("unsupported feed")
        if not countries:
            raise ValueError("countries list must not be empty")

        self.recover_dead_processes()
        now_dt = datetime.now(UTC)
        now = _utc_text(now_dt)
        feeds = chart_types or ["top-free"]

        expected = {(platform, c, f) for c in countries for f in feeds}

        def scope(conn, run_id):
            return {
                (
                    r["platform"],
                    r["country"],
                    (
                        "top-free"
                        if r["collection"] in ("top-free", "topfreeapplications")
                        else "top-grossing"
                    ),
                )
                for r in conn.execute(
                    "SELECT c.platform,c.country,c.collection FROM market_runs m JOIN charts c ON c.id=m.chart_id WHERE m.run_id=?",
                    (run_id,),
                )
            }

        with self.repo._write_connection() as conn:
            existing_key = conn.execute(
                "SELECT id FROM runs WHERE request_key = ?", (request_key,)
            ).fetchone()
            if existing_key is not None:
                if scope(conn, existing_key["id"]) != expected:
                    raise ValueError("idempotency key scope mismatch")
                return str(existing_key["id"])

            active_run = conn.execute(
                "SELECT id FROM runs WHERE status IN ('queued', 'running') ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if active_run is not None:
                if scope(conn, active_run["id"]) != expected:
                    raise CollectionBusyError("collector busy with another scope")
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
                for feed in feeds:
                    if platform == "android":
                        from casual_scout.providers.google import chart_url

                        chart = Chart(
                            country.lower(),
                            provider="google",
                            platform="android",
                            genre="GAME_CASUAL",
                            feed_type=feed,
                        )
                        chart_endpoint = chart_url(chart)
                    else:
                        chart = Chart(country.lower(), feed_type=feed)
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
            run = conn.execute("SELECT id, status FROM runs WHERE id = ?", (run_id,)).fetchone()
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
            conn.execute("UPDATE runs SET status = 'running' WHERE id = ?", (run_id,))
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

            abandoned = conn.execute(
                "SELECT id FROM runs WHERE status='queued' AND launch_claimed_at IS NOT NULL AND launch_claimed_at<?",
                (_utc_text(datetime.now(UTC) - timedelta(seconds=120)),),
            ).fetchall()
            for row in abandoned:
                conn.execute(
                    "UPDATE runs SET status='interrupted',ended_at=?,launch_claimed_at=NULL WHERE id=?",
                    (now, row["id"]),
                )
                recovered.append(str(row["id"]))
            running_runs = conn.execute("SELECT id FROM runs WHERE status = 'running'").fetchall()
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
