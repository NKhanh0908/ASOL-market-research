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
        assert parsed.quality == ("complete" if len(case["expected_entries"]) == 100 else "partial")
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
    chart = Chart(
        "vn", provider="google", platform="android", genre="GAME_CASUAL", feed_type="top-free"
    )
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
    </html>""".encode()

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


def test_grossing_short_source_is_partial():
    chart = Chart(
        "vn", provider="google", platform="android", genre="GAME_CASUAL", feed_type="top-grossing"
    )
    parsed = parse_google_chart(
        (Path(__file__).parent / "fixtures/google_play/vn_top_grossing.bin").read_bytes(), chart
    )
    assert parsed.quality == "partial"
    assert len(parsed.entries) == 49
    assert parsed.issues


def test_metadata_unknown_flags_and_price_stay_unknown():
    details = [["Game"]] + [None] * 12 + [["10,000+", 10000]]
    body = (
        "AF_initDataCallback({key: 'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    meta = parse_google_metadata(body, "com.game")
    assert meta["has_ads"] is None
    assert meta["has_iap"] is None
    assert meta["price"] is None


def mutate_chart(items):
    lines = (
        (Path(__file__).parent / "fixtures/google_play/vn_top_free.bin")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    for line in lines:
        try:
            outer = json.loads(line)
        except ValueError:
            continue
        if isinstance(outer, list):
            for frame in outer:
                if isinstance(frame, list) and frame[:2] == ["wrb.fr", "vyAe2"]:
                    inner = json.loads(frame[2])
                    apps = inner[0][1][0][28][0]
                    inner[0][1][0][28][0] = items(apps)
                    frame[2] = json.dumps(inner)
                    return json.dumps(outer).encode()
    raise AssertionError("fixture RPC missing")


@pytest.mark.parametrize(
    "mutator", [lambda apps: apps + [apps[0]], lambda apps: apps[:1] + apps[:1]]
)
def test_duplicate_chart_is_invalid(mutator):
    chart = Chart(
        "vn", provider="google", platform="android", genre="GAME_CASUAL", feed_type="top-free"
    )
    assert parse_google_chart(mutate_chart(mutator), chart).quality == "invalid"


def test_chart_overflow_is_invalid():
    chart = Chart(
        "vn",
        provider="google",
        platform="android",
        genre="GAME_CASUAL",
        depth=10,
        feed_type="top-free",
    )
    assert parse_google_chart(mutate_chart(lambda apps: apps), chart).quality == "invalid"


def test_wrong_chart_category_is_invalid():
    chart = Chart(
        "vn", provider="google", platform="android", genre="GAME_ACTION", feed_type="top-free"
    )
    assert parse_google_chart(mutate_chart(lambda apps: apps), chart).quality == "invalid"


def test_metadata_wrong_canonical_package_is_partial():
    details = [["Game"]] + [None] * 12 + [["10,000+", 10000]]
    body = (
        '<link rel="canonical" href="https://play.google.com/store/apps/details?id=com.other">'
        + "AF_initDataCallback({key: 'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    metadata = parse_google_metadata(body, "com.expected")
    assert metadata["status"] == "partial"
    assert metadata["min_installs"] is None


def test_malformed_numeric_metadata_is_partial_not_exception():
    details = (
        [["Game"]] + [None] * 12 + [["unknown", None]] + [None] * 37 + [[None, "not a rating"]]
    )
    body = (
        "AF_initDataCallback({key: 'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    assert parse_google_metadata(body, "com.expected")["status"] == "partial"


def test_missing_required_metadata_fields_marks_partial():
    details = [["Game"]] + [None] * 12 + [["10,000+", 10000]]
    body = (
        "AF_initDataCallback({key: 'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    meta = parse_google_metadata(body, "com.game")
    assert meta["status"] == "partial"
    assert meta["genres"] == []


def rpc_body(apps):
    container = [None] * 29
    container[28] = [apps]
    inner = [[None, [[container][0]]]]
    return json.dumps([["wrb.fr", "vyAe2", json.dumps(inner)]]).encode()


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"[]",
        b"123\nnull\n[]",
        b'[["wrb.fr","vyAe2","not json"]]',
        b'[["wrb.fr","vyAe2","[]"]]',
    ],
)
def test_missing_or_corrupt_rpc_is_invalid(body):
    chart = Chart("vn", provider="google", platform="android", genre="GAME_CASUAL")
    assert parse_google_chart(body, chart).quality == "invalid"


@pytest.mark.parametrize(
    "apps",
    [
        [None, []],
        [[[None]]],
        [[["bad package"]]],
        [[["com.direct", None, None, "Direct"]]],
        [[[[None], ["com.fallback"], None, "Fallback"]]],
        [[[[], None, None, "No package"]]],
    ],
)
def test_rpc_entry_shapes_have_explicit_quality(apps):
    chart = Chart("vn", provider="google", platform="android", genre="GAME_CASUAL")
    result = parse_google_chart(rpc_body(apps), chart)
    if result.entries:
        assert result.quality == "partial"
        assert result.entries[0].rank == 1
    else:
        assert result.quality == "invalid"


@pytest.mark.parametrize(
    "body",
    [
        b"AF_initDataCallback({key: 'ds:5', data: broken, sideChannel: {}});",
        b"AF_initDataCallback({key: 'other', data: [], sideChannel: {}});",
        b"<link rel='canonical' href='https://play.google.com/store/apps/details'>",
    ],
)
def test_malformed_metadata_callbacks_stay_partial(body):
    assert parse_google_metadata(body, "com.game")["status"] == "partial"


@pytest.mark.parametrize(
    "text,expected", [("", None), ("1.000.000+", 1000000), ("5.5M+", 5500000), (" 10+ ", 10)]
)
def test_install_display_additional_formats(text, expected):
    assert minimum_from_ascii_display(text) == expected


@pytest.mark.parametrize(
    "rating,count", [("bad", None), (9, -3), (True, True), (float("nan"), 2.5), (0, 0)]
)
def test_numeric_metadata_avoids_invalid_coercions(rating, count):
    details = [None] * 96
    details[0] = ["Game"]
    details[13] = ["unknown"]
    details[51] = [None, rating, None, count]
    details[48] = []
    details[19] = [False]
    body = (
        "AF_initDataCallback({key:'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    meta = parse_google_metadata(body, "com.game")
    assert meta["status"] == "partial"
    assert meta["has_ads"] is False and meta["has_iap"] is False
    assert meta["min_installs"] is None


@pytest.mark.parametrize("installs", [[], [None]])
def test_absent_install_display_remains_unknown(installs):
    details = [None] * 96
    details[0] = ["Game"]
    details[13] = installs
    body = (
        "AF_initDataCallback({key:'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    meta = parse_google_metadata(body, "com.game")
    assert meta["installs"] is None and meta["min_installs"] is None


def test_paid_direct_fields_and_nested_icon():
    details = [None] * 96
    details[0] = ["Paid Game"]
    details[13] = ["10+", 10]
    details[57] = [[[[[None, [[2500000, "USD"]]]]]]]
    details[95] = [["not an icon", [["https://example.com/icon"]]]]
    body = (
        "AF_initDataCallback({key:'ds:5', data:"
        + json.dumps([None, [None, None, details]])
        + ", sideChannel: {}});"
    ).encode()
    meta = parse_google_metadata(body, "com.game")
    assert meta["price"] == 2.5 and meta["currency"] == "USD"
    assert meta["icon_url"] == "https://example.com/icon"


def test_malformed_middle_entry_does_not_fabricate_compact_ranking():
    chart = Chart("vn", provider="google", platform="android", genre="GAME_CASUAL")
    body = rpc_body(
        [[["com.first", None, None, "First"]], [], [["com.third", None, None, "Third"]]]
    )
    result = parse_google_chart(body, chart)
    assert result.quality == "invalid" and not result.entries


def test_numeric_package_segment_rejected_consistently_with_storage():
    chart = Chart("vn", provider="google", platform="android", genre="GAME_CASUAL")
    result = parse_google_chart(rpc_body([[["com.123", None, None, "Wrong"]]]), chart)
    assert result.quality == "invalid" and not result.entries
