from dataclasses import replace
from threading import Event
from time import monotonic, sleep

from fastapi.testclient import TestClient

from casual_scout.ai.provider import ProviderQuota
from casual_scout.ai.settings import AISettings
from casual_scout.ai.worker import EvaluationWorker
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app
from tests.ai_support import FakeProvider, seed_ai_evidence
from tests.test_ai_web import NoopScheduler, confirm, preflight


def runtime_app(tmp_path, provider=None):
    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    return create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler(),
                      ai_provider=provider or FakeProvider(),
                      ai_settings=AISettings(enabled=True, cost_mode="free_tier",
                                             free_tier_confirmed=True,
                                             allow_unknown_cost_confirmation=True))


def test_worker_lifecycle_and_read_only_startup(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(EvaluationWorker, "recover_orphans", lambda self: events.append("recover"))
    original_close = EvaluationWorker.close
    def close(self):
        events.append("close")
        original_close(self)
    monkeypatch.setattr(EvaluationWorker, "close", close)
    app = runtime_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert events == ["recover"]
        assert client.get("/dashboard").status_code == 200
        assert client.get("/recommendations").status_code == 200
        assert app.state.ai_engine.provider.calls == 0
    assert events == ["recover", "close"]


def test_confirmation_returns_before_provider_finishes_and_busy_is_conflict(tmp_path):
    entered, release = Event(), Event()
    def block():
        entered.set()
        assert release.wait(5)
    app = runtime_app(tmp_path, FakeProvider(on_complete=block))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.get("/dashboard")
        first_quote = preflight(client).json()["quote"]
        try:
            response = confirm(client, first_quote)
            assert response.status_code == 202
            assert entered.wait(2)
            run_id = response.json()["run_id"]
            assert client.get(f"/api/recommendations/{run_id}").json()["status"] == "running"
            assert confirm(client, first_quote).json() == response.json()
            assert confirm(client, preflight(client).json()["quote"]).status_code == 409
        finally:
            release.set()


def test_preflight_exposes_frozen_policy_and_status_safe_fields(tmp_path):
    app = runtime_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.get("/dashboard")
        ready = preflight(client).json()
        assert ready["max_output_tokens"] == 2000
        assert ready["timeout_seconds"] == 60
        assert ready["free_tier_confirmed"] is True
        assert ready["cost_mode"] == "free_tier"
        assert ready["warnings"]
        run = app.state.ai_engine.submit(app.state.ai_engine.prepare("2026-09-25", ("vn",)), True)
        response = client.get(f"/api/recommendations/{run['id']}").json()
        assert {"actual_cost_usd", "cost_method", "safe_error", "ended_at"} <= response.keys()
        assert response["warnings"] == run["policy"]["warnings"]
        assert "system_prompt" not in str(response)
        assert "policy" not in response


def test_cli_serve_passes_explicit_runtime_configuration(tmp_path, monkeypatch):
    from casual_scout import cli
    from casual_scout.ai import settings as ai_settings_module
    from casual_scout.web import app as app_module
    provider, policy = FakeProvider(), AISettings(enabled=True)
    seen = {}
    monkeypatch.setattr(ai_settings_module, "load_ai_runtime", lambda: (policy, provider))
    def capture(settings, **kwargs):
        seen.update(kwargs)
        return object()
    monkeypatch.setattr(app_module, "create_app", capture)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    assert cli.main(["serve", "--data-dir", str(tmp_path)]) == 0
    assert seen == {"ai_settings": policy, "ai_provider": provider}


def terminal(client, run_id):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        run = client.get(f"/api/recommendations/{run_id}").json()
        if run["status"] not in {"queued", "running"}:
            return run
        sleep(0.01)
    raise AssertionError("Worker did not finish")


def test_startup_marks_confirmed_orphan_terminal_without_call(tmp_path, monkeypatch):
    app = runtime_app(tmp_path)
    engine = app.state.ai_engine
    run = engine.submit(engine.prepare("2026-09-25", ("vn",)), True)
    monkeypatch.setattr(EvaluationWorker, "_owner_confirmed_dead", staticmethod(lambda _: True))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        persisted = client.get(f"/api/recommendations/{run['id']}").json()
        assert persisted["status"] == "failed"
        assert persisted["error_category"] == "dispatch_failed"
        assert engine.provider.calls == 0


def test_direct_app_defaults_disabled_and_injected_app_bypasses_config(tmp_path, monkeypatch):
    def unexpected_load(*args, **kwargs):
        raise AssertionError("Direct app construction must not read local configuration")
    monkeypatch.setattr("casual_scout.ai.settings.load_ai_runtime", unexpected_load)
    app = create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler())
    assert app.state.ai_engine.settings.enabled is False
    assert app.state.ai_engine.provider is None
    injected = runtime_app(tmp_path / "injected")
    assert injected.state.ai_engine.settings.enabled is True
    with TestClient(injected, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/dashboard").status_code == 200
        assert injected.state.ai_engine.provider.calls == 0
    app.state.ai_worker.close()


def test_old_confirmed_quote_replays_after_fifty_newer_records(tmp_path):
    app = runtime_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.get("/dashboard")
        quote = preflight(client).json()["quote"]
        response = confirm(client, quote)
        terminal(client, response.json()["run_id"])
        engine = app.state.ai_engine
        engine.settings = replace(engine.settings, enabled=False)
        for _ in range(51):
            engine.submit(engine.prepare("2026-09-25", ("vn",)))
        assert response.json()["run_id"] not in {run["id"] for run in engine.store.list_runs()}
        assert confirm(client, quote).json() == response.json()
        assert engine.provider.calls == 1


def test_quota_error_is_safe_terminal_status_and_cost_remains_unknown(tmp_path):
    app = runtime_app(tmp_path, FakeProvider(error=ProviderQuota(
        usage={"input_tokens": 7, "api_key": "secret"})))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.get("/dashboard")
        response = confirm(client, preflight(client).json()["quote"])
        run = terminal(client, response.json()["run_id"])
        assert run["status"] == "failed"
        assert run["error_category"] == "provider_quota"
        assert run["safe_error"] == "AI provider quota is exhausted."
        assert run["usage"] == {"input_tokens": 7}
        assert run["actual_cost_usd"] is run["cost_method"] is None
        assert "secret" not in str(run)
