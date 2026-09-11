from datetime import UTC, datetime
import uuid
from typing import Any
from casual_scout.storage import Repository

class ShortlistService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def bookmark_game(
        self,
        app_id: str,
        title: str,
        primary_country: str,
        rank_at_bookmark: int,
        icon_url: str | None = None,
        developer: str | None = None,
        subgenre: str | None = None,
        mechanic: str | None = None,
        opportunity_score: float | None = None,
        notes: str | None = None,
        priority: str = "MEDIUM",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        now_str = datetime.now(UTC).isoformat()
        existing = self.repo.get_shortlist_item_by_app_id(str(app_id))
        
        item = {
            "id": existing["id"] if existing else str(uuid.uuid4()),
            "app_id": str(app_id),
            "title": title,
            "icon_url": icon_url,
            "developer": developer,
            "subgenre": subgenre,
            "mechanic": mechanic,
            "primary_country": primary_country.lower(),
            "rank_at_bookmark": int(rank_at_bookmark),
            "opportunity_score": opportunity_score,
            "status": existing["status"] if existing else "CONSIDERING",
            "priority": priority or (existing["priority"] if existing else "MEDIUM"),
            "notes": notes if notes is not None else (existing.get("notes") if existing else ""),
            "tags": tags if tags is not None else (existing.get("tags") if existing else []),
            "created_at": existing["created_at"] if existing else now_str,
            "updated_at": now_str,
        }
        self.repo.save_shortlist_item(item)
        return item

    def list_shortlists(self, status: str | None = None, priority: str | None = None) -> list[dict[str, Any]]:
        return self.repo.get_shortlist_items(status=status, priority=priority)

    def get_by_app_id(self, app_id: str) -> dict[str, Any] | None:
        return self.repo.get_shortlist_item_by_app_id(str(app_id))

    def update_item(self, app_id: str, updates: dict[str, Any]) -> bool:
        updates["updated_at"] = datetime.now(UTC).isoformat()
        return self.repo.update_shortlist_item(str(app_id), updates)

    def remove_item(self, app_id: str) -> bool:
        return self.repo.delete_shortlist_item(str(app_id))
