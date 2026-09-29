"""Stored review pages render frozen evidence, never current analytics."""

import json
import os
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import psutil
import pytest
from ai_support import request, seed_ai_evidence, valid_output
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from casual_scout.ai.storage import EvaluationStore
from casual_scout.storage import Repository

TEMPLATES = Path(__file__).resolve().parents[1] / "src/casual_scout/web/templates"


def render(name, **context):
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape())
    env.globals["static_asset"] = lambda name: "/static/" + name + "?v=test"
    try:
        template = env.get_template(name)
    except TemplateNotFound:
        pytest.fail("Review template is not implemented: " + name)
    return template.render(active_tab="dashboard", platform="ios", **context)


@pytest.fixture
def store(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    return EvaluationStore(repo)


def stored_run(store, status="succeeded", count=1, reason=None, hash_value="a" * 64):
    manifest = {"e1": {"id": "e1", "metric": "chart_rank", "value": 7,
        "unit": "position", "market": "vn", "platform": "ios",
        "analysis_date": "2026-09-25", "observed_at": "2026-09-25T08:00:00Z",
        "snapshot_id": "frozen-snapshot", "app_id": "123", "raw_hash": hash_value}}
    req = replace(request(key="review-" + str(len(store.list_runs()) + 1)),
        provider_id="test-only", model_id="fixture-v1",
        canonical_input={"manifest": manifest, "messages": []})
    run = store.create(req, blocked_reason=reason if status == "blocked" else None)
    if status not in {"blocked", "queued"}:
        assert store.claim(run["id"], os.getpid(), psutil.Process().create_time())
        if status != "running":
            output = valid_output()
            output["recommendations"] = [deepcopy(output["recommendations"][0]) for _ in range(count)]
            run = store.finish(run["id"], status, result=output if status != "failed" else None,
                error_category=reason)
    run = store.get(run["id"])
    run["manifest"] = run["input"]["manifest"]
    run["warnings"] = ["Partial market coverage"] if status == "partial" else []
    return run


def test_history_empty_and_scope_cost_columns(store):
    assert "Chưa có lượt gợi ý AI" in render("recommendations.html", runs=[])
    run = stored_run(store)
    html = render("recommendations.html", runs=[run])
    for text in ("2026-09-25", "vn", "test-only", "fixture-v1", "succeeded", "Chưa xác định", run["created_at"]):
        assert text in html
    assert 'href="/dashboard"' in html
    assert html.count('class="nav-link') == 5


@pytest.mark.parametrize("count", [0, 1, 3])
def test_results_render_separate_evidence_inference_estimates(store, count):
    html = render("recommendation_run.html", run=stored_run(store, count=count))
    assert html.count('class="card ai-recommendation"') == count
    if not count:
        assert "Chưa có gợi ý đủ căn cứ" in html
        return
    for text in ("Dữ liệu quan sát", "Suy luận của AI", "Ước lượng theo giả định",
                 "chart_rank", "7", "position", "prototype", "gameplay developer",
                 "Single observation only", "Retention and monetization are unknown"):
        assert text in html
    assert "/evidence/" + "a" * 64 in html
    assert "snapshot_id=frozen-snapshot" in html and "platform=ios" in html and "country=vn" in html


@pytest.mark.parametrize("status,reason", [("queued", None), ("running", None),
    ("partial", None), ("failed", "timeout_uncertain"),
    ("blocked", "provider_not_configured"), ("blocked", "insufficient_evidence")])
def test_status_and_safe_failure_are_visible(store, status, reason):
    run = stored_run(store, status=status, reason=reason)
    html = render("recommendation_run.html", run=run)
    assert status in html and 'role="status"' in html
    assert "Chưa xác định" in html
    if reason:
        assert reason in html and run["safe_error"] in html
    if status == "partial":
        assert "Phạm vi dữ liệu chưa đầy đủ" in html
    assert "/static/recommendation_run.js?v=test" in html


def test_model_text_and_invalid_hash_are_not_html_or_links(store):
    run = stored_run(store, hash_value="javascript:alert(1)")
    run["result"]["recommendations"][0]["concept"] = "<script>alert(1)</script>"
    html = render("recommendation_run.html", run=run)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert '/evidence/javascript:' not in html


def test_frozen_page_survives_real_analytics_recalculation(store):
    from casual_scout.analysis.service import AnalysisService
    seed_ai_evidence(store.repo)
    run = stored_run(store)
    before = render("recommendation_run.html", run=run)
    with store.repo._write_connection() as db:
        db.execute("UPDATE daily_rank_analytics SET mechanic='Changed after evaluation'")
    AnalysisService(store.repo).analyze_date("2026-09-25", ["vn"])
    fresh = store.get(run["id"])
    fresh["manifest"] = fresh["input"]["manifest"]
    fresh["warnings"] = []
    assert render("recommendation_run.html", run=fresh) == before


def test_history_caps_rows_and_preserves_reported_zero_cost(store):
    run = stored_run(store)
    rows = [dict(run, id=f"run-{number}", actual_cost_usd="0.00") for number in range(51)]
    html = render("recommendations.html", runs=rows)
    assert "/recommendations/run-49" in html
    assert "/recommendations/run-50" not in html
    assert "0.00" in html and "Chưa xác định" not in html


def test_derived_observation_resolves_its_frozen_source(store):
    run = stored_run(store)
    run["manifest"]["e1"]["source_ids"] = ["base"]
    run["manifest"]["e1"]["derived"] = True
    run["manifest"]["base"] = {"metric": "chart_rank", "value": 31,
        "unit": "position", "market": "us", "analysis_date": "2026-09-24"}
    html = render("recommendation_run.html", run=run)
    assert "Nguồn tham chiếu: base" in html
    assert "31 position" in html and "us · 2026-09-24" in html


def test_rationale_only_citation_also_renders_frozen_observation(store):
    run = stored_run(store)
    run["manifest"]["rationale-source"] = {"metric": "chart_rank", "value": 42,
        "unit": "position", "market": "us", "analysis_date": "2026-09-24",
        "raw_hash": "b" * 64}
    run["result"]["recommendations"][0]["why_now"]["evidence_ids"] = ["rationale-source"]
    html = render("recommendation_run.html", run=run)
    assert "42 position" in html
    assert "us · 2026-09-24" in html
    assert "/evidence/" + "b" * 64 in html


def test_real_engine_result_route_keeps_original_chart_lineage_after_recalculation(store):
    from ai_support import FakeProvider
    from fastapi.testclient import TestClient

    from casual_scout.ai.contracts import ProviderReply
    from casual_scout.ai.service import EvaluationEngine
    from casual_scout.ai.settings import AISettings
    from casual_scout.analysis.service import AnalysisService
    from casual_scout.config import Settings
    from casual_scout.web.app import create_app

    class ManifestProvider(FakeProvider):
        def complete(self, canonical_input):
            self.calls += 1
            output = valid_output()
            evidence_id = next(key for key, item in canonical_input["manifest"].items()
                               if item["metric"] == "chart_rank")
            output["recommendations"][0]["observations"] = [{"evidence_id": evidence_id}]
            output["recommendations"][0]["why_now"]["evidence_ids"] = [evidence_id]
            return ProviderReply(output=output)

    class NoopScheduler:
        def start(self):
            pass

        def stop(self):
            pass

    seed_ai_evidence(store.repo)
    provider = ManifestProvider(estimate="0.01")
    engine = EvaluationEngine(store.repo, store,
        AISettings(enabled=True, max_cost_per_run_usd="0.05"), provider)
    prepared = engine.prepare("2026-09-25", ("vn",))
    queued = engine.submit(prepared)
    completed = engine.run(queued["id"])
    assert completed["status"] in {"succeeded", "partial"}
    ref_id = completed["result"]["recommendations"][0]["observations"][0]["evidence_id"]
    frozen = completed["input"]["manifest"][ref_id]
    app = create_app(Settings(store.repo.data_dir),
        scheduler_factory=lambda *_: NoopScheduler(), ai_provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        url = "/recommendations/" + completed["id"]
        response = client.get(url)
        assert response.status_code == 200
        before = response.text
        assert "snapshot_id=" + frozen["snapshot_id"] in before
        assert "/evidence/" + frozen["raw_hash"] in before
        assert frozen["observed_at"] in before
        with store.repo._write_connection() as db:
            db.execute("UPDATE daily_rank_analytics SET mechanic='Changed after evaluation'")
        AnalysisService(store.repo).analyze_date("2026-09-25", ["vn"])
        assert client.get(url).text == before
        assert provider.calls == 1


@pytest.mark.parametrize("initial,outcome", [("queued", "running"), ("running", "succeeded"),
    ("running", "partial"), ("running", "failed"), ("running", "blocked"),
    ("queued", "network-error"), ("succeeded", "succeeded")])
def test_polling_get_terminal_stop_and_manual_refresh(initial, outcome):
    script_path = TEMPLATES.parent / "static/recommendation_run.js"
    harness = r'''
const vm = require("node:vm");
const fs = require("node:fs");
const status = {dataset: {status: INITIAL, runId: "stored-id"}};
const warning = {hidden: true};
const refresh = {hidden: true, addEventListener: (event, fn) => { refresh.click = fn; }};
const timers = [], listeners = {}, calls = [];
let reloads = 0;
const context = {
  document: {getElementById: id => ({"ai-run-status":status, "ai-poll-warning":warning, "ai-refresh":refresh})[id]},
  window: {setTimeout: (fn, ms) => {timers.push({fn, ms}); return timers.length;},
    addEventListener: (event, fn) => {listeners[event] = fn;}, location: {reload: () => reloads++}},
  clearTimeout: () => {}, AbortController, encodeURIComponent,
  fetch: async (url, options) => {calls.push({url, method: options.method});
    if (OUTCOME === "network-error") throw new Error("offline");
    return {ok:true, json:async () => ({status:OUTCOME})};}
};
vm.runInNewContext(fs.readFileSync(SCRIPT_PATH, "utf8"), context);
(async () => {
  const initialCalls = calls.length;
  if (timers.length) await timers[0].fn();
  const afterPoll = {initialCalls, calls, reloads, timers:timers.length,
    delay:timers[0]?.ms, warningHidden:warning.hidden, refreshHidden:refresh.hidden};
  if (listeners.pagehide) listeners.pagehide();
  if (timers[1]) await timers[1].fn();
  afterPoll.callsAfterUnload = calls.length;
  console.log(JSON.stringify(afterPoll));
})();
'''
    harness = (harness.replace("INITIAL", json.dumps(initial))
        .replace("OUTCOME", json.dumps(outcome))
        .replace("SCRIPT_PATH", json.dumps(str(script_path))))
    completed = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    assert result["initialCalls"] == 0
    if initial == "succeeded":
        assert result["calls"] == [] and result["reloads"] == 0
        return
    assert result["delay"] == 2000
    assert result["calls"] == [{"url": "/api/recommendations/stored-id", "method": "GET"}]
    assert result["callsAfterUnload"] == 1
    assert result["reloads"] == (0 if outcome in {"running", "network-error"} else 1)
    if outcome == "network-error":
        assert result["warningHidden"] is False and result["refreshHidden"] is False
    else:
        assert result["timers"] == (2 if outcome == "running" else 1)
