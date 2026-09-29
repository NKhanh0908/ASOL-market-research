from dataclasses import replace
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from casual_scout.ai.settings import AISettings
from casual_scout.ai.storage import EvaluationStore
from casual_scout.config import IOS_COLLECTION_COUNTRIES, Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app
from tests.ai_support import FakeProvider, seed_ai_evidence


class NoopScheduler:
    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def ai_client(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    provider = FakeProvider()
    settings = AISettings(enabled=True, cost_mode="free_tier", free_tier_confirmed=True,
                          allow_unknown_cost_confirmation=True)
    app = create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler(),
                     ai_provider=provider, ai_settings=settings)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.get("/dashboard", params={"date": "2026-09-25", "country": "vn"})
        yield client, provider, EvaluationStore(repo), app


def headers(client):
    return {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": client.cookies["csrftoken"]}


def preflight(client, market="vn", date="2026-09-25"):
    return client.post("/api/recommendations/preflight", headers=headers(client),
                       json={"analysis_date": date, "market": market})


def confirm(client, quote, consent=True):
    return client.post("/api/recommendations/runs", headers=headers(client),
                       json={"quote": quote, "confirm_unknown": consent})


def wait_terminal(client, run_id):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        response = client.get(f"/api/recommendations/{run_id}")
        assert response.status_code == 200
        if response.json()["status"] not in {"queued", "running"}:
            return response
        sleep(0.01)
    pytest.fail("The offline fake evaluation did not finish within five seconds")


def test_get_pages_and_status_never_call_provider(ai_client):
    client, provider, store, _ = ai_client
    assert client.get("/recommendations").status_code == 200
    ready = preflight(client).json()
    assert ready["state"] == "ready"
    run_id = confirm(client, ready["quote"]).json()["run_id"]
    assert client.get("/dashboard").status_code == 200
    assert client.get("/recommendations").status_code == 200
    assert client.get(f"/recommendations/{run_id}").status_code == 200
    assert client.get(f"/api/recommendations/{run_id}").status_code == 200
    wait_terminal(client, run_id)
    assert provider.calls == 1
    assert store.get(run_id)["status"] in {"succeeded", "partial"}


def test_missing_configuration_persists_blocked_only_on_explicit_post(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    with TestClient(create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler()),
                    base_url="http://127.0.0.1:8000") as client:
        assert client.get("/dashboard").status_code == 200
        assert client.get("/recommendations").status_code == 200
        assert EvaluationStore(repo).list_runs() == []
        response = preflight(client)
        assert response.status_code == 200
        assert response.json()["state"] == "blocked"
        assert EvaluationStore(repo).get(response.json()["run_id"])["status"] == "blocked"


def test_confirmed_quote_is_one_call_and_replay_reuses_run(ai_client):
    client, provider, store, _ = ai_client
    ready = preflight(client).json()
    assert ready["scope"] == {"analysis_date": "2026-09-25", "markets": ["vn"]}
    assert ready["provider_id"] == "test-only"
    assert ready["model_id"] == "fixture-v1"
    assert ready["requires_unknown_confirmation"] is True
    assert ready["attempts_remaining"] == 5
    first = confirm(client, ready["quote"])
    second = confirm(client, ready["quote"])
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    wait_terminal(client, first.json()["run_id"])
    assert len(store.list_runs()) == provider.calls == 1
    assert first.json()["url"] == "/recommendations/" + first.json()["run_id"]


def test_all_scope_uses_nine_verified_collection_markets(ai_client):
    client, _, _, _ = ai_client
    response = preflight(client, "all")
    assert response.status_code == 200
    assert response.json()["scope"]["markets"] == list(IOS_COLLECTION_COUNTRIES)


@pytest.mark.parametrize("market,date", [
    ("zz", "2026-09-25"), ("vn,zz", "2026-09-25"),
    ("vn", "2026-09-25T00:00:00"), ("vn", "2026-02-30"),
    (",".join(["vn"] * 13), "2026-09-25"),
])
def test_invalid_scope_rejected_before_preparing(ai_client, market, date):
    client, provider, store, _ = ai_client
    response = preflight(client, market, date)
    assert response.status_code == 422
    assert store.list_runs() == []
    assert provider.calls == 0


def test_unconfirmed_quote_rejected_without_dispatch(ai_client):
    client, provider, store, _ = ai_client
    response = confirm(client, preflight(client).json()["quote"], consent=False)
    assert response.status_code == 422
    assert store.list_runs() == []
    assert provider.calls == 0


@pytest.mark.parametrize("change", ["input", "provider", "policy"])
def test_changed_preflight_requires_fresh_confirmation(ai_client, monkeypatch, change):
    client, provider, store, app = ai_client
    quote = preflight(client).json()["quote"]
    if change == "provider":
        provider.model_id = "different-model"
    elif change == "policy":
        app.state.ai_engine.settings = replace(app.state.ai_engine.settings, max_output_tokens=1999)
    else:
        original = app.state.ai_engine.prepare

        def changed(*args):
            prepared = original(*args)
            request = replace(prepared.request,
                              canonical_input={**prepared.request.canonical_input, "changed": True})
            return replace(prepared, request=request)

        monkeypatch.setattr(app.state.ai_engine, "prepare", changed)
    response = confirm(client, quote)
    assert response.status_code == 409
    assert store.list_runs() == []
    assert provider.calls == 0


def test_public_status_whitelists_persisted_content(ai_client):
    client, _, store, _ = ai_client
    run_id = confirm(client, preflight(client).json()["quote"]).json()["run_id"]
    response = wait_terminal(client, run_id)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == run_id
    assert body["status"] in {"succeeded", "partial"}
    assert "manifest" in body and "warnings" in body
    for forbidden in ("input", "canonical_input", "system_prompt", "request_key", "owner_pid", "evidence"):
        assert forbidden not in body
    assert store.get(run_id)["input"]["system_prompt"] not in response.text


def test_missing_run_is_404(ai_client):
    client, _, _, _ = ai_client
    assert client.get("/recommendations/missing").status_code == 404
    assert client.get("/api/recommendations/missing").status_code == 404
