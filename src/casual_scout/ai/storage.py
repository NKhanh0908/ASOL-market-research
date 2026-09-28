"""Short SQLite transactions for durable, immutable AI evaluations."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

import psutil

from casual_scout.ai.contracts import EvaluationRequest, canonical_json
from casual_scout.storage import Repository


class EvaluationBusy(RuntimeError):
    """Another evaluation is queued or running."""


_FORBIDDEN_KEYS = {
    "authorization", "api_key", "access_token", "password", "client_secret",
    "headers", "request_headers", "response_headers", "raw_response",
    "raw_exception", "exception",
}
_USAGE_KEYS = {
    "input_tokens", "output_tokens", "total_tokens", "prompt_tokens",
    "completion_tokens", "cached_tokens", "reasoning_tokens",
}
_RAW_ENVELOPE_KEYS = {
    "candidates", "choices", "usagemetadata", "promptfeedback",
    "responseid", "modelversion", "providerpayload", "providerresponse",
    "rawproviderresponse", "rawresponse", "httpresponse", "responseenvelope",
    "requestenvelope",
}
_SAFE_ERRORS = {
    "disabled": "AI evaluation is disabled.",
    "provider_not_configured": "AI provider is not configured.",
    "budget_missing": "A positive per-run USD budget is required.",
    "budget_exceeded": "Estimated cost exceeds the per-run USD budget.",
    "unknown_cost_confirmation_disabled": "Unknown cost is not permitted by the current policy.",
    "invalid_settings": "AI evaluation settings are invalid.",
    "invalid_free_tier_policy": "Free-tier evaluation policy is incomplete or invalid.",
    "insufficient_evidence": "Selected markets have insufficient source evidence.",
    "daily_limit_reached": "Daily free-tier evaluation limit reached.",
    "configuration_changed": "AI configuration changed after preflight.",
    "dispatch_failed": "Evaluation could not be started.",
    "interrupted_uncertain": "Evaluation was interrupted; billing outcome is unknown.",
    "timeout_uncertain": "AI provider timed out; billing outcome is unknown.",
    "provider_quota": "AI provider quota is exhausted.",
    "provider_failure": "AI provider could not complete the evaluation.",
    "invalid_output": "AI provider returned invalid structured output.",
    "unsupported_claim": "AI output contains an unsupported claim.",
    "provider_timeout": "AI provider timed out; billing outcome is unknown.",
    "timeout": "AI provider timed out; billing outcome is unknown.",
    "invalid_response": "AI provider returned an invalid response.",
    "provider_error": "AI provider could not complete the evaluation.",
}


def _check_sensitive(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            if key.lower() in _FORBIDDEN_KEYS:
                raise ValueError("sensitive content cannot be persisted")
            _check_sensitive(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _check_sensitive(nested)


def _check_result(value: dict) -> None:
    if not isinstance(value, dict) or not value.keys() <= {"schema_version", "recommendations"}:
        raise ValueError("result must use the evaluated output shape")
    _check_sensitive(value)

    def check_envelope(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = key.casefold().replace("_", "").replace("-", "")
                if normalized in _RAW_ENVELOPE_KEYS:
                    raise ValueError("raw provider envelope cannot be persisted")
                check_envelope(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                check_envelope(nested)

    check_envelope(value)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _evidence_values(request: EvaluationRequest) -> list[tuple]:
    values = [
        (
            item.evidence_id, item.analysis_date, item.country, item.app_id,
            item.snapshot_id, item.analytics_id, item.metadata_version_id,
        )
        for item in request.evidence
    ]
    return sorted(values)


class EvaluationStore:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    @staticmethod
    def _decode(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
        run = dict(row)
        for column, key in (
            ("input_json", "input"), ("result_json", "result"),
            ("usage_json", "usage"), ("markets_json", "markets"),
            ("policy_json", "policy"),
        ):
            value = run.pop(column)
            run[key] = json.loads(value) if value is not None else None
        evidence = db.execute(
            "SELECT evidence_id,analysis_date,country,app_id,snapshot_id,analytics_id,"
            "metadata_version_id FROM ai_run_evidence WHERE run_id=? ORDER BY evidence_id",
            (run["id"],),
        ).fetchall()
        run["evidence"] = [dict(item) for item in evidence]
        return run

    def get(self, run_id: str) -> dict:
        with closing(self.repo._connect()) as db:
            row = db.execute("SELECT * FROM ai_evaluation_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return self._decode(db, row)

    def list_runs(self, limit: int = 50) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with closing(self.repo._connect()) as db:
            rows = db.execute(
                "SELECT * FROM ai_evaluation_runs ORDER BY created_at DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._decode(db, row) for row in rows]

    def active(self) -> dict | None:
        with closing(self.repo._connect()) as db:
            row = db.execute(
                "SELECT * FROM ai_evaluation_runs WHERE status IN ('queued','running')"
            ).fetchone()
            return None if row is None else self._decode(db, row)

    @staticmethod
    def _free_tier_attempts(db: sqlite3.Connection, day: str) -> int:
        return db.execute(
            "SELECT count(*) FROM ai_evaluation_runs "
            "WHERE status != 'blocked' "
            "AND json_extract(policy_json,'$.cost_mode')='free_tier' "
            "AND json_extract(policy_json,'$.reservation_day')=?",
            (day,),
        ).fetchone()[0]

    def free_tier_attempts(self, day: str) -> int:
        """Read the durable daily attempt count for preflight display."""
        with closing(self.repo._connect()) as db:
            return self._free_tier_attempts(db, day)

    def create(self, request: EvaluationRequest, *, blocked_reason: str | None = None) -> dict:
        _check_sensitive(request.canonical_input)
        _check_sensitive(request.policy)
        input_json = canonical_json(request.canonical_input)
        policy_json = canonical_json(request.policy)
        markets_json = canonical_json(list(request.markets))
        evidence = _evidence_values(request)
        fingerprint = (
            request.analysis_date, markets_json, request.provider_id, request.model_id,
            request.prompt_version, request.prompt_hash, request.schema_version,
            input_json, policy_json, request.rerun_of,
        )
        with self.repo._write_connection() as db:
            existing = db.execute(
                "SELECT * FROM ai_evaluation_runs WHERE request_key=?", (request.request_key,)
            ).fetchone()
            if existing is not None:
                old = tuple(existing[key] for key in (
                    "analysis_date", "markets_json", "provider_id", "model_id",
                    "prompt_version", "prompt_hash", "schema_version", "input_json",
                    "policy_json", "rerun_of",
                ))
                old_evidence = db.execute(
                    "SELECT evidence_id,analysis_date,country,app_id,snapshot_id,analytics_id,"
                    "metadata_version_id FROM ai_run_evidence WHERE run_id=? ORDER BY evidence_id",
                    (existing["id"],),
                ).fetchall()
                if old != fingerprint or [tuple(row) for row in old_evidence] != evidence:
                    raise ValueError("request key was already used for different content")
                return self._decode(db, existing)

            if request.policy.get("cost_mode") == "free_tier" and blocked_reason is None:
                today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
                if (request.policy.get("max_runs_per_day") != 5
                        or isinstance(request.policy.get("max_runs_per_day"), bool)
                        or request.policy.get("reservation_day") != today):
                    raise ValueError("invalid free-tier reservation policy")
                used = self._free_tier_attempts(db, today)
                if used >= 5:
                    blocked_reason = "daily_limit_reached"

            if blocked_reason is not None:
                self._validate_category(blocked_reason)
            status = "blocked" if blocked_reason is not None else "queued"
            owner_pid = None if status == "blocked" else os.getpid()
            owner_birth = None if status == "blocked" else psutil.Process().create_time()
            run_id = str(uuid4())
            now = _now()
            try:
                db.execute(
                    "INSERT INTO ai_evaluation_runs (id,request_key,status,analysis_date,markets_json,"
                    "created_at,ended_at,provider_id,model_id,prompt_version,prompt_hash,"
                    "schema_version,input_json,input_hash,policy_json,error_category,safe_error,"
                    "owner_pid,owner_birth,rerun_of) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id, request.request_key, status, request.analysis_date, markets_json,
                        now, now if status == "blocked" else None, request.provider_id,
                        request.model_id, request.prompt_version, request.prompt_hash,
                        request.schema_version, input_json,
                        sha256(input_json.encode("utf-8")).hexdigest(), policy_json,
                        blocked_reason, self._safe_error(blocked_reason), owner_pid,
                        owner_birth, request.rerun_of,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "ai_one_active" in str(exc):
                    raise EvaluationBusy("another evaluation is active") from exc
                raise
            db.executemany(
                "INSERT INTO ai_run_evidence(run_id,evidence_id,analysis_date,country,app_id,"
                "snapshot_id,analytics_id,metadata_version_id) VALUES (?,?,?,?,?,?,?,?)",
                [(run_id, *item) for item in evidence],
            )
            db.execute("INSERT INTO ai_run_evidence_seals(run_id) VALUES (?)", (run_id,))
            row = db.execute("SELECT * FROM ai_evaluation_runs WHERE id=?", (run_id,)).fetchone()
            return self._decode(db, row)

    def claim(self, run_id: str, owner_pid: int, owner_birth: float) -> bool:
        with self.repo._write_connection() as db:
            cursor = db.execute(
                "UPDATE ai_evaluation_runs SET status='running',started_at=?,owner_pid=?,"
                "owner_birth=? WHERE id=? AND status='queued'",
                (_now(), owner_pid, owner_birth, run_id),
            )
            return cursor.rowcount == 1

    def fail_if_owned(
        self, run_id: str, expected_status: str, owner_pid: int, owner_birth: float,
        error_category: str,
    ) -> bool:
        """Fail only the exact active row observed by a worker or recovery scan."""
        if expected_status not in {"queued", "running"}:
            raise ValueError("expected status must be active")
        self._validate_category(error_category)
        with self.repo._write_connection() as db:
            cursor = db.execute(
                "UPDATE ai_evaluation_runs SET status='failed',ended_at=?,error_category=?,"
                "safe_error=? WHERE id=? AND status=? AND owner_pid=? AND owner_birth=?",
                (
                    _now(), error_category, self._safe_error(error_category), run_id,
                    expected_status, owner_pid, owner_birth,
                ),
            )
            return cursor.rowcount == 1

    @staticmethod
    def _validate_category(category: str) -> None:
        if not isinstance(category, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", category) is None:
            raise ValueError("error category must be a safe identifier")

    @staticmethod
    def _safe_error(category: str | None) -> str | None:
        if category is None:
            return None
        return _SAFE_ERRORS.get(category, "Evaluation could not be completed.")

    def finish(
        self, run_id: str, status: str, *, result: dict | None = None,
        usage: dict | None = None, actual_cost_usd: str | None = None,
        cost_method: str | None = None, error_category: str | None = None,
        safe_error: str | None = None,
    ) -> dict:
        if status not in {"succeeded", "partial", "failed"}:
            raise ValueError("invalid finish status")
        if result is not None:
            _check_result(result)
        result_json = canonical_json(result) if result is not None else None
        if usage is not None:
            if not isinstance(usage, dict):
                raise ValueError("usage must be a dictionary")
            usage = {
                key: value for key, value in usage.items()
                if key in _USAGE_KEYS and type(value) is int and value >= 0
            }
        usage_json = canonical_json(usage) if usage is not None else None
        if actual_cost_usd is not None:
            try:
                amount = Decimal(actual_cost_usd)
            except (InvalidOperation, TypeError):
                raise ValueError("invalid USD cost") from None
            if not amount.is_finite() or amount < 0:
                raise ValueError("invalid USD cost")
            actual_cost_usd = str(amount)
        if (actual_cost_usd is None) != (cost_method is None):
            raise ValueError("USD cost requires explicit provenance and amount")
        if cost_method is not None and cost_method not in {
            "provider_reported_usd", "verified_conversion"
        }:
            raise ValueError("unverified cost method")
        if error_category is not None:
            self._validate_category(error_category)
        fixed_error = self._safe_error(error_category)
        if safe_error is not None and safe_error != fixed_error:
            raise ValueError("error text must be engine-owned")
        with self.repo._write_connection() as db:
            cursor = db.execute(
                "UPDATE ai_evaluation_runs SET status=?,ended_at=?,result_json=?,usage_json=?,"
                "actual_cost_usd=?,cost_method=?,error_category=?,safe_error=? "
                "WHERE id=? AND (status='running' OR (status='queued' AND ?='failed'))",
                (
                    status, _now(), result_json, usage_json, actual_cost_usd, cost_method,
                    error_category, fixed_error, run_id, status,
                ),
            )
            if cursor.rowcount != 1:
                exists = db.execute("SELECT 1 FROM ai_evaluation_runs WHERE id=?", (run_id,)).fetchone()
                if exists is None:
                    raise KeyError(run_id)
                raise ValueError("invalid AI run transition")
            row = db.execute("SELECT * FROM ai_evaluation_runs WHERE id=?", (run_id,)).fetchone()
            return self._decode(db, row)
