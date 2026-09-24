from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from casual_scout.analysis.taxonomy import classify_app

VN = ZoneInfo("Asia/Ho_Chi_Minh")
ACTIVE = ("pending", "queued", "running")


def utcnow():
    return datetime.now(UTC).isoformat()


class AndroidStore:
    def __init__(self, repo):
        self.repo = repo

    def initialize(self):
        with closing(self.repo._connect()) as db:
            db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def enqueue(self, trigger="manual", local_date=None):
        now = utcnow()
        day = local_date or datetime.now(VN).date().isoformat()
        with self.repo._write_connection() as db:
            active = db.execute(
                "SELECT id FROM android_jobs WHERE status IN ('pending','queued','running') ORDER BY created_at LIMIT 1"
            ).fetchone()
            if active:
                return active["id"]
            key = f"android-daily-{day}" if trigger == "daily" else f"android-{uuid4()}"
            existing = db.execute(
                "SELECT id FROM android_jobs WHERE request_key=?", (key,)
            ).fetchone()
            if existing:
                return existing["id"]
            job_id = str(uuid4())
            db.execute(
                """INSERT INTO android_jobs
                (id,request_key,trigger,status,local_date,created_at,updated_at)
                VALUES(?,?,?,'pending',?,?,?)""",
                (job_id, key, trigger, day, now, now),
            )
        return job_id

    def dispatch(self):
        now = utcnow()
        with self.repo._write_connection() as db:
            if db.execute(
                "SELECT 1 FROM runs WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone():
                return None
            row = db.execute(
                "SELECT * FROM android_jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            db.execute(
                """INSERT INTO runs(id,request_key,"trigger",status,started_at,summary_json)
                VALUES(?,?,?,'queued',?,?)""",
                (
                    row["id"],
                    row["request_key"],
                    row["trigger"],
                    now,
                    json.dumps({"platform": "android"}),
                ),
            )
            db.execute(
                "UPDATE android_jobs SET status='queued',phase='starting',core_run_id=id,dispatched_at=?,updated_at=? WHERE id=?",
                (now, now, row["id"]),
            )
            return row["id"]

    def started(self, job_id, pid, created):
        with self.repo._write_connection() as db:
            db.execute(
                "UPDATE android_jobs SET status='running',phase='charts',pid=?,process_created=?,updated_at=? WHERE id=?",
                (pid, created, utcnow(), job_id),
            )

    def record_process(self, job_id, pid, created):
        with self.repo._write_connection() as db:
            db.execute(
                "UPDATE android_jobs SET pid=?,process_created=? WHERE id=?", (pid, created, job_id)
            )

    def phase(self, job_id, phase):
        with self.repo._write_connection() as db:
            db.execute(
                "UPDATE android_jobs SET phase=?,updated_at=? WHERE id=?", (phase, utcnow(), job_id)
            )

    def add_error(self, job_id, message):
        with self.repo._write_connection() as db:
            row = db.execute(
                "SELECT errors_json FROM android_jobs WHERE id=?", (job_id,)
            ).fetchone()
            errors = json.loads(row["errors_json"])
            errors.append(str(message)[:1000])
            db.execute(
                "UPDATE android_jobs SET errors_json=?,updated_at=? WHERE id=?",
                (json.dumps(errors, ensure_ascii=False), utcnow(), job_id),
            )

    def save_chart(self, job_id, feed, entries, evidence, observed_at=None):
        if feed not in ("top-free", "top-grossing") or not entries:
            raise ValueError("empty or unsupported chart")
        if [e["rank"] for e in entries] != list(range(1, len(entries) + 1)):
            raise ValueError("non-contiguous chart ranks")
        if len({e["package"] for e in entries}) != len(entries):
            raise ValueError("duplicate chart package")
        field = "free_rank" if feed == "top-free" else "grossing_rank"
        observed_at = observed_at or datetime.now(UTC)
        if observed_at.tzinfo is None:
            raise ValueError("chart observation must be timezone-aware")
        with self.repo._write_connection() as db:
            day = observed_at.astimezone(VN).date().isoformat()
            previous = self._previous_chart(db, day, feed)
            db.execute(
                "INSERT INTO android_charts VALUES(?,?,?,?,?)",
                (job_id, feed, observed_at.astimezone(UTC).isoformat(), len(entries), evidence),
            )
            for entry in entries:
                row = db.execute(
                    "SELECT data_json FROM android_entries WHERE job_id=? AND package=?",
                    (job_id, entry["package"]),
                ).fetchone()
                data = (
                    json.loads(row["data_json"])
                    if row
                    else {
                        "package": entry["package"],
                        "name": entry["name"],
                        "icon_url": entry.get("icon_url"),
                        "store_url": entry.get("url"),
                        "free_rank": None,
                        "grossing_rank": None,
                        "metadata_status": "pending",
                        "developer": None,
                        "delta_free_1d": None,
                        "delta_grossing_1d": None,
                        "monetization_model": "UNKNOWN",
                        "revenue_amount": None,
                    }
                )
                data[field] = entry["rank"]
                previous_rank = previous.get(entry["package"])
                data["delta_free_1d" if feed == "top-free" else "delta_grossing_1d"] = (
                    previous_rank - entry["rank"] if previous_rank is not None else None
                )
                self._put(db, job_id, data)
            db.execute(
                """UPDATE android_jobs SET total=(SELECT count(*) FROM android_entries WHERE job_id=?),
                updated_at=? WHERE id=?""",
                (job_id, utcnow(), job_id),
            )

    @staticmethod
    def _put(db, job_id, data):
        db.execute(
            """INSERT INTO android_entries VALUES(?,?,?) ON CONFLICT(job_id,package)
            DO UPDATE SET data_json=excluded.data_json""",
            (job_id, data["package"], json.dumps(data, ensure_ascii=False)),
        )

    @staticmethod
    def _previous_chart(db, day, feed):
        previous_day = (datetime.fromisoformat(day).date() - timedelta(days=1)).isoformat()
        row = db.execute(
            """SELECT c.job_id FROM android_charts c JOIN android_jobs j ON j.id=c.job_id
            WHERE date(c.observed_at,'+7 hours')=? AND c.feed=? AND j.status IN ('succeeded','partial')
            ORDER BY c.observed_at DESC LIMIT 1""",
            (previous_day, feed),
        ).fetchone()
        if not row:
            return {}
        field = "free_rank" if feed == "top-free" else "grossing_rank"
        values = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT data_json FROM android_entries WHERE job_id=?", (row["job_id"],)
            )
        ]
        return {r["package"]: r[field] for r in values if r.get(field) is not None}

    def save_batch(self, job_id, results):
        with self.repo._write_connection() as db:
            for result in results:
                row = db.execute(
                    "SELECT data_json FROM android_entries WHERE job_id=? AND package=?",
                    (job_id, result["package"]),
                ).fetchone()
                if row is None:
                    raise ValueError("metadata package outside captured charts")
                data = json.loads(row["data_json"])
                data.update(result)
                classified = classify_app(["Casual"], data["name"], data.get("description") or "")
                data["mechanic"] = classified["mechanic"]
                data["mechanic_confidence"] = classified["confidence"]
                data["subgenre"] = classified["subgenre"]
                data["analyzed_at"] = utcnow()
                ads, iap = data.get("ads_observed"), data.get("iap_observed")
                data["monetization_model"] = (
                    "PAID_PREMIUM"
                    if (data.get("price") or 0) > 0
                    else "HYBRID"
                    if ads is True and iap is True
                    else "IAP_OBSERVED"
                    if iap is True
                    else "ADS_OBSERVED"
                    if ads is True
                    else "UNKNOWN"
                )
                self._put(db, job_id, data)
            db.execute(
                """UPDATE android_jobs SET processed=(SELECT count(*) FROM android_entries
                WHERE job_id=? AND json_extract(data_json,'$.metadata_status') <> 'pending'),
                batches=batches+1,updated_at=? WHERE id=?""",
                (job_id, utcnow(), job_id),
            )

    def cached_metadata(self, package):
        with closing(self.repo._connect()) as db:
            rows = db.execute(
                """SELECT data_json FROM android_entries WHERE package=?
                AND json_extract(data_json,'$.metadata_status') IN ('complete','cached')
                ORDER BY json_extract(data_json,'$.fetched_at') DESC LIMIT 1""",
                (package,),
            ).fetchall()
        if not rows:
            return None
        data = json.loads(rows[0][0])
        fetched_at = data.get("fetched_at")
        if not fetched_at or datetime.now(UTC) - datetime.fromisoformat(fetched_at) > timedelta(
            hours=48
        ):
            return None
        fields = (
            "package",
            "developer",
            "description",
            "rating",
            "rating_count",
            "price",
            "currency",
            "ads_observed",
            "iap_observed",
            "fetched_at",
            "metadata_evidence",
        )
        return {**{key: data.get(key) for key in fields}, "metadata_status": "cached"}

    def finish(self, job_id, status, error=None):
        if status not in ("succeeded", "partial", "failed", "interrupted"):
            raise ValueError("invalid terminal status")
        if error:
            self.add_error(job_id, error)
        with self.repo._write_connection() as db:
            db.execute(
                "UPDATE android_jobs SET status=?,phase=?,updated_at=? WHERE id=?",
                (status, status, utcnow(), job_id),
            )
            db.execute("UPDATE runs SET status=?,ended_at=? WHERE id=?", (status, utcnow(), job_id))
            db.execute("DELETE FROM collector_lock WHERE run_id=?", (job_id,))

    def view(self, job_id=None):
        with closing(self.repo._connect()) as db:
            jobs = [
                dict(r)
                for r in db.execute("SELECT * FROM android_jobs ORDER BY created_at DESC LIMIT 50")
            ]
            row = (
                db.execute("SELECT * FROM android_jobs WHERE id=?", (job_id,)).fetchone()
                if job_id
                else (jobs[0] if jobs else None)
            )
            if job_id and row is None:
                raise KeyError(job_id)
            entries, charts = [], []
            job = dict(row) if row else None
            if job:
                job["errors"] = json.loads(job.pop("errors_json"))
                entries = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT data_json FROM android_entries WHERE job_id=?", (job["id"],)
                    )
                ]
                entries.sort(
                    key=lambda r: (r.get("free_rank") or 100000, r.get("grossing_rank") or 100000)
                )
                charts = [
                    dict(r)
                    for r in db.execute("SELECT * FROM android_charts WHERE job_id=?", (job["id"],))
                ]
            schedule = dict(db.execute("SELECT * FROM android_schedule WHERE id=1").fetchone())
            schedule["enabled"] = bool(schedule["enabled"])
            active = db.execute(
                "SELECT id FROM android_jobs WHERE status IN ('pending','queued','running') LIMIT 1"
            ).fetchone()
        return {
            "job": job,
            "entries": entries,
            "charts": charts,
            "schedule": schedule,
            "jobs": [
                {key: j[key] for key in ("id", "status", "created_at", "local_date")} for j in jobs
            ],
            "active_job_id": active["id"] if active else None,
        }

    def set_schedule(self, enabled):
        with self.repo._write_connection() as db:
            db.execute("UPDATE android_schedule SET enabled=? WHERE id=1", (int(enabled),))

    def enqueue_daily(self, now):
        local = now.astimezone(VN)
        if (local.hour, local.minute) != (7, 0):
            return None
        day = local.date().isoformat()
        with self.repo._write_connection() as db:
            result = db.execute(
                "UPDATE android_schedule SET last_date=? WHERE id=1 AND enabled=1 AND (last_date IS NULL OR last_date<>?)",
                (day, day),
            )
            if result.rowcount == 0:
                return None
            # Claim and insert together; existing manual work still permits today's daily queue.
            job_id = str(uuid4())
            db.execute(
                """INSERT OR IGNORE INTO android_jobs
                (id,request_key,trigger,status,local_date,created_at,updated_at)
                VALUES(?,?,'daily','pending',?,?,?)""",
                (job_id, f"android-daily-{day}", day, utcnow(), utcnow()),
            )
            return job_id
