from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def launch_collector(run_id: str, data_dir: Path) -> int:
    resolved_dir = Path(data_dir).resolve()
    log_dir = resolved_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{run_id}.log"
    log_file = log_path.open("a", encoding="utf-8")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "casual_scout",
                "work",
                "--run-id",
                run_id,
                "--data-dir",
                str(resolved_dir),
            ],
            shell=False,
            creationflags=creationflags,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        return proc.pid
    except Exception as exc:
        log_file.close()
        from casual_scout.collection.jobs import JobService
        from casual_scout.storage import Repository

        repo = Repository(resolved_dir)
        repo.initialize()
        jobs = JobService(repo)
        jobs.finish(run_id, "failed", {"launch_error": str(exc)})
        raise
