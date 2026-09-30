from casual_scout.market_brief.reader import SnapshotData
from casual_scout.market_brief.service import compute_platform_brief, compute_game_history

def test_top_10_always_included_regardless_of_movement():
    entries_t = [{"app_id": f"app_{i}", "rank": i, "name": f"Game {i}", "store_url": None} for i in range(1, 11)]
    snap_t = SnapshotData("s_t", "2026-09-30T00:00:00Z", "2026-09-30", "complete", "h_t", entries_t)
    snapshots = {"2026-09-30": snap_t}

    brief = compute_platform_brief("vn", "ios", "2026-09-30", snapshots)
    assert len(brief.top_10) == 10
    assert brief.total_top_10 == 10
    assert len(brief.strong_movers_outside_top_10) == 0

def test_strong_movers_threshold_boundary():
    # app_up20 moved from rank 40 (T-1) to rank 20 (T) -> delta +20 (qualifies)
    # app_up19 moved from rank 39 (T-1) to rank 20 (T) -> delta +19 (does not qualify)
    # app_3d30 moved from rank 60 (T-3) to rank 30 (T) -> delta +30 (qualifies)
    entries_t = [
        {"app_id": "app_up20", "rank": 20, "name": "Mover 20", "store_url": None},
        {"app_id": "app_up19", "rank": 21, "name": "Mover 19", "store_url": None},
        {"app_id": "app_3d30", "rank": 30, "name": "Mover 3d30", "store_url": None},
    ]
    entries_t1 = [
        {"app_id": "app_up20", "rank": 40, "name": "Mover 20", "store_url": None},
        {"app_id": "app_up19", "rank": 40, "name": "Mover 19", "store_url": None},
    ]
    entries_t3 = [
        {"app_id": "app_3d30", "rank": 60, "name": "Mover 3d30", "store_url": None},
    ]
    snapshots = {
        "2026-09-30": SnapshotData("s0", "2026-09-30T00:00:00Z", "2026-09-30", "complete", "h0", entries_t),
        "2026-09-29": SnapshotData("s1", "2026-09-29T00:00:00Z", "2026-09-29", "complete", "h1", entries_t1),
        "2026-09-27": SnapshotData("s3", "2026-09-27T00:00:00Z", "2026-09-27", "complete", "h3", entries_t3),
    }
    brief = compute_platform_brief("vn", "ios", "2026-09-30", snapshots)
    movers = {m.app_id for m in brief.strong_movers_outside_top_10}
    assert "app_up20" in movers
    assert "app_3d30" in movers
    assert "app_up19" not in movers

def test_opposite_direction_deltas_preserved():
    # app moved up 20 in 1d (40 -> 20) and down 30 in 3d (10 -> 40 -> 20: 3d is 10 -> 20: delta is -10)
    # let's test T=50, T-1=75 (delta_1d=+25), T-3=15 (delta_3d=-35) -> both 1d up and 3d down!
    entries_t = [{"app_id": "app_opp", "rank": 50, "name": "Opposite", "store_url": None}]
    entries_t1 = [{"app_id": "app_opp", "rank": 75, "name": "Opposite", "store_url": None}]
    entries_t3 = [{"app_id": "app_opp", "rank": 15, "name": "Opposite", "store_url": None}]
    snapshots = {
        "2026-09-30": SnapshotData("s0", "2026-09-30T00:00:00Z", "2026-09-30", "complete", "h0", entries_t),
        "2026-09-29": SnapshotData("s1", "2026-09-29T00:00:00Z", "2026-09-29", "complete", "h1", entries_t1),
        "2026-09-27": SnapshotData("s3", "2026-09-27T00:00:00Z", "2026-09-27", "complete", "h3", entries_t3),
    }
    brief = compute_platform_brief("vn", "ios", "2026-09-30", snapshots)
    assert len(brief.strong_movers_outside_top_10) == 1
    mover = brief.strong_movers_outside_top_10[0]
    assert mover.delta_1d == 25
    assert mover.delta_3d == -35
    assert len(mover.strong_moves) == 2
    directions = {m.direction for m in mover.strong_moves}
    assert directions == {"up", "down"}
