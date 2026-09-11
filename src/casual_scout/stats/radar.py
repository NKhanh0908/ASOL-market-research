from typing import Any

def calculate_opportunity_score(record: dict[str, Any]) -> dict[str, Any]:
    signal = record.get("signal", "NONE")
    delta_1d = record.get("delta_1d")
    delta_3d = record.get("delta_3d")
    current_rank = record.get("current_rank", 100)
    
    # 1. Momentum Score (Max 40)
    momentum = 0.0
    if signal == "FAST_RISER":
        if delta_1d is not None and delta_1d >= 20:
            momentum = 20.0 + min(20.0, delta_1d * 0.5)
        elif delta_3d is not None and delta_3d >= 30:
            momentum = 15.0 + min(25.0, delta_3d * 0.4)
        else:
            momentum = 20.0
    elif signal == "NEW_ENTRY":
        momentum = 25.0 if current_rank <= 50 else 15.0
    elif signal == "STEADY":
        momentum = 5.0 if current_rank <= 20 else 0.0
    elif signal == "FALLING":
        momentum = 0.0
    else:
        momentum = 0.0

    # 2. Cross-Market Breadth (Max 35)
    cross_count = record.get("cross_market_count", 1)
    breadth = min(35.0, round(cross_count * 3.5, 1))

    # 3. Current Rank Tier (Max 25)
    if current_rank <= 10:
        rank_score = 25.0
    elif current_rank <= 30:
        rank_score = 20.0
    elif current_rank <= 50:
        rank_score = 15.0
    else:
        rank_score = max(0.0, round((100 - current_rank) * 0.2, 1))

    total_score = round(min(100.0, momentum + breadth + rank_score), 1)

    if total_score >= 75.0:
        badge = "HOT WAVE"
    elif total_score >= 50.0:
        badge = "PROMISING"
    elif total_score >= 30.0:
        badge = "EMERGING"
    else:
        badge = "WATCHLIST"

    return {
        "score": total_score,
        "badge": badge,
        "momentum_score": round(momentum, 1),
        "breadth_score": round(breadth, 1),
        "rank_score": round(rank_score, 1)
    }

def rank_opportunities(records: list[dict[str, Any]], shortlisted_app_ids: set[str] | None = None) -> list[dict[str, Any]]:
    shortlisted = shortlisted_app_ids or set()
    best_by_app: dict[str, dict[str, Any]] = {}

    for r in records:
        app_id = str(r["app_id"])
        scored_info = calculate_opportunity_score(r)
        
        entry = dict(r)
        entry["opportunity_score"] = scored_info["score"]
        entry["opportunity_badge"] = scored_info["badge"]
        entry["momentum_score"] = scored_info["momentum_score"]
        entry["breadth_score"] = scored_info["breadth_score"]
        entry["rank_score"] = scored_info["rank_score"]
        entry["is_shortlisted"] = app_id in shortlisted
        
        if app_id not in best_by_app or entry["opportunity_score"] > best_by_app[app_id]["opportunity_score"]:
            best_by_app[app_id] = entry

    results = list(best_by_app.values())
    results.sort(
        key=lambda x: (
            x["opportunity_score"],
            x.get("cross_market_count", 0),
            -x.get("current_rank", 100)
        ),
        reverse=True
    )
    return results
