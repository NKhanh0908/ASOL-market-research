from pathlib import Path

from fastapi.testclient import TestClient

from casual_scout.config import Settings
from casual_scout.web.app import create_app


def client_for(tmp_path, launcher):
    client = TestClient(create_app(Settings(tmp_path), launcher=launcher))
    client.get("/data")
    return client


def headers(client):
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": client.cookies["csrftoken"],
        "Idempotency-Key": "test",
    }


def test_api_security_validation_and_once(tmp_path):
    calls = []
    client = client_for(tmp_path, lambda run, path: calls.append((run, path)))
    body = {"platform": "android", "markets": ["vn"], "chart_type": "grossing"}
    assert (
        client.post("/api/crawl", json=body, headers={"Origin": "http://testserver"}).status_code
        == 403
    )
    first = client.post("/api/crawl", json=body, headers=headers(client))
    assert first.status_code == 200
    assert (
        client.post("/api/crawl", json=body, headers=headers(client)).json()["run_id"]
        == first.json()["run_id"]
    )
    assert len(calls) == 1 and isinstance(calls[0][1], Path)
    assert (
        client.post(
            "/api/crawl", json={**body, "markets": ["us"]}, headers=headers(client)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/crawl", json={**body, "platform": "ios"}, headers=headers(client)
        ).status_code
        == 409
    )
    for query in ("platform=windows", "date=wrong", "feed_type=wrong", "country=xx"):
        assert client.get("/api/data?" + query).status_code == 422
    assert (
        len([r for r in client.app.routes if getattr(r, "path", None) == "/api/stats/radar"]) == 1
    )


def test_launch_failure_persisted(tmp_path):
    def fail(*args):
        raise OSError("spawn unavailable")

    client = client_for(tmp_path, fail)
    assert (
        client.post(
            "/api/crawl", json={"platform": "android", "markets": ["vn"]}, headers=headers(client)
        ).status_code
        == 503
    )
    with client.app.state.repo._connect() as db:
        assert db.execute("SELECT status FROM runs").fetchone()[0] == "failed"
