from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from casual_scout.collection.jobs import JobService
from casual_scout.collection.service import Collector
from casual_scout.config import Settings
from casual_scout.models import Chart
from casual_scout.providers.apple import AppleProvider
from casual_scout.providers.http import HttpClient, RequestGate
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


def test_p1_end_to_end_offline_acceptance(evidence_dir: Path, tmp_path: Path):
    data_dir = tmp_path / "acceptance_data"
    settings = Settings(data_dir=data_dir)
    repo = Repository(data_dir)
    repo.initialize()

    # Fixtures
    vn_chart_bytes = (evidence_dir / "vn-casual-100.json").read_bytes()
    vn_lookup_bytes = (evidence_dir / "vn-lookup-sample.json").read_bytes()
    us_chart_bytes = (evidence_dir / "us-casual-100.json").read_bytes()

    vn_chart_data = json.loads(vn_chart_bytes.decode("utf-8-sig"))
    expected_vn_entry_count = len(vn_chart_data["feed"]["entry"])
    assert expected_vn_entry_count == 100


    requested_urls: list[str] = []

    def handle_mock_request(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        requested_urls.append(url_str)

        if "vn/rss/topfreeapplications" in url_str:
            return httpx.Response(
                200,
                content=vn_chart_bytes,
                headers={"content-type": "application/json", "last-modified": "Wed, 10 Sep 2026 00:00:00 GMT"},
                request=request,
            )
        if "us/rss/topfreeapplications" in url_str:
            return httpx.Response(
                200,
                content=us_chart_bytes,
                headers={"content-type": "application/json"},
                request=request,
            )
        if "lookup" in url_str and "country=vn" in url_str:
            return httpx.Response(
                200,
                content=vn_lookup_bytes,
                headers={"content-type": "application/json"},
                request=request,
            )
        if "lookup" in url_str and "country=us" in url_str:
            return httpx.Response(
                500,
                content=b"Internal Server Error",
                headers={"content-type": "text/plain"},
                request=request,
            )
        return httpx.Response(404, content=b"Not Found", request=request)

    mock_transport = httpx.MockTransport(handle_mock_request)
    http_client = httpx.Client(transport=mock_transport)
    http = HttpClient(
        settings=settings,
        client=http_client,
        sleep=lambda _s: None,
        clock=lambda: datetime.now(UTC),
        gate=RequestGate(),
    )

    provider = AppleProvider(settings, http=http)
    jobs = JobService(repo)

    collector = Collector(repo, provider, jobs)

    # 1. Run Collection covering VN (complete), US (lookup partial/fail), TL (unverified)
    req_key = "acceptance-run-01"
    run_id = jobs.submit("manual", ["vn", "us", "tl"], req_key)

    # Collector executes job (partial because US lookup returned 500)
    status = collector.execute(run_id, enrich=True)
    assert status == "partial"


    # 2. Verify Timor-Leste (TL) handling
    # Confirm no HTTP request was made with "tl" in URL
    assert not any("/tl/" in call_url for call_url in requested_urls)

    # Check market_runs status for TL in DB
    with repo._connect() as conn:
        tl_mr = conn.execute(
            """
            SELECT market_runs.chart_status, market_runs.error
            FROM market_runs
            JOIN charts ON charts.id = market_runs.chart_id
            WHERE market_runs.run_id = ? AND charts.country = 'tl'
            """,
            (run_id,),
        ).fetchone()
        assert tl_mr is not None
        assert tl_mr["chart_status"] == "failed"
        assert "not verified" in tl_mr["error"]


    # 3. Test duplicate request_key deduplication
    duplicate_run_id = jobs.submit("manual", ["vn", "us", "tl"], req_key)
    assert duplicate_run_id == run_id
    with pytest.raises(ValueError, match="scope mismatch"):
        jobs.submit("manual", ["vn"], req_key)

    # 4. Verify VN snapshot and metadata in DB
    vn_snap = repo.latest_complete(Chart("vn"))
    assert vn_snap is not None
    assert len(vn_snap["entries"]) == 100
    assert vn_snap["quality"] == "complete"
    assert vn_snap["entries"][0]["rank"] == 1

    first_entry_app_id = vn_snap["entries"][0]["app_id"]
    # Check that metadata version was bound for VN
    assert first_entry_app_id in vn_snap["metadata_versions"]

    # 5. Verify US snapshot (chart succeeded, enrichment failed gracefully)
    us_snap = repo.latest_complete(Chart("us"))
    assert us_snap is not None
    assert len(us_snap["entries"]) == 100
    assert us_snap["quality"] == "complete"

    # 6. Test Web UI integration with TestClient
    app = create_app(repo)
    client = TestClient(app)

    # Test Root / (Dashboard) for VN
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert "Casual Scout" in resp_root.text
    assert "Vietnam" in resp_root.text
    assert vn_snap["entries"][0]["name"] in resp_root.text

    # Test CSV Export
    resp_csv = client.get("/data/download?country=vn&format=csv")
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "rank" in resp_csv.text and "name" in resp_csv.text and "developer" in resp_csv.text

    # Test Runs screen
    resp_runs = client.get("/runs")
    assert resp_runs.status_code == 200
    assert run_id in resp_runs.text

    # Test Run detail screen
    resp_run_detail = client.get(f"/runs/{run_id}")
    assert resp_run_detail.status_code == 200
    assert "vn" in resp_run_detail.text
    assert "us" in resp_run_detail.text
    assert "tl" in resp_run_detail.text

    # Test Game Detail screen
    resp_game = client.get(f"/games/{first_entry_app_id}?country=vn")
    assert resp_game.status_code == 200
    assert vn_snap["entries"][0]["name"] in resp_game.text

    # 7. Test Historical Snapshot Immutability:
    # Collecting a second run must preserve old snapshot & metadata versions
    snap_1_id = vn_snap["id"]
    snap_1_meta_version = vn_snap["metadata_versions"][first_entry_app_id]

    # Run second collection
    run_2_id = jobs.submit("manual", ["vn"], "acceptance-run-02")
    collector.execute(run_2_id, enrich=False)

    # Fetch snap 1 again
    snap_1_retrieved = repo.get_snapshot(snap_1_id)
    assert snap_1_retrieved["metadata_versions"][first_entry_app_id] == snap_1_meta_version
    assert snap_1_retrieved["id"] == snap_1_id
