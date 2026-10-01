from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date as Date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from casual_scout.storage.migrations_retention import (
    authorize_maintenance_connection,
    deauthorize_maintenance_connection,
)


def compute_utc_cutoff(ref_date: Date | None = None) -> datetime:
    """Compute cutoff timestamp: 00:00:00 UTC on D-14 (retaining 15 calendar days: D-14 to D)."""
    base = ref_date or datetime.now(UTC).date()
    target = base - timedelta(days=14)
    return datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=UTC)


@dataclass
class RetentionCandidateReport:
    cutoff_utc: str
    expired_snapshots_count: int = 0
    expired_snapshot_ids: list[str] = field(default_factory=list)
    expired_daily_analytics_count: int = 0
    expired_daily_canonical_count: int = 0
    expired_runs_count: int = 0
    expired_run_ids: list[str] = field(default_factory=list)
    unreferenced_raw_hashes: list[str] = field(default_factory=list)
    raw_files_to_delete: list[str] = field(default_factory=list)
    log_files_to_delete: list[str] = field(default_factory=list)
    estimated_bytes_reclaimable: int = 0


class RetentionService:
    def __init__(self, data_dir: Path, reference_date: Date | None = None) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.db_path = self.data_dir / "casual-scout.sqlite3"
        self.raw_dir = self.data_dir / "raw"
        self.log_dir = self.data_dir / "logs"
        self.manifest_file = self.data_dir / ".retention_gc_manifest.json"
        self.cutoff = compute_utc_cutoff(reference_date)

    def _check_ai_retired(self, conn: sqlite3.Connection) -> None:
        ai_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_%'"
        ).fetchall()
        if ai_tables:
            names = ", ".join(r[0] for r in ai_tables)
            raise RuntimeError(
                f"Cannot run retention: internal AI tables still exist ({names}). Run AI retirement migration first."
            )

    def scan_candidates(self) -> RetentionCandidateReport:
        cutoff_iso = self.cutoff.isoformat().replace("+00:00", "Z")
        cutoff_date = self.cutoff.strftime("%Y-%m-%d")
        report = RetentionCandidateReport(cutoff_utc=cutoff_iso)

        if not self.db_path.exists():
            return report

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._check_ai_retired(conn)

            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            # 1. Snapshots
            if "snapshots" in tables:
                rows = conn.execute(
                    "SELECT id, raw_hash FROM snapshots WHERE observed_at < ?", (cutoff_iso,)
                ).fetchall()
                report.expired_snapshots_count = len(rows)
                report.expired_snapshot_ids = [r["id"] for r in rows]

                # Identify raw hashes referenced by KEPT snapshots
                kept_hashes = {
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT raw_hash FROM snapshots WHERE observed_at >= ?", (cutoff_iso,)
                    ).fetchall()
                    if r[0]
                }
                expired_hashes = {r["raw_hash"] for r in rows if r["raw_hash"]}
                unref_hashes = expired_hashes - kept_hashes
            else:
                unref_hashes = set()

            # 2. Check metadata_versions if table exists
            if "metadata_versions" in tables:
                meta_hashes = {
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT raw_hash FROM metadata_versions"
                    ).fetchall()
                    if r[0]
                }
                unref_hashes -= meta_hashes

            # 3. Check request_observations if table exists
            if "request_observations" in tables:
                obs_hashes = {
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT raw_hash FROM request_observations WHERE raw_hash IS NOT NULL"
                    ).fetchall()
                    if r[0]
                }
                unref_hashes -= obs_hashes

            report.unreferenced_raw_hashes = sorted(list(unref_hashes))

            # 4. Daily analytics
            if "daily_rank_analytics" in tables:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM daily_rank_analytics WHERE date < ?", (cutoff_date,)
                ).fetchone()[0]
                report.expired_daily_analytics_count = cnt

            # 5. Daily canonical snapshots
            if "daily_canonical_snapshots" in tables:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM daily_canonical_snapshots WHERE date < ?", (cutoff_date,)
                ).fetchone()[0]
                report.expired_daily_canonical_count = cnt

            if "platform_canonical_snapshots" in tables:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM platform_canonical_snapshots WHERE date < ?", (cutoff_date,)
                ).fetchone()[0]
                report.expired_daily_canonical_count += cnt

            # 6. Closed runs
            if "runs" in tables:
                run_rows = conn.execute(
                    "SELECT id FROM runs WHERE started_at < ? AND status NOT IN ('queued', 'running')",
                    (cutoff_iso,),
                ).fetchall()
                report.expired_runs_count = len(run_rows)
                report.expired_run_ids = [r["id"] for r in run_rows]

            # 7. Calculate raw files and reclaimable bytes
            total_bytes = 0
            file_paths: list[str] = []
            for h in report.unreferenced_raw_hashes:
                candidate_path = (self.raw_dir / h[:2] / h).resolve()
                if candidate_path.is_file():
                    total_bytes += candidate_path.stat().st_size
                    file_paths.append(str(candidate_path))

            report.raw_files_to_delete = file_paths

            # 8. Calculate log files for expired runs
            log_files: list[str] = []
            if self.log_dir.is_dir():
                for run_id in report.expired_run_ids:
                    log_file = (self.log_dir / f"run-{run_id}.log").resolve()
                    if log_file.is_file():
                        total_bytes += log_file.stat().st_size
                        log_files.append(str(log_file))

            report.log_files_to_delete = log_files
            report.estimated_bytes_reclaimable = total_bytes
            return report
        finally:
            conn.close()

    def apply_retention(self) -> dict[str, Any]:
        """Apply retention: atomic two-phase GC across DB transaction and filesystem unlinking."""
        recovered_raw_count = 0
        recovered_log_count = 0

        # Step 0: Crash recovery from prior incomplete run manifest if present
        if self.manifest_file.is_file():
            try:
                prior_manifest = json.loads(self.manifest_file.read_text(encoding="utf-8"))
                for p_str in prior_manifest.get("raw_files", []):
                    p = Path(p_str).resolve()
                    if self.raw_dir in p.parents and p.is_file() and not p.is_symlink():
                        p.unlink(missing_ok=True)
                        recovered_raw_count += 1
                for p_str in prior_manifest.get("log_files", []):
                    p = Path(p_str).resolve()
                    if self.log_dir in p.parents and p.is_file() and not p.is_symlink():
                        p.unlink(missing_ok=True)
                        recovered_log_count += 1
                self.manifest_file.unlink(missing_ok=True)
            except Exception:
                pass

        report = self.scan_candidates()
        has_db_work = (
            report.expired_snapshots_count > 0
            or report.expired_daily_canonical_count > 0
            or report.expired_daily_analytics_count > 0
            or report.expired_runs_count > 0
            or len(report.unreferenced_raw_hashes) > 0
        )
        has_file_work = (
            len(report.raw_files_to_delete) > 0
            or len(report.log_files_to_delete) > 0
        )

        if not has_db_work and not has_file_work:
            if recovered_raw_count > 0 or recovered_log_count > 0:
                return {
                    "status": "success",
                    "cutoff_utc": report.cutoff_utc,
                    "deleted_snapshots": 0,
                    "deleted_daily_canonical": 0,
                    "deleted_daily_analytics": 0,
                    "deleted_runs": 0,
                    "deleted_raw_files": recovered_raw_count,
                    "deleted_log_files": recovered_log_count,
                    "reclaimed_bytes": 0,
                }
            return {
                "status": "noop",
                "cutoff_utc": report.cutoff_utc,
                "deleted_snapshots": 0,
                "deleted_daily_canonical": 0,
                "deleted_daily_analytics": 0,
                "deleted_runs": 0,
                "deleted_raw_files": 0,
                "deleted_log_files": 0,
                "reclaimed_bytes": 0,
            }

        # Step 1: Write persistent GC manifest before DB commit
        manifest = {
            "cutoff_utc": report.cutoff_utc,
            "expired_snapshot_ids": report.expired_snapshot_ids,
            "raw_files": report.raw_files_to_delete,
            "raw_hashes": report.unreferenced_raw_hashes,
            "log_files": report.log_files_to_delete,
        }
        self.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

        # Step 2: DB Deletion in transaction
        cutoff_date = self.cutoff.strftime("%Y-%m-%d")
        cutoff_iso = report.cutoff_utc

        if self.db_path.exists():
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON;")
            authorize_maintenance_connection(conn)
            try:
                with conn:
                    tables = {
                        r[0]
                        for r in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }

                    # Delete daily canonical snapshots older than cutoff or referencing expired snapshots
                    if "daily_canonical_snapshots" in tables:
                        if report.expired_snapshot_ids:
                            q_marks = ",".join("?" for _ in report.expired_snapshot_ids)
                            conn.execute(
                                f"DELETE FROM daily_canonical_snapshots WHERE date < ? OR snapshot_id IN ({q_marks})",
                                [cutoff_date, *report.expired_snapshot_ids],
                            )
                        else:
                            conn.execute(
                                "DELETE FROM daily_canonical_snapshots WHERE date < ?",
                                (cutoff_date,),
                            )

                    # Delete platform canonical snapshots older than cutoff or referencing expired snapshots
                    if "platform_canonical_snapshots" in tables:
                        if report.expired_snapshot_ids:
                            q_marks = ",".join("?" for _ in report.expired_snapshot_ids)
                            conn.execute(
                                f"DELETE FROM platform_canonical_snapshots WHERE date < ? OR snapshot_id IN ({q_marks})",
                                [cutoff_date, *report.expired_snapshot_ids],
                            )
                        else:
                            conn.execute(
                                "DELETE FROM platform_canonical_snapshots WHERE date < ?",
                                (cutoff_date,),
                            )

                    # Delete daily rank analytics
                    if "daily_rank_analytics" in tables:
                        conn.execute(
                            "DELETE FROM daily_rank_analytics WHERE date < ?",
                            (cutoff_date,),
                        )

                    # Delete snapshot metadata and entries for expired snapshots
                    if report.expired_snapshot_ids:
                        q_marks = ",".join("?" for _ in report.expired_snapshot_ids)
                        if "snapshot_metadata" in tables:
                            conn.execute(
                                f"DELETE FROM snapshot_metadata WHERE snapshot_id IN ({q_marks})",
                                report.expired_snapshot_ids,
                            )
                        if "entries" in tables:
                            conn.execute(
                                f"DELETE FROM entries WHERE snapshot_id IN ({q_marks})",
                                report.expired_snapshot_ids,
                            )
                        if "snapshots" in tables:
                            conn.execute(
                                f"DELETE FROM snapshots WHERE id IN ({q_marks})",
                                report.expired_snapshot_ids,
                            )

                    # Delete expired request observations, market_runs, runs
                    if report.expired_run_ids:
                        r_marks = ",".join("?" for _ in report.expired_run_ids)
                        if "one_time_collection_schedule" in tables:
                            conn.execute(
                                f"UPDATE one_time_collection_schedule SET run_id = NULL WHERE run_id IN ({r_marks})",
                                report.expired_run_ids,
                            )
                        if "android_jobs" in tables:
                            conn.execute(
                                f"UPDATE android_jobs SET core_run_id = NULL WHERE core_run_id IN ({r_marks})",
                                report.expired_run_ids,
                            )
                        if "collector_lock" in tables:
                            conn.execute(
                                f"DELETE FROM collector_lock WHERE run_id IN ({r_marks})",
                                report.expired_run_ids,
                            )
                        if "survey_slots" in tables:
                            conn.execute(
                                f"UPDATE survey_slots SET run_id = NULL WHERE run_id IN ({r_marks})",
                                report.expired_run_ids,
                            )
                        if "request_observations" in tables:
                            conn.execute(
                                f"DELETE FROM request_observations WHERE run_id IN ({r_marks})",
                                report.expired_run_ids,
                            )
                        if "market_runs" in tables:
                            conn.execute(
                                f"DELETE FROM market_runs WHERE run_id IN ({r_marks}) AND id NOT IN (SELECT market_run_id FROM snapshots)",
                                report.expired_run_ids,
                            )
                        if "runs" in tables:
                            conn.execute(
                                f"DELETE FROM runs WHERE id IN ({r_marks}) AND id NOT IN (SELECT run_id FROM market_runs)",
                                report.expired_run_ids,
                            )

                    # Delete expired survey slots if table exists
                    if "survey_slots" in tables:
                        conn.execute(
                            "DELETE FROM survey_slots WHERE slot_utc < ?",
                            (cutoff_iso,),
                        )

                    # Delete orphaned raw_responses
                    if report.unreferenced_raw_hashes and "raw_responses" in tables:
                        h_marks = ",".join("?" for _ in report.unreferenced_raw_hashes)
                        conn.execute(
                            f"DELETE FROM raw_responses WHERE hash IN ({h_marks})",
                            report.unreferenced_raw_hashes,
                        )

                    # Integrity check
                    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
                    if fk_errors:
                        raise RuntimeError(f"Foreign key check failed during retention: {fk_errors}")
            finally:
                deauthorize_maintenance_connection(conn)
                conn.close()

        # Step 3: Filesystem deletion
        deleted_raw_count = recovered_raw_count
        for p_str in report.raw_files_to_delete:
            p = Path(p_str).resolve()
            if self.raw_dir in p.parents and p.is_file() and not p.is_symlink():
                p.unlink(missing_ok=True)
                deleted_raw_count += 1

        # Clean empty subdirs in raw_dir
        if self.raw_dir.is_dir():
            for sub in self.raw_dir.iterdir():
                if sub.is_dir():
                    try:
                        sub.rmdir()
                    except OSError:
                        pass

        deleted_log_count = recovered_log_count
        for p_str in report.log_files_to_delete:
            p = Path(p_str).resolve()
            if self.log_dir in p.parents and p.is_file() and not p.is_symlink():
                p.unlink(missing_ok=True)
                deleted_log_count += 1

        # Manifest cleanup
        self.manifest_file.unlink(missing_ok=True)

        return {
            "status": "success",
            "cutoff_utc": report.cutoff_utc,
            "deleted_snapshots": report.expired_snapshots_count,
            "deleted_daily_canonical": report.expired_daily_canonical_count,
            "deleted_daily_analytics": report.expired_daily_analytics_count,
            "deleted_runs": report.expired_runs_count,
            "deleted_raw_files": deleted_raw_count,
            "deleted_log_files": deleted_log_count,
            "reclaimed_bytes": report.estimated_bytes_reclaimable,
        }
