from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from casual_scout.storage import Repository
from casual_scout.config import Settings
from casual_scout.web.app import create_app

def test_p3_end_to_end_flow(tmp_path: Path):
    data_dir = tmp_path / "data"
    repo = Repository(data_dir)
    repo.initialize()
    
    # 1. Insert seed analytics data for multi-market
    records = [
        {
            "id": f"an-{i}",
            "date": "2026-09-11",
            "country": "vn",
            "app_id": f"app-{i}",
            "current_rank": i,
            "rank_1d_ago": i + 25 if i <= 10 else None,
            "delta_1d": 25 if i <= 10 else None,
            "rank_3d_ago": None,
            "delta_3d": None,
            "rank_7d_ago": None,
            "delta_7d": None,
            "signal": "FAST_RISER" if i <= 10 else "STEADY",
            "signal_reasons": ["delta_1d >= 20"],
            "subgenre": "Puzzle" if i % 2 == 0 else "Simulation",
            "mechanic": "Match-3" if i % 2 == 0 else "Idle",
            "mechanic_evidence": "match gems",
            "mechanic_confidence": "high",
            "cross_market_count": 8 if i <= 5 else 1,
            "cross_markets": ["vn", "th", "sg", "ph", "id", "my", "us", "tw"],
            "created_at": "2026-09-11T00:00:00Z"
        }
        for i in range(1, 21)
    ]
    repo.save_daily_analytics(records)
    
    # 2. Test Web App and Dashboard APIs
    settings = Settings(data_dir=data_dir)
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    
    # Check Summary
    summary_resp = client.get("/api/stats/summary?date=2026-09-11&country=all")
    assert summary_resp.status_code == 200
    data = summary_resp.json()
    assert data["total_games"] == 20
    assert "Puzzle" in data["genre_distribution"]["breakdown"]
    
    # Check Radar Ranking
    radar_resp = client.get("/api/stats/radar?date=2026-09-11")
    assert radar_resp.status_code == 200
    radar_data = radar_resp.json()
    assert len(radar_data) == 20
    assert radar_data[0]["opportunity_score"] >= 75.0
    assert radar_data[0]["opportunity_badge"] == "HOT WAVE"
    
    # 3. Bookmark top game to Shortlist via API
    top_game = radar_data[0]
    headers = {"Origin": "http://127.0.0.1:8000"}
    bm_resp = client.post("/api/shortlist", headers=headers, json={
        "app_id": top_game["app_id"],
        "title": "Top Trending Game",
        "primary_country": "vn",
        "rank_at_bookmark": top_game["current_rank"],
        "opportunity_score": top_game["opportunity_score"],
        "notes": "Verified top opportunity candidate"
    })
    assert bm_resp.status_code == 200
    
    # 4. Export Shortlist CSV
    csv_resp = client.get("/api/export/shortlist?format=csv")
    assert csv_resp.status_code == 200
    assert "Top Trending Game" in csv_resp.text
    assert "Verified top opportunity candidate" in csv_resp.text
