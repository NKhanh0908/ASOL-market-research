"""Opt-in live cold/warm acceptance measurement; never uses the normal data directory."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

MARKETS = ("vn", "th", "id", "my", "ph", "sg", "la", "kh", "us")
FEEDS = ("top-free", "top-grossing")
BROWSERS = ("chrome", "chromium", "msedge", "firefox", "chromedriver", "geckodriver")


def assert_acceptance(report):
    assert report["browser_processes_started"] == 0, "browser started"
    assert report["chart_count"] == 18, "expected eighteen charts"
    assert set(map(tuple, report["market_feed_pairs"])) == {
        (c, f) for c in MARKETS for f in FEEDS
    }, "market/feed matrix incomplete"
    assert len(report["chart_sizes"]) == 18 and all(n == 100 for n in report["chart_sizes"]), (
        "source chart shorter than Top 100"
    )
    assert report["missing_installs"] == 0, "missing install displays"
    assert report["missing_min_installs"] == 0, "missing numeric minimum installs"
    assert report["run_status"] == "succeeded", "collection did not succeed"
    assert report["elapsed_seconds"] < 60, "elapsed time at least sixty seconds"


def _count_attempts(database):
    if not database.exists():
        return 0
    with sqlite3.connect(database) as conn:
        return conn.execute("SELECT count(*) FROM request_observations").fetchone()[0]


def measure(data_dir, phase):
    database = data_dir / "casual-scout.sqlite3"
    before_attempts = _count_attempts(database)
    command = [
        sys.executable,
        "-m",
        "casual_scout",
        "collect",
        "--platform",
        "android",
        "--countries",
        ",".join(MARKETS),
        "--data-dir",
        str(data_dir),
    ]
    browser_pids = set()
    sample_errors = []
    log_path = data_dir.parent / (phase + ".log")
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        parent = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                for child in parent.children(recursive=True):
                    try:
                        if any(name in child.name().lower() for name in BROWSERS):
                            browser_pids.add(child.pid)
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as error:
                sample_errors.append(str(error))
            time.sleep(0.02)
    elapsed = time.perf_counter() - started
    report = {
        "phase": phase,
        "elapsed_seconds": elapsed,
        "exit_code": process.returncode,
        "browser_processes_started": len(browser_pids),
        "process_sampling_errors": sample_errors,
        "process_sample_interval_seconds": 0.02,
        "command": command,
        "log_path": str(log_path),
        "data_directory": str(data_dir),
    }
    if not database.exists():
        report.update(accepted=False, acceptance_error="collection created no database")
        return report
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        run = conn.execute(
            "SELECT id,status,started_at FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None:
            report.update(accepted=False, acceptance_error="collection created no run")
            return report
        charts = conn.execute(
            """SELECT c.country,c.collection,mr.received_count,mr.valid_count,mr.chart_status,
            mr.enrichment_status,s.id snapshot_id FROM market_runs mr JOIN charts c ON c.id=mr.chart_id
            LEFT JOIN snapshots s ON s.market_run_id=mr.id WHERE mr.run_id=? ORDER BY c.country,c.collection""",
            (run["id"],),
        ).fetchall()
        entries = conn.execute(
            """SELECT c.country,e.app_id,mv.id metadata_version_id,mv.installs,mv.min_installs,mv.fetched_at
            FROM market_runs mr JOIN charts c ON c.id=mr.chart_id JOIN snapshots s ON s.market_run_id=mr.id
            JOIN entries e ON e.snapshot_id=s.id LEFT JOIN snapshot_metadata sm ON sm.snapshot_id=s.id AND sm.app_id=e.app_id
            LEFT JOIN metadata_versions mv ON mv.id=sm.metadata_version_id WHERE mr.run_id=?""",
            (run["id"],),
        ).fetchall()
        evidence = [
            dict(row) for row in conn.execute("SELECT hash,path,size_bytes FROM raw_responses")
        ]
    report.update(
        run_id=run["id"],
        run_status=run["status"],
        chart_count=len(charts),
        charts=[dict(row) for row in charts],
        chart_sizes=[row["valid_count"] for row in charts],
        market_feed_pairs=[(row["country"], row["collection"]) for row in charts],
        missing_installs=sum(row["installs"] is None for row in entries),
        missing_min_installs=sum(row["min_installs"] is None for row in entries),
        unique_package_country_pairs=len({(row["country"], row["app_id"]) for row in entries}),
        cache_hits=sum(row["metadata_version_id"] is not None for row in entries)
        - len(
            {
                row["metadata_version_id"]
                for row in entries
                if row["fetched_at"] is not None and row["fetched_at"] >= run["started_at"]
            }
        ),
        http_attempts=_count_attempts(database) - before_attempts,
        evidence=evidence,
    )
    try:
        assert_acceptance(report)
        assert process.returncode == 0, "CLI failed"
        assert not sample_errors, "process sampling incomplete"
        report["accepted"] = True
    except AssertionError as error:
        report.update(accepted=False, acceptance_error=str(error))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="JSON report outside production data"
    )
    parser.add_argument(
        "--live", action="store_true", help="Explicitly run Google Play network requests"
    )
    parser.add_argument("--pairs", type=int, default=3)
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this benchmark performs network collection")
    if args.pairs < 1:
        parser.error("--pairs must be positive")
    # Keep temporary directories after measurement so report evidence references remain usable.
    report = {
        "measured": True,
        "source_contract": "POST batchexecute charts; GET details",
        "runs": [],
    }
    for index in range(args.pairs):
        root = Path(tempfile.mkdtemp(prefix="google-play-benchmark-"))
        data = root / "data"
        data.mkdir()
        report["runs"].append(measure(data, f"cold-{index + 1}"))
        report["runs"].append(measure(data, f"warm-{index + 1}"))
        report["accepted"] = len(report["runs"]) == 6 and all(
            run["accepted"] for run in report["runs"]
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(args.output)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
