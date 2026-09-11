from casual_scout.analysis.delta import (
    compute_cross_market_presence,
    compute_rank_deltas,
)


def test_compute_rank_deltas():
    current_entries = {
        'app-1': 5,
        'app-2': 20,
        'app-3': 50,
    }
    past_snapshots = {
        1: {'app-1': 30, 'app-2': 18},  # 1 day ago
        3: {'app-1': 60, 'app-3': 40},  # 3 days ago
        7: {},                          # 7 days ago
    }

    deltas = compute_rank_deltas(current_entries, past_snapshots)

    # app-1: was 30 (1d), was 60 (3d) -> delta_1d = +25, delta_3d = +55, delta_7d = None
    assert deltas['app-1']['rank_1d_ago'] == 30
    assert deltas['app-1']['delta_1d'] == 25
    assert deltas['app-1']['rank_3d_ago'] == 60
    assert deltas['app-1']['delta_3d'] == 55
    assert deltas['app-1']['delta_7d'] is None
    assert deltas['app-1']['is_new_entry'] is False

    # app-2: was 18 (1d), not in 3d -> delta_1d = -2, delta_3d = None
    assert deltas['app-2']['delta_1d'] == -2
    assert deltas['app-2']['delta_3d'] is None
    assert deltas['app-2']['is_new_entry'] is False

    # app-3: not in 1d (so new entry relative to 1d if 1d exists), was 40 in 3d -> delta_3d = -10
    assert deltas['app-3']['rank_1d_ago'] is None
    assert deltas['app-3']['delta_1d'] is None
    assert deltas['app-3']['delta_3d'] == -10
    assert deltas['app-3']['is_new_entry'] is True


def test_compute_cross_market_presence():
    country_app_maps = {
        'vn': ['app-1', 'app-2', 'app-3'],
        'th': ['app-1', 'app-2', 'app-4'],
        'sg': ['app-1', 'app-5'],
        'us': ['app-2', 'app-6'],
    }

    cross_presence = compute_cross_market_presence(country_app_maps)

    assert set(cross_presence['app-1']) == {'vn', 'th', 'sg'}
    assert set(cross_presence['app-2']) == {'vn', 'th', 'us'}
    assert set(cross_presence['app-3']) == {'vn'}
    assert set(cross_presence['app-4']) == {'th'}