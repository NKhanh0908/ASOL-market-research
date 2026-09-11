from typing import Any


def calculate_opportunity_score_v15(
    record: dict[str, Any] | None = None,
    *,
    current_rank: int | None = None,
    delta_1d: int | None = None,
    delta_3d: int | None = None,
    signal: str | None = None,
    cross_market_count: int | None = None,
    grossing_rank: int | None = None,
    monetization_efficiency: str | None = None,
    **kwargs: Any,
) -> tuple[float, dict[str, Any]]:
    rec = dict(record) if record else {}
    cur_rank = current_rank if current_rank is not None else rec.get("current_rank", 100)
    d_1d = delta_1d if delta_1d is not None else rec.get("delta_1d")
    d_3d = delta_3d if delta_3d is not None else rec.get("delta_3d")
    sig = signal if signal is not None else rec.get("signal", "NONE")
    cross_cnt = cross_market_count if cross_market_count is not None else rec.get("cross_market_count", 1)
    gr_rank = grossing_rank if grossing_rank is not None else rec.get("grossing_rank")
    eff = monetization_efficiency if monetization_efficiency is not None else (rec.get("monetization_efficiency_flag") or rec.get("monetization_efficiency"))

    # 1. Momentum Score (Max 40)
    momentum = 0.0
    if sig == "FAST_RISER":
        if d_1d is not None and d_1d >= 20:
            momentum = 20.0 + min(20.0, d_1d * 0.5)
        elif d_3d is not None and d_3d >= 30:
            momentum = 15.0 + min(25.0, d_3d * 0.4)
        else:
            momentum = 20.0
    elif sig == "NEW_ENTRY":
        momentum = 25.0 if cur_rank <= 50 else 15.0
    elif sig == "STEADY":
        momentum = 5.0 if cur_rank <= 20 else 0.0
    elif sig == "FALLING":
        momentum = 0.0
    else:
        momentum = 0.0

    # 2. Cross-Market Breadth (Max 35)
    breadth = min(35.0, round(cross_cnt * 3.5, 1))

    # 3. Current Rank Tier (Max 25)
    if cur_rank <= 10:
        rank_score = 25.0
    elif cur_rank <= 30:
        rank_score = 20.0
    elif cur_rank <= 50:
        rank_score = 15.0
    else:
        rank_score = max(0.0, round((100 - cur_rank) * 0.2, 1))

    # 4. Grossing Power (Max 15)
    grossing_power = 0.0
    if gr_rank is not None and gr_rank > 0:
        if gr_rank <= 10:
            grossing_power = 15.0
        elif gr_rank <= 30:
            grossing_power = 10.0
        elif gr_rank <= 70:
            grossing_power = 6.0
        elif gr_rank <= 100:
            grossing_power = 3.0

    # 5. Efficiency Bonus (Max 5)
    efficiency_bonus = 5.0 if eff == "HIGH_GROSSING_EFFICIENCY" else 0.0

    total_score = round(min(100.0, momentum + breadth + rank_score + grossing_power + efficiency_bonus), 1)

    if total_score >= 75.0:
        badge = "HOT WAVE"
    elif total_score >= 50.0:
        badge = "PROMISING"
    elif total_score >= 30.0:
        badge = "EMERGING"
    else:
        badge = "WATCHLIST"

    breakdown = {
        "score": total_score,
        "badge": badge,
        "momentum_score": round(momentum, 1),
        "breadth_score": round(breadth, 1),
        "rank_score": round(rank_score, 1),
        "grossing_power": round(grossing_power, 1),
        "efficiency_bonus": round(efficiency_bonus, 1),
    }
    return total_score, breakdown


def calculate_opportunity_score(record: dict[str, Any]) -> dict[str, Any]:
    score, breakdown = calculate_opportunity_score_v15(record)
    return breakdown


def rank_opportunities(
    records: list[dict[str, Any]], shortlisted_app_ids: set[str] | None = None
) -> list[dict[str, Any]]:
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
        entry["grossing_power"] = scored_info["grossing_power"]
        entry["efficiency_bonus"] = scored_info["efficiency_bonus"]
        entry["is_shortlisted"] = app_id in shortlisted

        if (
            app_id not in best_by_app
            or entry["opportunity_score"] > best_by_app[app_id]["opportunity_score"]
        ):
            best_by_app[app_id] = entry

    results = list(best_by_app.values())
    results.sort(
        key=lambda x: (
            x["opportunity_score"],
            x.get("cross_market_count", 0),
            -x.get("current_rank", 100),
        ),
        reverse=True,
    )
    return results

