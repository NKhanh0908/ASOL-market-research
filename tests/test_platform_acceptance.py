"""Offline integration acceptance using synthetic HTTP payloads, not live-source evidence."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

from android_core_support import seed_snapshot
from fastapi.testclient import TestClient

from casual_scout.analysis.service import AnalysisService
from casual_scout.collection import platforms
from casual_scout.config import Settings
from casual_scout.models import Entry, HttpResult, ParsedChart
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


class NoopScheduler:
    def start(self):
        pass

    def stop(self):
        pass


class SyntheticGoogleProvider:
    """Deterministic 100-row charts; records actual collection/cache requests."""

    def __init__(self):
        self.chart_requests = []
        self.detail_requests = []

    def fetch_chart(self, chart):
        self.chart_requests.append((chart.country, chart.feed_type))
        packages = [f"com.fixture.game{i}" for i in range(1, 101)]
        if chart.feed_type == "top-grossing":
            packages.reverse()
        entries = [
            Entry(
                package,
                rank,
                f"Fixture Game {package.rsplit('game', 1)[1]}",
                f"https://play.google.com/store/apps/details?id={package}",
                None,
                "Fixture Studio",
                [],
            )
            for rank, package in enumerate(packages, 1)
        ]
        body = json.dumps(
            {
                "fixture": True,
                "request": len(self.chart_requests),
                "feed": chart.feed_type,
                "packages": packages,
            }
        ).encode()
        result = HttpResult(
            "https://fixture.invalid/chart", datetime.now(UTC), 1, 200, body, {}, None
        )
        return result, ParsedChart(chart, entries, None, "complete")

    def fetch_metadata(self, country, packages):
        self.detail_requests.extend((country, package) for package in packages)
        values = {
            package: {
                "name": f"Fixture Game {package.rsplit('game', 1)[1]}",
                "developer": "Fixture Studio",
                "status": "complete",
                "installs": "1M+",
                "min_installs": 1000000,
                "price": 0,
                "has_ads": True,
                "has_iap": True,
                "genres": ["Casual"],
                "description": "merge puzzle",
            }
            for package in packages
        }
        body = json.dumps({"fixture": True, "values": values}, sort_keys=True).encode()
        return [
            (
                HttpResult(
                    "https://fixture.invalid/details", datetime.now(UTC), 1, 200, body, {}, None
                ),
                values,
            )
        ]


def test_signed_api_collection_analysis_views_cache_and_ios_preservation(tmp_path, monkeypatch):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    day = datetime.now(UTC).date().isoformat()
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    seed_snapshot(
        repo,
        "ios-baseline",
        yesterday,
        "topfreeapplications",
        [("123456", 1)],
        platform="ios",
        metadata={"123456": {"trackName": "Preserved iOS"}},
    )
    with repo._write_connection() as conn:
        conn.execute("UPDATE runs SET status='succeeded' WHERE id='ios-baseline'")

    def ios_fingerprint():
        with repo._connect() as conn:
            snapshots = [
                tuple(r) for r in conn.execute("SELECT * FROM snapshots WHERE id='ios-baseline'")
            ]
            entries = [
                tuple(r)
                for r in conn.execute("SELECT * FROM entries WHERE snapshot_id='ios-baseline'")
            ]
            bindings = [
                tuple(r)
                for r in conn.execute(
                    "SELECT * FROM snapshot_metadata WHERE snapshot_id='ios-baseline'"
                )
            ]
            metadata = [
                tuple(r)
                for r in conn.execute("SELECT * FROM metadata_versions WHERE platform='ios'")
            ]
            raw_hashes = {snapshots[0][2]} | {
                r["raw_hash"]
                for r in conn.execute("SELECT raw_hash FROM metadata_versions WHERE platform='ios'")
            }
            raws = [
                tuple(r)
                for r in conn.execute("SELECT * FROM raw_responses")
                if r["hash"] in raw_hashes
            ]
            raw_files = {
                r["hash"]: hashlib.sha256((repo.data_dir / r["path"]).read_bytes()).hexdigest()
                for r in conn.execute("SELECT hash,path FROM raw_responses")
                if r["hash"] in raw_hashes
            }
        return snapshots, entries, bindings, metadata, sorted(raws), raw_files

    preserved = ios_fingerprint()
    provider = SyntheticGoogleProvider()
    monkeypatch.setattr(platforms, "GooglePlayProvider", lambda transport: provider)
    launched = []
    app = create_app(
        Settings(repo.data_dir),
        launcher=lambda run, path: launched.append((run, path)),
        scheduler_factory=lambda *_: NoopScheduler(),
    )
    with TestClient(app) as client:
        assert client.get("/data?platform=android").status_code == 200
        body = {"platform": "android", "markets": ["vn"], "chart_type": "all"}

        def submit(key):
            response = client.post(
                "/api/crawl",
                json=body,
                headers={
                    "Origin": "http://testserver",
                    "X-CSRF-Token": client.cookies["csrftoken"],
                    "Idempotency-Key": key,
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["platform"] == "android"
            return response.json()["run_id"]

        first = submit("acceptance-first")
        assert launched[0] == (first, repo.data_dir)
        assert platforms.execute_run(repo, first) == "succeeded"
        AnalysisService(repo).analyze_date(day, ["vn"], platform="android")
        with repo._connect() as conn:
            snapshots = conn.execute(
                "SELECT s.id FROM snapshots s JOIN market_runs m ON m.id=s.market_run_id WHERE m.run_id=?",
                (first,),
            ).fetchall()
            assert len(snapshots) == 2
            for snapshot in snapshots:
                assert (
                    conn.execute(
                        "SELECT COUNT(*) FROM entries WHERE snapshot_id=?", (snapshot["id"],)
                    ).fetchone()[0]
                    == 100
                )
                assert (
                    conn.execute(
                        "SELECT COUNT(*) FROM snapshot_metadata WHERE snapshot_id=?",
                        (snapshot["id"],),
                    ).fetchone()[0]
                    == 100
                )
                assert all(
                    meta["min_installs"] == 1000000
                    for meta in repo.get_snapshot_metadata(snapshot["id"]).values()
                )
        assert len(provider.detail_requests) == 100
        data = client.get(f"/api/data?platform=android&country=vn&date={day}")
        assert data.status_code == 200
        assert data.json()["platform"] == "android" and len(data.json()["entries"]) == 100
        first_entry = data.json()["entries"][0]
        assert first_entry["app_id"] == "com.fixture.game1"
        assert first_entry["rank"] == 1 and first_entry["min_installs"] == 1000000
        radar = client.get(f"/api/stats/radar?platform=android&country=vn&date={day}")
        assert radar.status_code == 200 and radar.json()
        assert all(row["app_id"].startswith("com.fixture.") for row in radar.json())
        game = client.get(f"/games/com.fixture.game1?platform=android&country=vn&date={day}")
        assert game.status_code == 200
        assert "Google Play" in game.text and "1M+" in game.text
        history = json.loads(re.search(r"const rankHistory = (.*?);", game.text).group(1))
        assert len(history) == 14
        assert history[-1] == {"date": day, "free_rank": 1, "grossing_rank": 100}
        second = submit("acceptance-second")
        assert second != first and len(launched) == 2
        assert platforms.execute_run(repo, second) == "succeeded"
        assert len(provider.chart_requests) == 4  # ranking is always freshly requested
        assert len(provider.detail_requests) == 100  # both feeds and second run use complete cache
        with repo._connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM snapshots s JOIN market_runs m ON m.id=s.market_run_id WHERE m.run_id=?",
                    (second,),
                ).fetchone()[0]
                == 2
            )
    assert ios_fingerprint() == preserved
