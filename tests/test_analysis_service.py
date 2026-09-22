import json
from pathlib import Path

import pytest

from casual_scout.analysis.service import AnalysisService
from casual_scout.storage import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / 'data')
    r.initialize()
    return r


def _create_snapshot_with_entries(
    repo: Repository,
    run_id: str,
    snap_id: str,
    country: str,
    date_str: str,
    observed_time_str: str,
    entries: list[tuple[str, int, str]],  # (app_id, rank, name)
    metadata_map: dict[str, dict] | None = None,
    collection: str = "topfreeapplications",
):
    chart_id = f'chart-{country}-{collection}'
    mr_id = f'mr-{snap_id}'
    hash_id = f'hash-{snap_id}'

    with repo._write_connection() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO runs (id, request_key, trigger, status, started_at) '
            'VALUES (?, ?, \'manual\', \'running\', ?)',
            (run_id, f'req-{run_id}', f'{date_str}T00:00:00Z'),
        )
        conn.execute(
            'INSERT OR IGNORE INTO charts (id, provider, platform, country, collection, genre, depth, version, endpoint, created_at) '
            'VALUES (?, \'apple\', \'ios\', ?, ?, \'7003\', 100, 1, \'url\', ?)',
            (chart_id, country, collection, f'{date_str}T00:00:00Z'),
        )
        conn.execute(
            'INSERT INTO market_runs (id, run_id, chart_id, chart_status, enrichment_status, started_at) '
            'VALUES (?, ?, ?, \'complete\', \'complete\', ?)',
            (mr_id, run_id, chart_id, f'{date_str}T00:00:00Z'),
        )
        conn.execute(
            'INSERT OR IGNORE INTO raw_responses (hash, path, endpoint, status, received_at, headers_json, size_bytes) '
            'VALUES (?, ?, \'url\', 200, ?, \'{}\', 100)',
            (hash_id, f'path-{snap_id}', observed_time_str),
        )
        conn.execute(
            'INSERT INTO snapshots (id, market_run_id, raw_hash, observed_at, quality, issues_json) '
            'VALUES (?, ?, ?, ?, \'complete\', \'[]\')',
            (snap_id, mr_id, hash_id, observed_time_str),
        )

        for app_id, rank, name in entries:
            conn.execute(
                'INSERT OR IGNORE INTO apps (id, provider, platform, source_app_id, created_at) '
                'VALUES (?, \'apple\', \'ios\', ?, ?)',
                (f'app:{app_id}', app_id, f'{date_str}T00:00:00Z'),
            )
            conn.execute(
                'INSERT INTO entries (snapshot_id, app_ref, app_id, rank, name, store_url, source_genres_json) '
                'VALUES (?, ?, ?, ?, ?, \'http://store\', \'[\"Games\", \"Casual\", \"Puzzle\"]\')',
                (snap_id, f'app:{app_id}', app_id, rank, name),
            )

            if metadata_map and app_id in metadata_map:
                meta = metadata_map[app_id]
                meta_id = f'mv-{snap_id}-{app_id}'
                conn.execute(
                    'INSERT INTO metadata_versions (id, app_ref, provider, platform, country, app_id, fetched_at, status, raw_hash, name, developer, primary_genre, genres_json, description, price, currency, values_json, in_app_purchases_json, has_in_app_purchases) '
                    'VALUES (?, ?, \'apple\', \'ios\', ?, ?, ?, \'complete\', ?, ?, ?, ?, ?, ?, 0, \'USD\', \'{}\', ?, ?)',
                    (
                        meta_id,
                        f'app:{app_id}',
                        country,
                        app_id,
                        observed_time_str,
                        hash_id,
                        name,
                        meta.get('developer', 'Dev Inc'),
                        'Games',
                        '[\"Games\", \"Casual\", \"Puzzle\"]',
                        meta.get('description', ''),
                        json.dumps(meta.get('in_app_purchases', [])),
                        int(bool(meta.get('in_app_purchases'))),
                    ),
                )
                conn.execute(
                    'INSERT INTO snapshot_metadata (snapshot_id, app_id, metadata_version_id) '
                    'VALUES (?, ?, ?)',
                    (snap_id, app_id, meta_id),
                )

        conn.execute('UPDATE runs SET status = \'succeeded\' WHERE id = ?', (run_id,))


def test_analysis_service_e2e(repo: Repository):
    # Day 1: 2026-09-09 (VN)
    # app-1 rank 30, app-2 rank 10
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-d1',
        snap_id='snap-d1-vn',
        country='vn',
        date_str='2026-09-09',
        observed_time_str='2026-09-09T08:00:00Z',
        entries=[
            ('1001', 30, 'Royal Match'),
            ('1002', 10, 'Block Blast'),
        ],
    )

    # Day 2: 2026-09-10 (VN & TH)
    # VN:
    # app-1: jumped to #5 (+25 -> FAST_RISER)
    # app-2: dropped to #40 (-30 -> FALLING)
    # app-3: new entry at #12 (NEW_ENTRY)
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-d2',
        snap_id='snap-d2-vn',
        country='vn',
        date_str='2026-09-10',
        observed_time_str='2026-09-10T08:00:00Z',
        entries=[
            ('1001', 5, 'Royal Match 3D'),
            ('1003', 12, 'Tile Sort Adventure'),
            ('1002', 40, 'Block Blast'),
        ],
        metadata_map={
            '1001': {'description': 'Swap and match 3 tiles in 3d puzzles!'},
            '1003': {'description': 'Sort colored water into tubes!'},
            '1002': {'description': 'Simple block puzzle.'},
        },
    )

    # TH:
    # app-1 rank #8
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-d2-th',
        snap_id='snap-d2-th',
        country='th',
        date_str='2026-09-10',
        observed_time_str='2026-09-10T08:00:00Z',
        entries=[
            ('1001', 8, 'Royal Match 3D'),
        ],
    )

    service = AnalysisService(repo)
    result = service.analyze_date('2026-09-10', countries=['vn', 'th'])

    assert result['status'] == 'completed'
    assert result['date'] == '2026-09-10'
    assert len(result['markets']) == 2

    # Check VN daily analytics
    vn_analytics = repo.get_daily_analytics('2026-09-10', 'vn')
    assert len(vn_analytics) == 3

    # app 1001: Rank 5, delta_1d +25, FAST_RISER, Match-3 mechanic, cross_market_count 2 (vn, th)
    app1 = next(a for a in vn_analytics if a['app_id'] == '1001')
    assert app1['current_rank'] == 5
    assert app1['rank_1d_ago'] == 30
    assert app1['delta_1d'] == 25
    assert app1['signal'] == 'FAST_RISER'
    assert app1['subgenre'] == 'Puzzle'
    assert app1['mechanic'] == 'Match-3'
    assert app1['cross_market_count'] == 2
    assert 'th' in app1['cross_markets'] and 'vn' in app1['cross_markets']

    # app 1003: Rank 12, NEW_ENTRY, Sort mechanic, cross_market_count 1
    app3 = next(a for a in vn_analytics if a['app_id'] == '1003')
    assert app3['current_rank'] == 12
    assert app3['signal'] == 'NEW_ENTRY'
    assert app3['mechanic'] == 'Sort'
    assert app3['cross_market_count'] == 1

    # app 1002: Rank 40, delta_1d -30, FALLING
    app2 = next(a for a in vn_analytics if a['app_id'] == '1002')
    assert app2['current_rank'] == 40
    assert app2['delta_1d'] == -30
    assert app2['signal'] == 'FALLING'
