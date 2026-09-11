import json
from pathlib import Path

import pytest
from test_analysis_service import _create_snapshot_with_entries

from casual_scout.cli import main
from casual_scout.storage import Repository


def test_cli_analyze_and_trends(tmp_path: Path, capsys: pytest.CaptureFixture):
    repo = Repository(tmp_path / 'data')
    repo.initialize()

    # Day 1 & Day 2 snapshots
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-d1',
        snap_id='snap-d1-vn',
        country='vn',
        date_str='2026-09-09',
        observed_time_str='2026-09-09T08:00:00Z',
        entries=[('1001', 30, 'Royal Match')],
    )
    _create_snapshot_with_entries(
        repo=repo,
        run_id='run-d2',
        snap_id='snap-d2-vn',
        country='vn',
        date_str='2026-09-10',
        observed_time_str='2026-09-10T08:00:00Z',
        entries=[('1001', 5, 'Royal Match 3D')],
        metadata_map={'1001': {'description': 'Match 3 tiles'}},
    )

    # Test analyze CLI command
    ret = main(['analyze', '--data-dir', str(tmp_path / 'data'), '--date', '2026-09-10', '--countries', 'vn'])
    assert ret == 0
    captured = capsys.readouterr()
    assert 'Analyzed 2026-09-10' in captured.out or 'vn' in captured.out

    # Test trends CLI command
    ret = main(['trends', '--data-dir', str(tmp_path / 'data'), '--date', '2026-09-10', '--country', 'vn'])
    assert ret == 0
    captured = capsys.readouterr()
    assert 'Royal Match' in captured.out or '1001' in captured.out

    # Test trends CLI with --json
    ret = main(['trends', '--data-dir', str(tmp_path / 'data'), '--date', '2026-09-10', '--country', 'vn', '--json'])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]['app_id'] == '1001'
    assert data[0]['signal'] == 'FAST_RISER'