import csv
import io
import json
from typing import Any

def export_shortlist_to_csv(items: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    
    writer.writerow([
        "App ID", "Title", "Developer", "Subgenre", "Mechanic",
        "Primary Country", "Rank At Bookmark",
        "Status", "Priority", "Notes", "Tags", "Updated At"
    ])
    
    for it in items:
        writer.writerow([
            it.get("app_id"),
            it.get("title"),
            it.get("developer") or "",
            it.get("subgenre") or "",
            it.get("mechanic") or "",
            it.get("primary_country"),
            it.get("rank_at_bookmark"),
            it.get("status"),
            it.get("priority"),
            it.get("notes") or "",
            ", ".join(it.get("tags") or []),
            it.get("updated_at")
        ])
    return output.getvalue()

def export_radar_to_csv(radar_items: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    
    writer.writerow([
        "App ID", "Title", "Developer", "Subgenre", "Mechanic",
        "Current Rank", "Delta 1D", "Delta 3D", "Signal",
        "Presence Count", "Observed Market Count", "Present Markets", "Reasons",
        "Comparable Markets", "Added Markets", "Lost Markets"
    ])
    
    for r in radar_items:
        writer.writerow([
            r.get("app_id"),
            r.get("title") or r.get("app_id"),
            r.get("developer") or "",
            r.get("subgenre") or "",
            r.get("mechanic") or "",
            r.get("current_rank"),
            r.get("delta_1d") if r.get("delta_1d") is not None else "",
            r.get("delta_3d") if r.get("delta_3d") is not None else "",
            r.get("noteworthy_label") or "",
            r.get("presence_count") if r.get("presence_count") is not None else "",
            r.get("observed_market_count", 0),
            ", ".join(r.get("presence_markets") or []),
            "; ".join(r.get("noteworthy_reasons") or []),
            ", ".join(r.get("comparable_markets") or []),
            ", ".join(r.get("added_markets") or []),
            ", ".join(r.get("lost_markets") or [])
        ])
    return output.getvalue()

def export_to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
