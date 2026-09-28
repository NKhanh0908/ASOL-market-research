from pathlib import Path
import pytest
from casual_scout.storage import Repository
from casual_scout.stats.shortlist import ShortlistService
from casual_scout.stats.exporter import export_shortlist_to_csv, export_radar_to_csv, export_to_json

@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "data")
    r.initialize()
    return r

def test_shortlist_service_flow(repo: Repository):
    service = ShortlistService(repo)
    item = service.bookmark_game(
        app_id="999",
        title="Merge Mansion",
        primary_country="vn",
        rank_at_bookmark=1,
        subgenre="Puzzle",
        mechanic="Merge",
        opportunity_score=85.0,
        notes="Top merge reference",
        priority="HIGH"
    )
    assert item["app_id"] == "999"
    assert item["status"] == "CONSIDERING"
    
    # List shortlists
    all_items = service.list_shortlists()
    assert len(all_items) == 1
    
    # Update item
    updated = service.update_item("999", {"status": "PROTOTYPE", "notes": "Approved for prototyping"})
    assert updated is True
    
    updated_items = service.list_shortlists(status="PROTOTYPE")
    assert len(updated_items) == 1
    assert updated_items[0]["notes"] == "Approved for prototyping"
    
    # Export CSV
    csv_content = export_shortlist_to_csv(updated_items)
    assert csv_content.startswith('\ufeff')  # UTF-8 BOM
    assert "Merge Mansion" in csv_content
    assert "Approved for prototyping" in csv_content
    
    # Remove item
    assert service.remove_item("999") is True
    assert service.list_shortlists() == []

def test_export_radar_csv_and_json():
    radar_items = [{
        "app_id": "888",
        "title": "Super Game",
        "developer": "Top Dev",
        "subgenre": "Simulation",
        "mechanic": "Idle",
        "current_rank": 3,
        "delta_1d": 25,
        "delta_3d": 35,
        "signal": "FAST_RISER",
        "cross_market_count": 6,
        "noteworthy_label": "Đang tăng",
        "noteworthy_reasons": ["VN: +25 hạng / 1 ngày"],
        "presence_count": 1,
        "observed_market_count": 2,
        "presence_markets": ["vn"]
    }]
    csv_str = export_radar_to_csv(radar_items)
    assert csv_str.startswith('\ufeff')
    assert "Super Game" in csv_str
    assert "Đang tăng" in csv_str
    assert "VN: +25 hạng / 1 ngày" in csv_str
    assert "Opportunity Score" not in csv_str
    
    json_str = export_to_json(radar_items)
    assert "Super Game" in json_str
    assert "888" in json_str
