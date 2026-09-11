from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_analysis_service import _create_snapshot_with_entries

from casual_scout.analysis.service import AnalysisService
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


@pytest.fixture
def test_app(tmp_path: Path):
    data_dir = tmp_path / 'data'
    repo = Repository(data_dir)
    repo.initialize()

    # Create Day 1 & Day 2 snapshots
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

    # Run analysis
    service = AnalysisService(repo)
    service.analyze_date('2026-09-10', countries=['vn'])

    settings = Settings(data_dir)
    app = create_app(settings)
    return TestClient(app), repo


def test_data_view_shows_trend_badges_and_filters(test_app):
    client, _repo = test_app

    # Normal view
    res = client.get('/data?country=vn')
    assert res.status_code == 200
    assert 'Royal Match 3D' in res.text
    assert 'FAST_RISER' in res.text
    assert 'Match-3' in res.text
    assert '+25' in res.text

    # Filter fast_risers
    res_fast = client.get('/data?country=vn&signal=fast_risers')
    assert res_fast.status_code == 200
    assert 'Royal Match 3D' in res_fast.text
    assert 'Block Blast' not in res_fast.text

    # Filter new_entries
    res_new = client.get('/data?country=vn&signal=new_entries')
    assert res_new.status_code == 200
    assert 'Tile Sort Adventure' in res_new.text
    assert 'Royal Match 3D' not in res_new.text


def test_game_detail_view_shows_rank_history_and_evidence(test_app):
    client, _repo = test_app
    res = client.get('/games/vn/1001')
    assert res.status_code == 200
    assert 'Royal Match 3D' in res.text
    assert 'Match-3' in res.text
    assert 'Rank History' in res.text or 'Lịch sử thứ hạng' in res.text
    assert 'Classification Evidence' in res.text or 'Bằng chứng phân loại' in res.text


def test_csv_export(test_app):
    client, _repo = test_app
    res = client.get('/export/csv?country=vn&date=2026-09-10')
    assert res.status_code == 200
    assert res.headers['content-type'].startswith('text/csv')
    assert '1001' in res.text
    assert 'FAST_RISER' in res.text
    assert 'Match-3' in res.text


def test_country_select_and_unanalyzed_fallback(tmp_path: Path):
    data_dir = tmp_path / 'data_unanalyzed'
    repo = Repository(data_dir)
    repo.initialize()

    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-unanalyzed',
        snap_id='snap-us',
        country='us',
        date_str='2026-09-11',
        observed_time_str='2026-09-11T08:00:00Z',
        entries=[
            ('2001', 1, 'Match Three Mania'),
        ],
        metadata_map={
            '2001': {'description': 'A fun match 3 game puzzle!'},
        },
    )

    settings = Settings(data_dir)
    app = create_app(settings)
    client = TestClient(app)

    # US page request
    res = client.get('/data?country=us')
    assert res.status_code == 200
    # Must have US selected in dropdown, not Brunei
    assert 'value="us" selected' in res.text
    # Must classify on the fly
    assert 'Match-3' in res.text
    assert 'None thị trường' not in res.text
    assert '1 thị trường' in res.text
    assert 'None' not in res.text