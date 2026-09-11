from casual_scout.stats.radar import calculate_opportunity_score, rank_opportunities

def test_calculate_opportunity_score_hot_wave():
    record = {
        "app_id": "1001",
        "current_rank": 5,
        "delta_1d": 35,
        "delta_3d": 45,
        "signal": "FAST_RISER",
        "cross_market_count": 10,
    }
    scored = calculate_opportunity_score(record)
    assert scored["score"] >= 75.0
    assert scored["badge"] == "HOT WAVE"
    assert scored["momentum_score"] == 37.5
    assert scored["breadth_score"] == 35.0
    assert scored["rank_score"] == 25.0

def test_calculate_opportunity_score_falling():
    record = {
        "app_id": "1002",
        "current_rank": 80,
        "delta_1d": -15,
        "signal": "FALLING",
        "cross_market_count": 1,
    }
    scored = calculate_opportunity_score(record)
    assert scored["momentum_score"] == 0.0
    assert scored["breadth_score"] == 3.5
    assert scored["badge"] == "WATCHLIST"

def test_calculate_opportunity_score_new_entry():
    record_top = {
        "app_id": "1003",
        "current_rank": 20,
        "signal": "NEW_ENTRY",
        "cross_market_count": 3,
    }
    scored_top = calculate_opportunity_score(record_top)
    assert scored_top["momentum_score"] == 25.0
    assert scored_top["rank_score"] == 20.0
    assert scored_top["badge"] == "PROMISING"

    record_low = {
        "app_id": "1004",
        "current_rank": 70,
        "signal": "NEW_ENTRY",
        "cross_market_count": 1,
    }
    scored_low = calculate_opportunity_score(record_low)
    assert scored_low["momentum_score"] == 15.0

def test_rank_opportunities_and_deduplication():
    records = [
        {"app_id": "1001", "current_rank": 5, "delta_1d": 30, "signal": "FAST_RISER", "cross_market_count": 8, "country": "vn"},
        {"app_id": "1001", "current_rank": 12, "delta_1d": 25, "signal": "FAST_RISER", "cross_market_count": 8, "country": "th"},
        {"app_id": "1002", "current_rank": 2, "delta_1d": 0, "signal": "STEADY", "cross_market_count": 1, "country": "vn"},
    ]
    ranked = rank_opportunities(records, shortlisted_app_ids={"1001"})
    assert len(ranked) == 2
    assert ranked[0]["app_id"] == "1001"
    assert ranked[0]["is_shortlisted"] is True
    assert ranked[1]["app_id"] == "1002"
    assert ranked[1]["is_shortlisted"] is False
