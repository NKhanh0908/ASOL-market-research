"""Single-threaded manual dispatch and conservative recovery of AI evaluations."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import psutil

from casual_scout.ai.service import EvaluationEngine
from casual_scout.ai.storage import EvaluationStore


class EvaluationWorker:
    def __init__(self, engine: EvaluationEngine, store: EvaluationStore) -> None:
        self.engine = engine
        self.store = store
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-evaluation")

    def submit(self, run_id: str) -> None:
        """Dispatch a locally owned queued run; the engine claims it once."""
        run = self.store.get(run_id)
        if run["status"] != "queued":
            return
        owner_pid = os.getpid()
        owner_birth = psutil.Process().create_time()
        if (run["owner_pid"], run["owner_birth"]) != (owner_pid, owner_birth):
            raise ValueError("queued run belongs to a different process")
        try:
            self._executor.submit(self._execute, run_id, owner_pid, owner_birth)
        except Exception:  # noqa: BLE001 - no task was accepted by the executor
            self.store.fail_if_owned(
                run_id, "queued", owner_pid, owner_birth, "dispatch_failed",
            )

    def _execute(self, run_id: str, owner_pid: int, owner_birth: float) -> None:
        try:
            self.engine.run(run_id)
        except BaseException:  # noqa: BLE001 - a background task must leave a terminal record
            run = self.store.get(run_id)
            if run["status"] in {"queued", "running"}:
                category = (
                    "interrupted_uncertain" if run["status"] == "running" else "dispatch_failed"
                )
                self.store.fail_if_owned(
                    run_id, run["status"], owner_pid, owner_birth, category,
                )

    def recover_orphans(self) -> int:
        """Fail an active run only when its recorded process is confirmed gone."""
        run = self.store.active()
        if run is None or not self._owner_confirmed_dead(run):
            return 0
        category = "interrupted_uncertain" if run["status"] == "running" else "dispatch_failed"
        return int(self.store.fail_if_owned(
            run["id"], run["status"], run["owner_pid"], run["owner_birth"],
            category,
        ))

    @staticmethod
    def _owner_confirmed_dead(run: dict) -> bool:
        pid, birth = run["owner_pid"], run["owner_birth"]
        if type(pid) is not int or pid <= 0 or type(birth) not in {int, float}:
            return False
        try:
            return psutil.Process(pid).create_time() != birth
        except psutil.NoSuchProcess:
            return True
        except (psutil.AccessDenied, OSError):
            return False

    def close(self) -> None:
        """Wait for accepted work to finish; never imply a provider call was canceled."""
        self._executor.shutdown(wait=True)
