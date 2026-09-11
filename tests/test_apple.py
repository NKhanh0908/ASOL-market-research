import copy
import hashlib
import json
from datetime import UTC, datetime

import pytest

from casual_scout.config import Settings
from casual_scout.models import Chart, HttpResult
from casual_scout.providers.apple import AppleProvider, parse_chart, parse_lookup


def _chart_payload(evidence_dir) -> tuple[bytes, dict]:
    raw = (evidence_dir / "vn-casual-100.json").read_bytes()
    return raw, json.loads(raw.decode("utf-8-sig"))


def _encoded(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode()


def test_casual_feed_preserves_source_order(evidence_dir):
    result = parse_chart((evidence_dir / "vn-casual-100.json").read_bytes(), Chart("vn"))

    assert result.quality == "complete"
    assert len(result.entries) == 100
    assert result.entries[0].app_id == "6757412443"
    assert [entry.rank for entry in result.entries] == list(range(1, 101))
    assert result.entries[0].store_url.startswith("https://apps.apple.com/vn/")


def test_chart_with_missing_source_entry_is_partial(evidence_dir):
    raw, payload = _chart_payload(evidence_dir)
    original_hash = hashlib.sha256(raw).hexdigest()
    payload["feed"]["entry"].pop()

    result = parse_chart(_encoded(payload), Chart("vn"))

    assert result.quality == "partial"
    assert len(result.entries) == 99
    assert hashlib.sha256((evidence_dir / "vn-casual-100.json").read_bytes()).hexdigest() == original_hash


def test_chart_with_duplicate_source_id_is_invalid(evidence_dir):
    _, payload = _chart_payload(evidence_dir)
    payload["feed"]["entry"][1]["id"]["attributes"]["im:id"] = "6757412443"

    result = parse_chart(_encoded(payload), Chart("vn"))

    assert result.quality == "invalid"
    assert any("duplicate app id" in issue for issue in result.issues)


def test_chart_without_self_link_is_invalid(evidence_dir):
    _, payload = _chart_payload(evidence_dir)
    payload["feed"]["link"] = [
        link
        for link in payload["feed"]["link"]
        if link["attributes"].get("rel") != "self"
    ]

    result = parse_chart(_encoded(payload), Chart("vn"))

    assert result.quality == "invalid"
    assert "missing self link" in result.issues


@pytest.mark.parametrize(
    "chart",
    [
        Chart("vn", provider="other"),
        Chart("vn", platform="android"),
        Chart("vn", version=2),
    ],
)
def test_chart_with_unsupported_identity_is_invalid(evidence_dir, chart):
    result = parse_chart((evidence_dir / "vn-casual-100.json").read_bytes(), chart)

    assert result.quality == "invalid"
    assert "unsupported Apple chart configuration" in result.issues


@pytest.mark.parametrize(
    ("mutation", "expected_issue"),
    [
        (
            lambda payload: payload["feed"]["link"].__setitem__(
                -1,
                {"attributes": {"rel": "self", "href": "https://itunes.apple.com/us/rss/topfreeapplications/limit=100/genre=7003/json"}},
            ),
            "self link country",
        ),
        (
            lambda payload: payload["feed"]["link"].__setitem__(
                -1,
                {"attributes": {"rel": "self", "href": "https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=6014/json"}},
            ),
            "self link genre",
        ),
        (lambda payload: payload["feed"]["title"].__setitem__("label", "Top Free Applications"), "title"),
    ],
)
def test_chart_with_mismatched_source_identity_is_invalid(evidence_dir, mutation, expected_issue):
    _, payload = _chart_payload(evidence_dir)
    mutation(payload)

    result = parse_chart(_encoded(payload), Chart("vn"))

    assert result.quality == "invalid"
    assert any(expected_issue in issue for issue in result.issues)


def test_invalid_chart_json_is_invalid():
    result = parse_chart(b"{not json", Chart("vn"))

    assert result.quality == "invalid"
    assert result.entries == []
    assert result.issues == ["invalid JSON"]


def test_chart_with_more_entries_than_depth_is_invalid(evidence_dir):
    _, payload = _chart_payload(evidence_dir)
    additional = copy.deepcopy(payload["feed"]["entry"][-1])
    additional["id"]["attributes"]["im:id"] = "9999999999"
    additional["id"]["label"] = "https://apps.apple.com/vn/app/example/id9999999999?uo=2"
    additional["link"][0]["attributes"]["href"] = "https://apps.apple.com/vn/app/example/id9999999999?uo=2"
    payload["feed"]["entry"].append(additional)

    result = parse_chart(_encoded(payload), Chart("vn"))

    assert result.quality == "invalid"
    assert any("expected 100 entries, received 101" in issue for issue in result.issues)


def test_lookup_returns_only_requested_metadata(evidence_dir):
    metadata = parse_lookup(
        (evidence_dir / "vn-lookup-sample.json").read_bytes(), ["6757412443", "missing-id"]
    )

    assert set(metadata) == {"6757412443"}
    assert metadata["6757412443"]["trackName"] == "Block Blast!"


class _RecordingHttp:
    def __init__(self, body: bytes):
        self.body = body
        self.urls: list[str] = []

    def get(self, url: str) -> HttpResult:
        self.urls.append(url)
        return HttpResult(
            url=url,
            started_at=datetime(2026, 9, 10, tzinfo=UTC),
            elapsed_ms=12,
            status=200,
            body=self.body,
            headers={},
            error=None,
        )


def test_provider_fetches_only_the_configured_casual_chart(evidence_dir, tmp_path):
    http = _RecordingHttp((evidence_dir / "vn-casual-100.json").read_bytes())
    provider = AppleProvider(Settings(data_dir=tmp_path), http=http)

    result, parsed = provider.fetch_chart(Chart("vn"))

    assert result.status == 200
    assert parsed.quality == "complete"
    assert http.urls == ["https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json"]


def test_provider_rejects_lookup_batches_larger_than_twenty(evidence_dir, tmp_path):
    provider = AppleProvider(Settings(data_dir=tmp_path), http=_RecordingHttp(b'{"results": []}'))

    with pytest.raises(ValueError, match="at most 20"):
        provider.fetch_metadata("vn", [str(index) for index in range(21)])
