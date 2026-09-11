from casual_scout.stats.radar import (
    calculate_opportunity_score_v15,
    calculate_opportunity_score,
    rank_opportunities,
)


def test_radar_v15_grossing_power_boost():
    # High momentum + High Grossing Rank #5
    score_with_grossing, breakdown = calculate_opportunity_score_v15(
        current_rank=10,
        delta_1d=20,
        delta_3d=30,
        signal="FAST_RISER",
        cross_market_count=8,
        grossing_rank=5,
        monetization_efficiency="MEGA_HIT"
    )
    assert breakdown["grossing_power"] == 15
    assert score_with_grossing >= 85


def test_radar_v15_efficiency_bonus():
    # High grossing efficiency whale: free #60, grossing #15
    score, breakdown = calculate_opportunity_score_v15(
        current_rank=60,
        signal="STEADY",
        cross_market_count=5,
        grossing_rank=15,
        monetization_efficiency="HIGH_GROSSING_EFFICIENCY"
    )
    assert breakdown["grossing_power"] == 10
    assert breakdown["efficiency_bonus"] == 5


def test_radar_v15_backwards_compatible_calculate_opportunity_score():
    res = calculate_opportunity_score({
        "current_rank": 10,
        "delta_1d": 20,
        "delta_3d": 30,
        "signal": "FAST_RISER",
        "cross_market_count": 8,
        "grossing_rank": 5,
    })
    assert "grossing_power" in res
    assert res["score"] >= 80
