from pathlib import Path
import pytest
from casual_scout.storage import Repository

@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "data")
    r.initialize()
    return r

def test_shortlist_crud(repo: Repository):
    assert repo.get_shortlist_items() == []
    
    item = {
        "id": "sl-1",
        "app_id": "123456",
        "title": "Block Blast!",
        "icon_url": "https://example.com/icon.png",
        "developer": "Hungry Studio",
        "subgenre": "Puzzle",
        "mechanic": "Block Puzzle",
        "primary_country": "vn",
        "rank_at_bookmark": 3,
        "opportunity_score": 88.5,
        "status": "CONSIDERING",
        "priority": "HIGH",
        "notes": "Very strong retention mechanic",
        "tags": ["trending_vn", "block_puzzle"],
        "created_at": "2026-09-11T00:00:00Z",
        "updated_at": "2026-09-11T00:00:00Z",
    }
    repo.save_shortlist_item(item)
    
    items = repo.get_shortlist_items()
    assert len(items) == 1
    assert items[0]["app_id"] == "123456"
    assert items[0]["status"] == "CONSIDERING"
    assert items[0]["tags"] == ["trending_vn", "block_puzzle"]
    
    # Update item
    updated = repo.update_shortlist_item("123456", {
        "status": "PROTOTYPE",
        "notes": "Started prototyping core loop",
        "updated_at": "2026-09-11T01:00:00Z"
    })
    assert updated is True
    
    single = repo.get_shortlist_item_by_app_id("123456")
    assert single is not None
    assert single["status"] == "PROTOTYPE"
    assert single["notes"] == "Started prototyping core loop"
    
    # Delete item
    deleted = repo.delete_shortlist_item("123456")
    assert deleted is True
    assert repo.get_shortlist_items() == []

def test_get_available_analytics_dates(repo: Repository):
    dates = repo.get_available_analytics_dates()
    assert isinstance(dates, list)
