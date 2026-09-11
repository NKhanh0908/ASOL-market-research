from casual_scout.stats.aggregator import (
    compute_genre_distribution,
    compute_mechanic_distribution,
    build_market_heatmap,
    compute_7day_subgenre_trends,
)

def test_genre_and_mechanic_distribution():
    records = [
        {"subgenre": "Puzzle", "mechanic": "Match-3"},
        {"subgenre": "Puzzle", "mechanic": "Block Puzzle"},
        {"subgenre": "Simulation", "mechanic": "Idle"},
        {"subgenre": "Action", "mechanic": "Runner"},
    ]
    g_dist = compute_genre_distribution(records)
    assert g_dist["total"] == 4
    assert g_dist["breakdown"]["Puzzle"]["count"] == 2
    assert g_dist["breakdown"]["Puzzle"]["percentage"] == 50.0
    assert g_dist["breakdown"]["Simulation"]["count"] == 1
    
    m_dist = compute_mechanic_distribution(records)
    assert m_dist["total"] == 4
    assert m_dist["breakdown"]["Match-3"]["count"] == 1
    assert m_dist["breakdown"]["Match-3"]["percentage"] == 25.0

def test_empty_distribution():
    g_dist = compute_genre_distribution([])
    assert g_dist["total"] == 0
    assert g_dist["breakdown"] == {}
    
    m_dist = compute_mechanic_distribution([])
    assert m_dist["total"] == 0
    assert m_dist["breakdown"] == {}

def test_build_market_heatmap():
    data = {
        "vn": [
            {"subgenre": "Puzzle"}, {"subgenre": "Puzzle"}, {"subgenre": "Simulation"}
        ],
        "us": [
            {"subgenre": "Word"}, {"subgenre": "Word"}, {"subgenre": "Puzzle"}
        ]
    }
    heatmap = build_market_heatmap(data)
    assert "vn" in heatmap["countries"]
    assert "us" in heatmap["countries"]
    assert "Puzzle" in heatmap["genres"]
    vn_idx = heatmap["countries"].index("vn")
    puzzle_idx = heatmap["genres"].index("Puzzle")
    assert heatmap["matrix"][vn_idx][puzzle_idx] == 2

def test_compute_7day_subgenre_trends():
    records = [
        {"date": "2026-09-05", "subgenre": "Puzzle"},
        {"date": "2026-09-05", "subgenre": "Simulation"},
        {"date": "2026-09-06", "subgenre": "Puzzle"},
        {"date": "2026-09-06", "subgenre": "Puzzle"},
    ]
    trends = compute_7day_subgenre_trends(records)
    assert "dates" in trends
    assert "2026-09-05" in trends["dates"]
    assert "2026-09-06" in trends["dates"]
    assert "series" in trends
    assert trends["series"]["Puzzle"] == [1, 2]
