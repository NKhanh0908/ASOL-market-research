import json
from pathlib import Path

import pytest

from casual_scout.models import Chart
from casual_scout.providers.google_parser import (
    minimum_from_ascii_display,
    parse_google_chart,
    parse_google_metadata,
)


def test_google_keeps_feed_identity():
    chart = Chart(
        "vn",
        provider="google",
        platform="android",
        genre="GAME_CASUAL",
        feed_type="top-grossing",
    )
    assert chart.collection == "top-grossing"
    assert chart.platform == "android"
    assert chart.provider == "google"

    # Apple default remains untouched
    apple_chart = Chart("vn", feed_type="top-grossing")
    assert apple_chart.collection == "topgrossingapplications"
    assert apple_chart.platform == "ios"


def test_invalid_google_chart_identity_raises():
    with pytest.raises(ValueError, match="invalid Google chart identity"):
        Chart("vn", provider="google", platform="android", feed_type="invalid-feed")


def test_parse_verified_chart_fixtures():
    root = Path(__file__).parent / "fixtures" / "google_play"
    cases = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for case in cases:
        chart = Chart(
            case["country"],
            provider="google",
            platform="android",
            genre="GAME_CASUAL",
            feed_type=case["feed"],
        )
        body = (root / case["body_file"]).read_bytes()
        parsed = parse_google_chart(body, chart)
        assert parsed.quality == "complete"
        assert [(e.app_id, e.rank) for e in parsed.entries] == [
            (e["package"], e["rank"]) for e in case["expected_entries"]
        ]
        assert len(parsed.entries) == len(case["expected_entries"])
        for idx, entry in enumerate(parsed.entries):
            exp = case["expected_entries"][idx]
            assert entry.name == exp["name"]
            assert entry.developer == exp["developer"]
            assert entry.icon_url == exp["icon_url"]
            assert entry.store_url == exp["store_url"]


def test_parse_malformed_chart_returns_invalid():
    chart = Chart("vn", provider="google", platform="android", feed_type="top-free")
    parsed = parse_google_chart(b"not json at all", chart)
    assert parsed.quality == "invalid"
    assert parsed.entries == []
    assert len(parsed.issues) > 0


def test_parse_google_metadata_complete():
    # Build a simulated AF_initDataCallback with ds:5
    sample_ds5 = [
        None,
        [
            None,
            None,
            [
                ["Sample Casual Game"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                ["Everyone"],
                ["2024-01-01"],
                None,
                [[["Full description of the game."]]],
                ["50,000,000+", 50000000, 52100000, "50M+"],
                None,
                None,
                None,
                None,
                None,
                ["In-app purchases"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                ["Contains ads"],
                None,
                None,
                [None, 4.65, None, 125000, 4.7],
                None,
                None,
                None,
                None,
                None,
                [[[[None, None, 0, None, "USD", "$0.00"]]]],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                ["Awesome Studio LLC"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                ["Casual", None, "GAME_CASUAL"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                [[None, None, None, "https://play-lh.googleusercontent.com/icon.png"]],
            ],
        ],
    ]
    html_body = f"""<html>
    <script>
    AF_initDataCallback({{key: 'ds:5', hash: '2', data: {json.dumps(sample_ds5)}, sideChannel: {{}}}});
    </script>
    </html>""".encode("utf-8")

    meta = parse_google_metadata(html_body, "com.example.casual")
    assert meta["status"] == "complete"
    assert meta["name"] == "Sample Casual Game"
    assert meta["developer"] == "Awesome Studio LLC"
    assert meta["description"] == "Full description of the game."
    assert meta["average_rating"] == 4.65
    assert meta["rating_count"] == 125000
    assert meta["installs"] == "50,000,000+"
    assert meta["min_installs"] == 50000000
    assert meta["has_ads"] is True
    assert meta["has_iap"] is True
    assert meta["price"] == 0.0
    assert meta["currency"] == "USD"
    assert meta["icon_url"] == "https://play-lh.googleusercontent.com/icon.png"
    assert meta["store_url"] == "https://play.google.com/store/apps/details?id=com.example.casual"
    assert meta["genres"] == [{"name": "Casual"}]


def test_parse_google_metadata_partial_when_app_removed():
    meta = parse_google_metadata(b"<html>Error 404 App not found</html>", "com.missing.app")
    assert meta["status"] == "partial"
    assert meta["error"] == "metadata payload missing ds:5 callback"
    assert meta["name"] is None
    assert meta["installs"] is None
    assert meta["min_installs"] is None


def test_minimum_from_ascii_display():
    assert minimum_from_ascii_display("10,000,000+") == 10000000
    assert minimum_from_ascii_display("50M+") == 50000000
    assert minimum_from_ascii_display("500K+") == 500000
    assert minimum_from_ascii_display("1B+") == 1000000000
    assert minimum_from_ascii_display("unknown") is None
