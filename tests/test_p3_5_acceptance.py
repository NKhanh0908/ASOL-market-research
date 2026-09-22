from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from test_analysis_service import _create_snapshot_with_entries

from casual_scout.analysis.service import AnalysisService
from casual_scout.collection.service import Collector
from casual_scout.config import Settings
from casual_scout.models import Chart
from casual_scout.providers.apple import parse_chart
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


def test_p3_5_collects_an_immutable_grossing_snapshot(collection_fixture):
    """A collector regression must not drop the Grossing chart or its raw evidence."""
    repo, provider, jobs, _collector = collection_fixture

    class GrossingFixtureProvider:
        def fetch_chart(self, chart: Chart):
            result, _parsed = provider.fetch_chart(chart)
            body = (result.body or b"").replace(
                b"topfreeapplications", b"topgrossingapplications"
            )
            result = replace(
                result,
                body=body,
                url=result.url.replace("topfreeapplications", "topgrossingapplications"),
            )
            return result, parse_chart(body, chart)

    collector = Collector(repo, GrossingFixtureProvider(), jobs)
    run_id = jobs.submit(
        "manual", ["vn"], "p3-5-grossing-collection", chart_types=["top-grossing"]
    )

    assert collector.execute(run_id, enrich=False) == "succeeded"

    snapshot = repo.latest_complete(Chart("vn", feed_type="top-grossing"))
    assert snapshot is not None
    raw_hash = snapshot["raw_hash"]
    assert (repo._raw.root / raw_hash[:2] / raw_hash).is_file()


def test_p3_5_exposes_grossing_snapshot_and_monetized_radar(tmp_path: Path):
    """A missing Grossing chart route or rank correlation must fail this flow."""
    data_dir = tmp_path / "data"
    repo = Repository(data_dir)
    repo.initialize()

    _create_snapshot_with_entries(
        repo, "run-free", "snapshot-free", "vn", "2026-09-11", "2026-09-11T08:00:00Z",
        [("1001", 5, "Hybrid Hero")],
        metadata_map={
            "1001": {
                "description": "Match three puzzle with coin packs.",
                "in_app_purchases": [{"name": "Coin pack", "price": 1.99}],
            }
        },
    )
    _create_snapshot_with_entries(
        repo, "run-grossing", "snapshot-grossing", "vn", "2026-09-11", "2026-09-11T08:00:00Z",
        [("1001", 3, "Hybrid Hero")],
        collection="topgrossingapplications",
    )
    AnalysisService(repo).analyze_date("2026-09-11", countries=["vn"])
    app = create_app(Settings(data_dir))
    client = TestClient(app)

    grossing = client.get("/api/charts/grossing?country=vn&date=2026-09-11")
    assert grossing.status_code == 200
    assert grossing.json()["entries"] == [{"app_id": "1001", "rank": 3, "name": "Hybrid Hero"}]

    radar = client.get("/api/stats/radar?country=vn&date=2026-09-11").json()
    assert radar[0]["grossing_rank"] == 3
    assert radar[0]["monetization_model"] == "HYBRID"
    assert radar[0]["grossing_power"] == 15.0
