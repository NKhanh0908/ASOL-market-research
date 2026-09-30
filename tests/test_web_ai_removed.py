import pytest
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.web.app import create_app

def test_ai_routes_return_404(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    res = client.get("/recommendations")
    assert res.status_code == 404

    res_detail = client.get("/recommendations/some-run-id")
    assert res_detail.status_code == 404

    res2 = client.post("/recommendations/evaluate", headers={"Origin": "http://127.0.0.1"})
    assert res2.status_code == 404

def test_dashboard_does_not_contain_ai_button(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Tạo gợi ý AI" not in res.text
    assert "/recommendations" not in res.text
