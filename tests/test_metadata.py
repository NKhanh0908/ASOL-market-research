import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from casual_scout.models import Chart, HttpResult
from casual_scout.providers.apple import parse_chart
from casual_scout.storage import Repository


def _response(body: bytes, started_at: datetime) -> HttpResult:
    return HttpResult(
        url="https://itunes.apple.com/lookup?country=vn&id=1,2",
        started_at=started_at,
        elapsed_ms=55,
        status=200,
        body=body,
        headers={"content-type": "application/json"},
        error=None,
    )


def _seed_run(repo: Repository, run_id: str, started_at: datetime) -> None:
    with sqlite3.connect(repo.database_path) as connection:
        connection.execute(
            """
            INSERT INTO runs (id, request_key, trigger, status, started_at)
            VALUES (?, ?, 'manual', 'running', ?)
            """,
            (run_id, f"request-{run_id}", started_at.isoformat()),
        )


@pytest.fixture
def metadata_repo(tmp_path):
    repository = Repository(tmp_path)
    repository.initialize()
    return repository


@pytest.fixture
def chart_snapshot(metadata_repo, evidence_dir):
    body = (evidence_dir / "vn-casual-100.json").read_bytes()
    observed_at = datetime(2026, 9, 10, 1, tzinfo=UTC)
    parsed = parse_chart(body, Chart("vn"))
    chart_response = HttpResult(
        url="https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json",
        started_at=observed_at,
        elapsed_ms=125,
        status=200,
        body=body,
        headers={},
        error=None,
    )
    _seed_run(metadata_repo, "metadata-run", observed_at)
    snapshot_id = metadata_repo.save_snapshot("metadata-run", chart_response, parsed)
    return snapshot_id, parsed


def test_metadata_is_bound_by_app_id_when_lookup_order_changes(
    metadata_repo, chart_snapshot
):
    snapshot_id, parsed = chart_snapshot
    first_id = parsed.entries[0].app_id
    second_id = parsed.entries[1].app_id
    values = {
        second_id: {"trackId": int(second_id), "trackName": "Second"},
        first_id: {"trackId": int(first_id), "trackName": "First"},
    }
    response = _response(
        json.dumps({"resultCount": 2, "results": list(values.values())}).encode(),
        datetime(2026, 9, 10, 2, tzinfo=UTC),
    )

    versions = metadata_repo.save_metadata("vn", values, response)
    metadata_repo.bind_metadata(
        snapshot_id,
        {first_id: versions[first_id], second_id: versions[second_id]},
    )

    stored = metadata_repo.get_snapshot(snapshot_id)
    assert stored["metadata_versions"] == {
        first_id: versions[first_id],
        second_id: versions[second_id],
    }
    with sqlite3.connect(metadata_repo.database_path) as connection:
        statuses = connection.execute(
            """
            SELECT chart_status, enrichment_status
            FROM market_runs
            WHERE run_id = 'metadata-run'
            """
        ).fetchone()
    assert statuses == ("complete", "partial")


def test_metadata_cache_is_fresh_for_only_twenty_four_hours(metadata_repo):
    fetched_at = datetime(2026, 9, 10, 2, tzinfo=UTC)
    values = {"123": {"trackId": 123, "trackName": "Cached"}}
    response = _response(b'{"resultCount":1}', fetched_at)
    versions = metadata_repo.save_metadata("vn", values, response)

    assert metadata_repo.cached_metadata(
        "vn", ["123", "missing"], fetched_at + timedelta(hours=24)
    ) == {"123": versions["123"]}
    assert metadata_repo.cached_metadata(
        "vn", ["123"], fetched_at + timedelta(hours=24, seconds=1)
    ) == {}


def test_closed_run_keeps_its_original_metadata_versions(
    metadata_repo, chart_snapshot
):
    snapshot_id, parsed = chart_snapshot
    app_id = parsed.entries[0].app_id
    old_values = {app_id: {"trackId": int(app_id), "trackName": "Old name"}}
    old_response = _response(b'{"resultCount":1,"generation":"old"}', datetime(2026, 9, 10, 2, tzinfo=UTC))
    old_version = metadata_repo.save_metadata("vn", old_values, old_response)[app_id]
    metadata_repo.bind_metadata(snapshot_id, {app_id: old_version})
    with sqlite3.connect(metadata_repo.database_path) as connection:
        connection.execute(
            """
            UPDATE runs SET status = 'succeeded', ended_at = ?
            WHERE id = 'metadata-run'
            """,
            (datetime(2026, 9, 10, 3, tzinfo=UTC).isoformat(),),
        )

    new_values = {app_id: {"trackId": int(app_id), "trackName": "New name"}}
    new_response = _response(b'{"resultCount":1,"generation":"new"}', datetime(2026, 9, 11, 2, tzinfo=UTC))
    new_version = metadata_repo.save_metadata("vn", new_values, new_response)[app_id]
    with pytest.raises(RuntimeError, match="closed run"):
        metadata_repo.bind_metadata(snapshot_id, {app_id: new_version})

    assert metadata_repo.get_snapshot(snapshot_id)["metadata_versions"] == {
        app_id: old_version
    }


def test_metadata_version_from_another_country_cannot_be_bound(
    metadata_repo, chart_snapshot
):
    snapshot_id, parsed = chart_snapshot
    app_id = parsed.entries[0].app_id
    values = {app_id: {"trackId": int(app_id), "trackName": "Wrong country"}}
    response = replace(
        _response(b'{"resultCount":1}', datetime(2026, 9, 10, 2, tzinfo=UTC)),
        url=f"https://itunes.apple.com/lookup?country=us&id={app_id}",
    )
    version = metadata_repo.save_metadata("us", values, response)[app_id]

    with pytest.raises(ValueError, match="does not match snapshot"):
        metadata_repo.bind_metadata(snapshot_id, {app_id: version})
    assert metadata_repo.get_snapshot(snapshot_id)["metadata_versions"] == {}


def test_metadata_without_response_body_is_not_committed(metadata_repo):
    response = _response(b"body", datetime(2026, 9, 10, 2, tzinfo=UTC))
    response = replace(response, body=None, status=None, error="timeout")

    with pytest.raises(ValueError, match="response body"):
        metadata_repo.save_metadata(
            "vn", {"123": {"trackId": 123, "trackName": "Missing raw"}}, response
        )

    with sqlite3.connect(metadata_repo.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM metadata_versions").fetchone()[0] == 0
