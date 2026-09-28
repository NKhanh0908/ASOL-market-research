from datetime import datetime

from fastapi.testclient import TestClient

from casual_scout.config import Settings
from casual_scout.web.app import create_app
from tests.test_ai_web import NoopScheduler, ai_client, confirm, headers, preflight


def test_preflight_requires_csrf(tmp_path):
    with TestClient(create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler()),
                    base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/recommendations/preflight",
            headers={"Origin": "http://127.0.0.1:8000"},
            json={"analysis_date": "2026-09-25", "market": "vn"})
        assert response.status_code == 403


def test_confirmation_requires_csrf(ai_client):
    client, provider, _, _ = ai_client
    quote = preflight(client).json()["quote"]
    response = client.post("/api/recommendations/runs",
                           headers={"Origin": "http://127.0.0.1:8000"},
                           json={"quote": quote, "confirm_unknown": True})
    assert response.status_code == 403
    assert provider.calls == 0


def test_post_requires_local_origin(ai_client):
    client, provider, _, _ = ai_client
    response = client.post("/api/recommendations/preflight", headers={"X-CSRF-Token": client.cookies["csrftoken"]},
                           json={"analysis_date": "2026-09-25", "market": "vn"})
    assert response.status_code == 403
    assert provider.calls == 0


def test_tampered_quote_rejected(ai_client):
    client, provider, _, _ = ai_client
    quote = preflight(client).json()["quote"]
    response = confirm(client, quote + "tampered")
    assert response.status_code == 403
    assert provider.calls == 0


def test_expired_quote_rejected(ai_client, monkeypatch):
    client, provider, _, _ = ai_client
    quote = preflight(client).json()["quote"]
    import itsdangerous.timed
    original = itsdangerous.timed.time.time
    monkeypatch.setattr(itsdangerous.timed.time, "time", lambda: original() + 301)
    response = confirm(client, quote)
    assert response.status_code == 403
    assert provider.calls == 0


def test_other_session_quote_rejected(ai_client):
    client, provider, _, app = ai_client
    quote = preflight(client).json()["quote"]
    with TestClient(app, base_url="http://127.0.0.1:8000") as other:
        other.get("/dashboard")
        response = confirm(other, quote)
    assert response.status_code == 403
    assert provider.calls == 0


def test_mock_demo_rejects_ai_post(tmp_path):
    (tmp_path / "MOCK_DATA.json").write_text("{}", encoding="utf-8")
    with TestClient(create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler()),
                    base_url="http://127.0.0.1:8000") as client:
        client.get("/dashboard")
        response = client.post("/api/recommendations/preflight", headers=headers(client),
                               json={"analysis_date": "2026-09-25", "market": "vn"})
        assert response.status_code == 403
        response = client.post("/api/recommendations/runs", headers=headers(client),
                               json={"quote": "invalid", "confirm_unknown": True})
        assert response.status_code == 403
