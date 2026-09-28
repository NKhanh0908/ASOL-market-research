from datetime import datetime
from hashlib import sha256
from pathlib import Path

from casual_scout.ai.contracts import EvaluationRequest, ProviderReply


class FakeProvider:
    provider_id = "test-only"
    model_id = "fixture-v1"

    def __init__(self, *, estimate=None, reply=None, error=None, on_complete=None):
        self.estimate = estimate
        self.reply = reply or ProviderReply(output={"schema_version": "1", "recommendations": []})
        self.error = error
        self.on_complete = on_complete
        self.calls = 0
        self.inputs = []

    def estimate_cost(self, canonical_input):
        return self.estimate

    def complete(self, canonical_input):
        self.calls += 1
        self.inputs.append(canonical_input)
        if self.on_complete:
            self.on_complete()
        if self.error:
            raise self.error
        return self.reply


def request(key="request-1"):
    return EvaluationRequest(
        request_key=key,
        analysis_date="2026-09-25",
        markets=("vn",),
        provider_id=None,
        model_id=None,
        prompt_version="p4-v1",
        prompt_hash=sha256(b"p4-v1").hexdigest(),
        schema_version="1",
        canonical_input={"messages": [], "manifest": {}},
        evidence=(),
        policy={"enabled": False, "max_cost_per_run_usd": None},
    )


def valid_output():
    return {"schema_version": "1", "recommendations": [{
        "concept": "A short-session sorting prototype", "subgenre": "Puzzle", "mechanic": "Sort",
        "why_now": {"inference": "Worth a prototype investigation, not proof of demand.",
                    "evidence_ids": ["e1"]},
        "observations": [{"evidence_id": "e1"}],
        "scope": "prototype", "features": ["One sorting interaction and a small level set"],
        "assumptions": ["Experienced generalist team; no live operations"],
        "roles": ["gameplay developer", "designer"],
        "team_size": {"min": 1, "max": 2},
        "timeline_weeks": {"min": 2, "max": 4},
        "feasibility": "insufficient evidence",
        "rubric": {"evidence_strength": "Single observation only",
                   "market_signal": "No comparable baseline",
                   "differentiation": "Hypothesis to test, not established novelty",
                   "delivery_risk": "Level design effort is uncertain"},
        "risks": ["Rank alone does not establish player demand"],
        "unknowns": ["Retention and monetization are unknown"],
        "validation_questions": ["Does a playtest support the sorting interaction?"]
    }]}


def seed_ai_evidence(repo):
    """Persist two real, complete VN charts and matching P3 analytics."""
    from casual_scout.analysis.service import AnalysisService
    from casual_scout.collection.jobs import JobService
    from casual_scout.models import Chart, HttpResult
    from casual_scout.providers.apple import parse_chart

    fixture = (Path(__file__).resolve().parents[1] / "docs/core/research/evidence/"
               "2026-09-10-ios-p1/vn-casual-100.json")
    body = fixture.read_bytes()
    jobs = JobService(repo)
    for day in ("2026-09-24", "2026-09-25"):
        run_id = jobs.submit("manual", ["vn"], "ai-seed-" + day)
        reply = HttpResult(
            url="https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json",
            started_at=datetime.fromisoformat(day + "T08:00:00+00:00"),
            elapsed_ms=1, status=200, body=body,
            headers={"content-type": "application/json"}, error=None,
        )
        repo.save_snapshot(run_id, reply, parse_chart(body, Chart("vn")))
        jobs.finish(run_id, "succeeded")
        AnalysisService(repo).analyze_date(day, ["vn"])
