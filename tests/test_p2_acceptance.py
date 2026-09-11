import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_analysis_service import _create_snapshot_with_entries

from casual_scout.analysis.service import AnalysisService
from casual_scout.cli import main
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


def test_p2_end_to_end_acceptance(tmp_path: Path, capsys: pytest.CaptureFixture):
    data_dir = tmp_path / 'data'
    repo = Repository(data_dir)
    repo.initialize()

    # 1. Populate multi-day data
    # Day 1: 2026-09-09 (VN, TH)
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-p2-d1-vn',
        snap_id='snap-p2-d1-vn',
        country='vn',
        date_str='2026-09-09',
        observed_time_str='2026-09-09T08:00:00Z',
        entries=[
            ('2001', 35, 'Royal Match'),
            ('2002', 15, 'Block Blast'),
            ('2004', 5, 'Subway Surfers'),
        ],
    )
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-p2-d1-th',
        snap_id='snap-p2-d1-th',
        country='th',
        date_str='2026-09-09',
        observed_time_str='2026-09-09T08:00:00Z',
        entries=[
            ('2001', 20, 'Royal Match'),
        ],
    )

    # Day 2: 2026-09-10 (VN, TH, US)
    # VN:
    # 2001 (Royal Match): jumped from #35 to #10 (+25 -> FAST_RISER, Match-3)
    # 2002 (Block Blast): dropped from #15 to #50 (-35 -> FALLING)
    # 2003 (Water Sort): new entry at #8 (NEW_ENTRY, Sort)
    # 2004 (Subway Surfers): moved from #5 to #6 (-1 -> STEADY, Runner)
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-p2-d2-vn',
        snap_id='snap-p2-d2-vn',
        country='vn',
        date_str='2026-09-10',
        observed_time_str='2026-09-10T08:00:00Z',
        entries=[
            ('2004', 6, 'Subway Surfers'),
            ('2003', 8, 'Water Sort Puzzle'),
            ('2001', 10, 'Royal Match 3D'),
            ('2002', 50, 'Block Blast'),
        ],
        metadata_map={
            '2001': {'description': 'Swap and match 3 tiles in 3D castle puzzles!'},
            '2002': {'description': 'Simple relaxing block puzzle game.'},
            '2003': {'description': 'Sort colored water into test tubes until all colors match.'},
            '2004': {'description': 'Dash and dodge trains in this endless runner adventure.'},
        },
    )
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-p2-d2-th',
        snap_id='snap-p2-d2-th',
        country='th',
        date_str='2026-09-10',
        observed_time_str='2026-09-10T08:00:00Z',
        entries=[
            ('2001', 5, 'Royal Match 3D'),
            ('2003', 12, 'Water Sort Puzzle'),
        ],
        metadata_map={
            '2001': {'description': 'Swap and match 3 tiles in 3D castle puzzles!'},
            '2003': {'description': 'Sort colored water into test tubes until all colors match.'},
        },
    )

    # 2. Run Analysis Service
    service = AnalysisService(repo)
    result = service.analyze_date('2026-09-10', countries=['vn', 'th'])
    assert result['status'] == 'completed'
    assert 'vn' in result['markets']
    assert 'th' in result['markets']

    # 3. Verify Database Persistence & Analytics Rules
    vn_analytics = repo.get_daily_analytics('2026-09-10', 'vn')
    assert len(vn_analytics) == 4

    app_2001 = next(a for a in vn_analytics if a['app_id'] == '2001')
    assert app_2001['current_rank'] == 10
    assert app_2001['delta_1d'] == 25
    assert app_2001['signal'] == 'FAST_RISER'
    assert app_2001['mechanic'] == 'Match-3'
    assert app_2001['mechanic_confidence'] == 'high'
    assert app_2001['cross_market_count'] == 2
    assert set(app_2001['cross_markets']) == {'vn', 'th'}

    app_2003 = next(a for a in vn_analytics if a['app_id'] == '2003')
    assert app_2003['current_rank'] == 8
    assert app_2003['signal'] == 'NEW_ENTRY'
    assert app_2003['mechanic'] == 'Sort'
    assert app_2003['cross_market_count'] == 2

    app_2002 = next(a for a in vn_analytics if a['app_id'] == '2002')
    assert app_2002['current_rank'] == 50
    assert app_2002['delta_1d'] == -35
    assert app_2002['signal'] == 'FALLING'

    app_2004 = next(a for a in vn_analytics if a['app_id'] == '2004')
    assert app_2004['current_rank'] == 6
    assert app_2004['delta_1d'] == -1
    assert app_2004['signal'] == 'STEADY'
    assert app_2004['mechanic'] == 'Runner'

    # 4. Verify CLI Commands
    ret_analyze = main(['analyze', '--data-dir', str(data_dir), '--date', '2026-09-10', '--countries', 'vn,th'])
    assert ret_analyze == 0
    capsys.readouterr()

    ret_trends = main(['trends', '--data-dir', str(data_dir), '--date', '2026-09-10', '--country', 'vn', '--signal', 'fast_risers', '--json'])
    assert ret_trends == 0
    captured = capsys.readouterr()
    trends_data = json.loads(captured.out)
    assert len(trends_data) == 1
    assert trends_data[0]['app_id'] == '2001'

    # 5. Verify Web UI endpoints
    settings = Settings(data_dir)
    app = create_app(settings)
    client = TestClient(app)

    # Main data explorer with badges & filter tabs
    resp_data = client.get('/data?country=vn')
    assert resp_data.status_code == 200
    assert 'FAST_RISER' in resp_data.text
    assert 'NEW_ENTRY' in resp_data.text
    assert 'Match-3' in resp_data.text
    assert 'Sort' in resp_data.text
    assert 'Runner' in resp_data.text

    # Game Detail with Rank History & Evidence
    resp_game = client.get('/games/vn/2001')
    assert resp_game.status_code == 200
    assert 'Royal Match 3D' in resp_game.text
    assert 'Bằng chứng phân loại' in resp_game.text
    assert 'Lịch sử thứ hạng' in resp_game.text
    assert 'Match-3' in resp_game.text

    # CSV Download with rich analytical columns & UTF-8 BOM
    resp_csv = client.get('/export/csv?country=vn&date=2026-09-10')
    assert resp_csv.status_code == 200
    assert resp_csv.headers['content-type'].startswith('text/csv')
    assert 'subgenre,mechanic,confidence' in resp_csv.text
    assert 'FAST_RISER' in resp_csv.text
    assert '2001' in resp_csv.text