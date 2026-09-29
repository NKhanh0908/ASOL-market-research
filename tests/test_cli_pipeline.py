from __future__ import annotations

from contextlib import closing
from pathlib import Path

from casual_scout import cli


def test_pipeline_analyzes_all_successful_markets_after_a_partial_collection(
    collection_fixture, monkeypatch
) -> None:
    from dataclasses import replace
    from datetime import UTC, datetime

    repo, provider, jobs, _collector = collection_fixture
    countries = ['vn', 'th', 'id', 'my', 'ph', 'sg', 'la', 'kh', 'us']
    fetch = provider.fetch_chart

    def fetch_on_historical_days(chart):
        provider.fail_chart = chart.country == 'kh'
        reply, parsed = fetch(chart)
        # A run can span UTC midnight: analyze each actual observed day, not now().
        day = 24 if chart.country == 'us' else 25
        return replace(reply, started_at=datetime(2026, 9, day, 23, 59, tzinfo=UTC)), parsed

    monkeypatch.setattr(provider, 'fetch_chart', fetch_on_historical_days)
    monkeypatch.setattr('casual_scout.collection.platforms.AppleProvider', lambda _settings: provider)
    run_id = jobs.submit('manual', countries, 'pipeline-nine')
    assert cli.main(['pipeline', '--run-id', run_id, '--data-dir', str(repo.data_dir),
                     '--no-enrich']) == 0
    assert set(provider.requested_countries) == set(countries)
    with closing(repo._connect()) as db:
        rows = db.execute('SELECT DISTINCT date,country FROM daily_rank_analytics').fetchall()
        assert {(r['date'], r['country']) for r in rows} == {
            ('2026-09-24' if c == 'us' else '2026-09-25', c)
            for c in countries if c != 'kh'
        }
        assert db.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()[0] == 'partial'


def test_pipeline_does_not_analyze_when_collection_fails(tmp_path: Path, monkeypatch) -> None:
    class FakeCollector:
        def __init__(self, *args: object) -> None:
            pass

        def execute(self, run_id: str, *, enrich: bool = True) -> str:
            return "failed"

    class UnexpectedAnalysisService:
        def __init__(self, repository: object) -> None:
            raise AssertionError("analysis must not run after a failed collection")

    monkeypatch.setattr("casual_scout.collection.platforms.execute_run", lambda *a, **kw: "failed")
    monkeypatch.setattr(cli, "AnalysisService", UnexpectedAnalysisService)

    exit_code = cli.main(
        ["pipeline", "--run-id", "run-123", "--data-dir", str(tmp_path / "data")]
    )

    assert exit_code == 1
