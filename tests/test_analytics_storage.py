from pathlib import Path

import pytest

from casual_scout.storage import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "data")
    r.initialize()
    return r


def test_canonical_snapshot_crud(repo: Repository):
    # Should be None initially
    assert repo.get_canonical_snapshot("2026-09-10", "vn") is None

    # Needs a valid snapshot_id from a real run
    with repo._write_connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, request_key, trigger, status, started_at) VALUES ('run-1', 'req-1', 'manual', 'succeeded', '2026-09-10T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO charts (id, provider, platform, country, collection, genre, depth, version, endpoint, created_at) VALUES ('chart-1', 'apple', 'ios', 'vn', 'topfreeapplications', '7003', 100, 1, 'url', '2026-09-10T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO market_runs (id, run_id, chart_id, chart_status, enrichment_status, started_at) VALUES ('mr-1', 'run-1', 'chart-1', 'complete', 'complete', '2026-09-10T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO raw_responses (hash, path, endpoint, status, received_at, headers_json, size_bytes) VALUES ('hash-1', 'path-1', 'url', 200, '2026-09-10T00:00:00Z', '{}', 100)"
        )
        conn.execute(
            "INSERT INTO snapshots (id, market_run_id, raw_hash, observed_at, quality, issues_json) VALUES ('snap-1', 'mr-1', 'hash-1', '2026-09-10T00:00:00Z', 'complete', '[]')"
        )

    repo.save_canonical_snapshot("2026-09-10", "vn", "snap-1", "2026-09-10T00:00:00Z")
    canonical = repo.get_canonical_snapshot("2026-09-10", "vn")
    assert canonical is not None
    assert canonical["snapshot_id"] == "snap-1"


def test_daily_analytics_crud(repo: Repository):
    records = [
        {
            "id": "an-1",
            "date": "2026-09-10",
            "country": "vn",
            "app_id": "123456",
            "current_rank": 5,
            "rank_1d_ago": 30,
            "delta_1d": 25,
            "rank_3d_ago": None,
            "delta_3d": None,
            "rank_7d_ago": None,
            "delta_7d": None,
            "signal": "FAST_RISER",
            "signal_reasons": ["delta_1d >= 20 (+25)"],
            "subgenre": "Puzzle",
            "mechanic": "Match-3",
            "mechanic_evidence": "match 3 gems",
            "mechanic_confidence": "high",
            "cross_market_count": 3,
            "cross_markets": ["vn", "th", "sg"],
            "created_at": "2026-09-10T01:00:00Z",
        }
    ]
    repo.save_daily_analytics(records)
    results = repo.get_daily_analytics("2026-09-10", "vn")
    assert len(results) == 1
    assert results[0]["app_id"] == "123456"
    assert results[0]["signal"] == "FAST_RISER"
    assert results[0]["mechanic"] == "Match-3"
    assert results[0]["cross_market_count"] == 3

    # Test filtering by signal
    fast_risers = repo.get_daily_analytics("2026-09-10", "vn", signal="FAST_RISER")
    assert len(fast_risers) == 1
    new_entries = repo.get_daily_analytics("2026-09-10", "vn", signal="NEW_ENTRY")
    assert len(new_entries) == 0

    # Test rank history for this app
    history = repo.get_app_rank_history("123456", "vn")
    assert len(history) == 1
    assert history[0]["date"] == "2026-09-10"
    assert history[0]["current_rank"] == 5
