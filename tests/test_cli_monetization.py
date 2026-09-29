from pathlib import Path
from unittest.mock import patch

import pytest
from test_analysis_service import _create_snapshot_with_entries

from casual_scout.analysis.service import AnalysisService
from casual_scout.cli import main
from casual_scout.storage.repository import Repository


def test_cli_collect_chart_type_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['collect', '--help'])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert '--chart-type' in captured.out or '--feed-type' in captured.out


def test_cli_trends_grossing_returns_the_grossing_snapshot(tmp_path: Path, capsys):
    data_dir = tmp_path / 'data'
    repo = Repository(data_dir)
    repo.initialize()
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-grossing-trends',
        snap_id='snap-vn-grossing',
        country='vn',
        date_str='2026-09-11',
        observed_time_str='2026-09-11T08:00:00Z',
        entries=[('1001', 3, 'Grossing Hero')],
        collection='topgrossingapplications',
    )

    rc = main([
        'trends', '--data-dir', str(data_dir), '--date', '2026-09-11',
        '--country', 'vn', '--chart-type', 'grossing', '--json',
    ])

    assert rc == 0
    assert capsys.readouterr().out == (
        '[\n  {\n    "app_id": "1001",\n    "current_rank": 3,\n'
        '    "name": "Grossing Hero",\n    "chart_type": "top-grossing"\n  }\n]\n'
    )


def test_cli_collect_passes_chart_type(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / 'data'
    repo = Repository(data_dir)
    repo.initialize()

    with patch('casual_scout.collection.jobs.JobService.submit') as mock_submit, \
         patch('casual_scout.collection.platforms.execute_run') as mock_execute:
        mock_submit.return_value = 'fake-run-id'
        mock_execute.return_value = 'succeeded'

        rc = main([
            'collect',
            '--data-dir', str(data_dir),
            '--countries', 'vn',
            '--chart-type', 'grossing',
            '--no-enrich',
        ])

        assert rc == 0
        mock_submit.assert_called_once()
        _args, kwargs = mock_submit.call_args
        assert kwargs.get('chart_types') == ['top-grossing']


def test_cli_stats_radar_monetization_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['stats', 'radar', '--help'])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert '--monetization' in captured.out


def test_cli_stats_radar_monetization_filter(tmp_path: Path, capsys):
    data_dir = tmp_path / 'data'
    repo = Repository(data_dir)
    repo.initialize()

    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-cli-1',
        snap_id='snap-vn-free',
        country='vn',
        date_str='2026-09-11',
        observed_time_str='2026-09-11T08:00:00Z',
        entries=[
            ('1001', 1, 'Game Hybrid'),
            ('1002', 5, 'Game Ads'),
        ],
        metadata_map={
            '1001': {
                'description': 'Match three puzzle with coin packs.',
                'in_app_purchases': [{'name': 'Pack', 'price': 1.99}],
            }
        },
    )

    service = AnalysisService(repo)
    service.analyze_date('2026-09-11', ['vn'])

    # Query with monetization filter = HYBRID
    rc = main([
        'stats', 'radar',
        '--data-dir', str(data_dir),
        '--date', '2026-09-11',
        '--country', 'vn',
        '--monetization', 'hybrid',
        '--json',
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert 'Game Hybrid' in captured.out
    assert 'Game Ads' not in captured.out
