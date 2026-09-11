from datetime import UTC, datetime
from pathlib import Path

import pytest

from casual_scout.models import Chart, HttpResult, ParsedChart
from casual_scout.providers.apple import parse_chart, parse_lookup
from casual_scout.storage import Repository


class FakeProvider:
    def __init__(self, evidence_dir: Path) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.chart = Chart("vn")
        self.requested_countries: list[str] = []
        self.lookup_call_count = 0
        self.chart_call_count = 0
        self.fail_chart = False
        self.fail_lookup = False
        self.partial_chart = False

    def fetch_chart(self, chart: Chart) -> tuple[HttpResult, ParsedChart]:
        self.chart_call_count += 1
        self.requested_countries.append(chart.country)
        now = datetime.now(UTC)
        if self.fail_chart:
            http_result = HttpResult(
                url=f"https://itunes.apple.com/{chart.country}/rss/topfreeapplications/limit=100/genre=7003/json",
                started_at=now,
                elapsed_ms=100,
                status=500,
                body=b"Internal Server Error",
                headers={"content-type": "text/plain"},
                error="HTTP 500",
            )
            return http_result, ParsedChart(chart, [], None, "invalid", ["HTTP 500 error"])

        file_path = self.evidence_dir / f"{chart.country}-casual-100.json"
        if not file_path.exists():
            file_path = self.evidence_dir / "vn-casual-100.json"
        body = file_path.read_bytes()

        parsed = parse_chart(body, chart)
        if self.partial_chart:
            parsed = ParsedChart(
                chart=chart,
                entries=parsed.entries[:50],
                source_updated=parsed.source_updated,
                quality="partial",
                issues=["feed only had 50 entries"],
            )

        http_result = HttpResult(
            url=f"https://itunes.apple.com/{chart.country}/rss/topfreeapplications/limit=100/genre=7003/json",
            started_at=now,
            elapsed_ms=50,
            status=200,
            body=body,
            headers={"content-type": "application/json"},
            error=None,
        )
        return http_result, parsed

    def fetch_metadata(self, country: str, ids: list[str]) -> tuple[HttpResult, dict[str, dict]]:
        self.lookup_call_count += 1
        now = datetime.now(UTC)
        if self.fail_lookup:
            http_result = HttpResult(
                url=f"https://itunes.apple.com/lookup?country={country}&id={','.join(ids)}",
                started_at=now,
                elapsed_ms=100,
                status=500,
                body=b"Internal Server Error",
                headers={"content-type": "text/plain"},
                error="HTTP 500",
            )
            return http_result, {}

        # Look for lookup sample or batch 20
        candidates = [
            self.evidence_dir / f"{country}-lookup-casual-20.json",
            self.evidence_dir / f"{country}-lookup-sample.json",
            self.evidence_dir / "lookup-batch20-results.json",
            self.evidence_dir / "vn-lookup-casual-20.json",
        ]
        body = b'{"resultCount": 0, "results": []}'
        for cand in candidates:
            if cand.exists():
                body = cand.read_bytes()
                break

        parsed_metadata = parse_lookup(body, ids)
        for aid in ids:
            if aid not in parsed_metadata:
                parsed_metadata[aid] = {
                    "name": f"App {aid}",
                    "developer": "Test Dev",
                    "primary_genre": "Casual",
                    "genres": [{"genreId": "7003", "name": "Casual"}],
                    "description": "Test description",
                    "average_rating": 4.5,
                    "rating_count": 100,
                    "store_url": f"https://apps.apple.com/{country}/app/id{aid}",
                    "price": 0.0,
                    "currency": "USD",
                }
        http_result = HttpResult(
            url=f"https://itunes.apple.com/lookup?country={country}&id={','.join(ids)}",
            started_at=now,
            elapsed_ms=60,
            status=200,
            body=body,
            headers={"content-type": "application/json"},
            error=None,
        )
        return http_result, parsed_metadata


@pytest.fixture
def evidence_dir() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "core"
        / "research"
        / "evidence"
        / "2026-09-10-ios-p1"
    )


@pytest.fixture
def fake_provider(evidence_dir: Path) -> FakeProvider:
    return FakeProvider(evidence_dir)


@pytest.fixture
def collection_fixture(tmp_path: Path, evidence_dir: Path):
    from casual_scout.collection.jobs import JobService
    from casual_scout.collection.service import Collector

    repo = Repository(tmp_path)
    repo.initialize()
    provider = FakeProvider(evidence_dir)
    jobs = JobService(repo)
    collector = Collector(repo, provider, jobs)
    return repo, provider, jobs, collector
