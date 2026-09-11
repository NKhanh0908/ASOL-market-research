from pathlib import Path
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.storage.repository import Repository
from casual_scout.web.app import create_app


def test_data_view_feed_type_toggle(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    settings = Settings(tmp_path / "data")
    app = create_app(settings)
    client = TestClient(app)

    res_free = client.get("/data?country=vn&feed_type=top-free")
    assert res_free.status_code == 200
    assert "Top Free" in res_free.text

    res_grossing = client.get("/data?country=vn&feed_type=top-grossing")
    assert res_grossing.status_code == 200
    assert "Top Grossing" in res_grossing.text


def test_api_stats_monetization_endpoint(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    settings = Settings(tmp_path / "data")
    app = create_app(settings)
    client = TestClient(app)

    res = client.get("/api/stats/monetization?date=2026-09-11")
    assert res.status_code == 200
    data = res.json()
    assert "models_breakdown" in data
