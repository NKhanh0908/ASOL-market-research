"""Explicit, signed and session-bound web dispatch for existing AI evaluations."""

from contextlib import closing
from dataclasses import asdict, replace
from datetime import date
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

from casual_scout.ai.contracts import canonical_json
from casual_scout.ai.service import ConfirmationRequired
from casual_scout.ai.storage import EvaluationBusy
from casual_scout.config import IOS_COLLECTION_COUNTRIES


class ScopeRequest(BaseModel):
    analysis_date: str
    market: str = "vn"


class ConfirmRequest(BaseModel):
    quote: str
    confirm_unknown: bool = False


def _fingerprint(prepared):
    value = asdict(prepared)
    value["request"].pop("request_key")
    return sha256(canonical_json(value).encode()).hexdigest()


def public_run(run: dict) -> dict:
    """Expose persisted review data without provider input or private configuration."""
    result = {key: run.get(key) for key in (
        "id", "status", "analysis_date", "markets", "provider_id", "model_id",
        "result", "usage", "error_category", "safe_error", "created_at", "started_at",
        "ended_at", "actual_cost_usd", "cost_method",
    )}
    result["scope"] = {"analysis_date": run.get("analysis_date"), "markets": run.get("markets")}
    result["manifest"] = run.get("input", {}).get("manifest", {})
    result["warnings"] = run.get("policy", {}).get("warnings", [])
    return result


def ai_router(engine, security, templates, worker):
    router = APIRouter()
    signer = URLSafeTimedSerializer(security.serializer.secret_key, salt="ai-preflight")

    def authorized(request):
        session = request.cookies.get("session_id", "")
        if not security.validate_csrf_token(request.headers.get("X-CSRF-Token", ""), session):
            raise HTTPException(403, "Invalid CSRF token")
        if (engine.repo.data_dir / "MOCK_DATA.json").exists():
            raise HTTPException(403, "Mock demo is read-only")
        return session

    def find_existing_request(key):
        with closing(engine.repo._connect()) as db:
            row = db.execute("SELECT id FROM ai_evaluation_runs WHERE request_key=?", (key,)).fetchone()
        return engine.store.get(row["id"]) if row else None

    def run_response(run):
        return {"run_id": run["id"], "url": "/recommendations/" + run["id"]}

    def get_run(run_id):
        try:
            return engine.store.get(run_id)
        except KeyError:
            raise HTTPException(404, "Evaluation not found") from None

    @router.get("/recommendations")
    def list_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="recommendations.html",
            context={
                "request": request,
                "active_tab": "dashboard",
                "runs": [public_run(r) for r in engine.store.list_runs(limit=50)],
            },
        )

    @router.get("/recommendations/{run_id}")
    def detail_page(request: Request, run_id: str):
        return templates.TemplateResponse(
            request=request,
            name="recommendation_run.html",
            context={
                "request": request,
                "active_tab": "dashboard",
                "run": public_run(get_run(run_id)),
            },
        )

    @router.get("/api/recommendations/{run_id}")
    def status(run_id: str):
        return public_run(get_run(run_id))

    @router.post("/api/recommendations/preflight")
    def preflight(request: Request, scope: ScopeRequest):
        session = authorized(request)
        try:
            if len(scope.analysis_date) != 10:
                raise ValueError()
            date.fromisoformat(scope.analysis_date)
            markets = (
                tuple(IOS_COLLECTION_COUNTRIES)
                if scope.market == "all"
                else tuple(scope.market.split(","))
            )
            if (not 1 <= len(markets) <= 12 or len(set(markets)) != len(markets)
                    or not set(markets) <= set(IOS_COLLECTION_COUNTRIES)):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Invalid analysis scope") from None
        prepared = engine.prepare(scope.analysis_date, markets)
        if prepared.blocked_reason:
            try:
                run = engine.submit(prepared)
            except EvaluationBusy:
                raise HTTPException(409, "Another evaluation is active") from None
            return {"state": "blocked", "run_id": run["id"], "reason": prepared.blocked_reason}
        quote = signer.dumps(
            {
                "session": session,
                "day": scope.analysis_date,
                "markets": markets,
                "fingerprint": _fingerprint(prepared),
                "key": prepared.request.request_key,
            }
        )
        return {
            "state": "ready",
            "quote": quote,
            "scope": {"analysis_date": scope.analysis_date, "markets": markets},
            "provider_id": prepared.request.provider_id,
            "model_id": prepared.request.model_id,
            "requires_unknown_confirmation": prepared.requires_unknown_confirmation,
            "attempts_remaining": prepared.request.policy.get("attempts_remaining"),
            "estimated_cost_usd": prepared.estimated_cost_usd,
            **{key: prepared.request.policy.get(key) for key in (
                "max_cost_per_run_usd", "max_output_tokens", "timeout_seconds", "cost_mode",
                "free_tier_confirmed", "max_runs_per_day", "monetary_upper_bound_guaranteed",
                "manual_confirmation_required",
            )},
            "warnings": list(prepared.request.policy.get("warnings", [])) + (
                ["Free Tier is owner-confirmed; the application cannot verify billing tier or guarantee zero cost.",
                 "Pilot recommendations still require human quality review."]
                if prepared.request.policy.get("cost_mode") == "free_tier" else []
            ),
        }

    @router.post("/api/recommendations/runs", status_code=202)
    def confirm(request: Request, body: ConfirmRequest):
        session = authorized(request)
        try:
            quote = signer.loads(body.quote, max_age=300)
            if quote["session"] != session:
                raise BadSignature("wrong session")
        except (BadSignature, KeyError):
            raise HTTPException(403, "Invalid or expired preflight") from None
        existing = find_existing_request(quote["key"])
        if existing is not None:
            return run_response(existing)
        prepared = engine.prepare(quote["day"], tuple(quote["markets"]))
        if _fingerprint(prepared) != quote["fingerprint"]:
            raise HTTPException(409, "Preflight changed; confirm a fresh quote")
        prepared = replace(prepared, request=replace(prepared.request, request_key=quote["key"]))
        try:
            run = engine.submit(prepared, confirm_unknown=body.confirm_unknown)
        except ConfirmationRequired as error:
            raise HTTPException(422, str(error)) from None
        except EvaluationBusy:
            raise HTTPException(409, "Another evaluation is active") from None
        if run["status"] == "queued":
            worker.submit(run["id"])
        return run_response(run)

    return router
