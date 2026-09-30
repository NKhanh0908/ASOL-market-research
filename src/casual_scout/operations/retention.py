from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date as Date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any

from casual_scout.storage.migrations_retention import authorize_maintenance_connection


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
                # Add hashes from surviving metadata_versions to kept_hashes
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
                # If the run for request observation is not expired, protect the raw hash
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
