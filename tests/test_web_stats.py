from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from casual_scout.storage import Repository
from casual_scout.config import Settings
from casual_scout.web.app import create_app

@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    repo = Repository(data_dir)
    repo.initialize()
    
    records = [
        {
            "id": "an-1",
            "date": "2026-09-11",
            "country": "vn",
            "app_id": "1001",
            "current_rank": 2,
            "rank_1d_ago": 25,
            "delta_1d": 23,
            "signal": "FAST_RISER",
            "signal_reasons": ["delta_1d >= 20"],
            "subgenre": "Puzzle",
            "mechanic": "Match-3",
            "mechanic_evidence": "match 3 gems",
            "mechanic_confidence": "high",
            "cross_market_count": 8,
            "cross_markets": ["vn", "th", "sg", "ph", "id", "my", "us", "tw"],
            "created_at": "2026-09-11T00:00:00Z",
        },
        {
            "id": "an-2",
            "date": "2026-09-11",
            "country": "vn",
            "app_id": "1002",
            "current_rank": 8,
            "signal": "NEW_ENTRY",
            "signal_reasons": ["first_time_in_top100"],
            "subgenre": "Simulation",
            "mechanic": "Idle",
            "mechanic_confidence": "medium",
            "cross_market_count": 1,
            "cross_markets": ["vn"],
            "created_at": "2026-09-11T00:00:00Z",
        }
    ]
    repo.save_daily_analytics(records)
    
    settings = Settings(data_dir=data_dir)
    app = create_app(settings)
    return TestClient(app, base_url="http://127.0.0.1:8000")

def test_web_dashboard_page(client: TestClient):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Market Research Dashboard" in resp.text
    assert "Opportunity Radar" in resp.text

def test_web_shortlist_page(client: TestClient):
    resp = client.get("/shortlist")
    assert resp.status_code == 200
    assert "Opportunity Shortlist" in resp.text

def test_api_stats_endpoints(client: TestClient):
    # Summary API
    s_resp = client.get("/api/stats/summary?date=2026-09-11&country=all")
    assert s_resp.status_code == 200
    s_data = s_resp.json()
    assert s_data["total_games"] == 2
    assert "Puzzle" in s_data["genre_distribution"]["breakdown"]

    # Heatmap API
    h_resp = client.get("/api/stats/heatmap?date=2026-09-11")
    assert h_resp.status_code == 200
    h_data = h_resp.json()
    assert "countries" in h_data
    assert "genres" in h_data

    # Radar API
    r_resp = client.get("/api/stats/radar?date=2026-09-11")
    assert r_resp.status_code == 200
    r_data = r_resp.json()
    assert len(r_data) == 2
    assert r_data[0]["opportunity_score"] >= 75.0

def test_api_shortlist_crud(client: TestClient):
    headers = {"Origin": "http://127.0.0.1:8000"}
    
    # Add to shortlist
    add_resp = client.post("/api/shortlist", headers=headers, json={
        "app_id": "1001",
        "title": "Royal Match",
        "primary_country": "vn",
        "rank_at_bookmark": 1,
        "subgenre": "Puzzle",
        "mechanic": "Match-3",
        "priority": "HIGH",
        "notes": "Excellent meta layer"
    })
    assert add_resp.status_code == 200
    assert add_resp.json()["app_id"] == "1001"
    
    # Get shortlist
    list_resp = client.get("/api/shortlist")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    
    # Patch shortlist
    patch_resp = client.patch("/api/shortlist/1001", headers=headers, json={"status": "PROTOTYPE", "notes": "Approved for dev"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "PROTOTYPE"
    
    # Export shortlist
    csv_resp = client.get("/api/export/shortlist?format=csv")
    assert csv_resp.status_code == 200
    assert "Royal Match" in csv_resp.text
    
    # Delete shortlist
    del_resp = client.delete("/api/shortlist/1001", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True


def test_create_app_auto_initializes_db_for_dashboard_and_shortlist(tmp_path: Path):
    # Uninitialized data directory without prior repo.initialize()
    raw_data_dir = tmp_path / "fresh_data"
    settings = Settings(raw_data_dir)
    app = create_app(settings)
    test_client = TestClient(app, base_url="http://127.0.0.1:8000")

    dash_resp = test_client.get("/dashboard")
    assert dash_resp.status_code == 200

    shortlist_resp = test_client.get("/shortlist")
    assert shortlist_resp.status_code == 200

