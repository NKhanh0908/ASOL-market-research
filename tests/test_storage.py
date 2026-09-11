import copy
import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from casual_scout.models import Chart, HttpResult, ParsedChart
from casual_scout.providers.apple import parse_chart
from casual_scout.storage import RawStore, Repository


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
def repo(tmp_path):
    repository = Repository(tmp_path)
    repository.initialize()
    return repository


@pytest.fixture
def complete_payload(evidence_dir):
    body = (evidence_dir / "vn-casual-100.json").read_bytes()
    observed_at = datetime(2026, 9, 10, 1, tzinfo=UTC)
    response = HttpResult(
        url="https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json",
        started_at=observed_at,
        elapsed_ms=125,
        status=200,
        body=body,
        headers={"content-type": "application/json"},
        error=None,
    )
    return response, parse_chart(body, Chart("vn"))


@pytest.fixture
def partial_payload(evidence_dir):
    source = (evidence_dir / "vn-casual-100.json").read_bytes()
    payload = copy.deepcopy(json.loads(source.decode("utf-8-sig")))
    payload["feed"]["entry"].pop()
    body = json.dumps(payload, ensure_ascii=False).encode()
    observed_at = datetime(2026, 9, 10, 2, tzinfo=UTC)
    response = HttpResult(
        url="https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json",
        started_at=observed_at,
        elapsed_ms=100,
        status=200,
        body=body,
        headers={"content-type": "application/json"},
        error=None,
    )
    return response, parse_chart(body, Chart("vn"))


def test_partial_does_not_replace_latest_complete(repo, complete_payload, partial_payload):
    response, parsed = complete_payload
    _seed_run(repo, "run-1", response.started_at)
    first = repo.save_snapshot("run-1", response, parsed)
    response2, parsed2 = partial_payload
    _seed_run(repo, "run-2", response2.started_at)
    repo.save_snapshot("run-2", response2, parsed2)

    assert repo.latest_complete(parsed.chart)["id"] == first
    assert len(repo.get_snapshot(first)["entries"]) == 100


def test_same_app_id_keeps_independent_country_ranks(repo, complete_payload):
    response, parsed = complete_payload
    _seed_run(repo, "run-vn", response.started_at)
    vn_snapshot = repo.save_snapshot("run-vn", response, parsed)

    us_entry = replace(parsed.entries[0], rank=17)
    us_parsed = ParsedChart(
        chart=Chart("us"),
        entries=[us_entry],
        source_updated=parsed.source_updated,
        quality="partial",
        issues=["expected 100 entries, received 1"],
    )
    us_response = replace(
        response,
        url="https://itunes.apple.com/us/rss/topfreeapplications/limit=100/genre=7003/json",
        started_at=response.started_at + timedelta(hours=1),
    )
    _seed_run(repo, "run-us", us_response.started_at)
    us_snapshot = repo.save_snapshot("run-us", us_response, us_parsed)

    assert repo.get_snapshot(vn_snapshot)["entries"][0]["rank"] == 1
    assert repo.get_snapshot(us_snapshot)["entries"][0] == {
        "app_id": parsed.entries[0].app_id,
        "rank": 17,
        "name": parsed.entries[0].name,
        "store_url": parsed.entries[0].store_url,
        "icon_url": parsed.entries[0].icon_url,
        "developer": parsed.entries[0].developer,
        "source_genres": parsed.entries[0].source_genres,
    }


def test_retrying_the_same_market_run_returns_existing_snapshot(repo, complete_payload):
    response, parsed = complete_payload
    _seed_run(repo, "run-retry", response.started_at)

    first = repo.save_snapshot("run-retry", response, parsed)
    second = repo.save_snapshot("run-retry", response, parsed)

    with sqlite3.connect(repo.database_path) as connection:
        snapshot_count = connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        entry_count = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert second == first
    assert snapshot_count == 1
    assert entry_count == 100


def test_raw_failure_leaves_no_market_snapshot_state(
    repo, complete_payload, monkeypatch
):
    response, parsed = complete_payload
    _seed_run(repo, "run-raw-failure", response.started_at)

    def fail_put(_store, _body):
        raise OSError("disk full")

    monkeypatch.setattr(RawStore, "put", fail_put)
    with pytest.raises(OSError, match="disk full"):
        repo.save_snapshot("run-raw-failure", response, parsed)

    with sqlite3.connect(repo.database_path) as connection:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("market_runs", "snapshots", "entries", "raw_responses")
        )
    assert counts == (0, 0, 0, 0)


def test_every_http_attempt_is_recorded(repo, complete_payload):
    response, parsed = complete_payload
    first_attempt = replace(
        response,
        elapsed_ms=20,
        status=500,
        body=b"temporary failure",
        error=None,
        attempts=(),
    )
    final_attempt = replace(response, elapsed_ms=40, attempts=())
    response = replace(response, attempts=(first_attempt, final_attempt))
    _seed_run(repo, "run-attempts", response.started_at)

    repo.save_snapshot("run-attempts", response, parsed)

    with sqlite3.connect(repo.database_path) as connection:
        observations = connection.execute(
            """
            SELECT retry_index, status, elapsed_ms, response_bytes
            FROM request_observations
            ORDER BY retry_index
            """
        ).fetchall()
    assert observations == [(1, 500, 20, 17), (2, 200, 40, len(response.body))]


def test_raw_store_is_content_addressed_and_rejects_corrupt_existing_file(tmp_path):
    store = RawStore(tmp_path / "raw")
    body = b"immutable evidence"

    digest, path = store.put(body)

    assert digest == hashlib.sha256(body).hexdigest()
    assert path.read_bytes() == body
    path.write_bytes(b"different bytes")
    with pytest.raises(RuntimeError, match="different content"):
        store.put(body)
    assert path.read_bytes() == b"different bytes"
