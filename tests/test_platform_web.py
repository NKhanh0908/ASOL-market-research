from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from casual_scout.config import Settings
from casual_scout.models import Chart, Entry, HttpResult, ParsedChart
from casual_scout.storage import Repository
from casual_scout.web.app import create_app
from casual_scout.web.presentation import app_store_url, platform_url
from casual_scout.web.views import get_dashboard_view, get_data_view, get_game_view


class NoopScheduler:
    def start(self):
        pass

    def stop(self):
        pass


def seed_snapshot(
    repo, day, platform="android", feed="top-free", package="com.example.game", enrich=True
):
    stamp = datetime.fromisoformat(day).replace(tzinfo=UTC)
    run_id = f"{platform}-{feed}-{day}"
    with repo._write_connection() as db:
        db.execute(
            'INSERT INTO runs(id,request_key,"trigger",status,started_at) '
            "VALUES(?,?,'manual','running',?)",
            (run_id, run_id, stamp.isoformat()),
        )
    android = platform == "android"
    chart = Chart(
        "vn",
        provider="google" if android else "apple",
        platform=platform,
        genre="GAME_CASUAL" if android else "7003",
        feed_type=feed,
    )
    entry = Entry(package, 1, "<script>Game</script>", "javascript:alert(1)", None, "Studio", [])
    response = HttpResult("https://play.google.com/fixture", stamp, 1, 200, day.encode(), {}, None)
    snapshot = repo.save_snapshot(run_id, response, ParsedChart(chart, [entry], None, "partial"))
    if not enrich:
        with repo._write_connection() as db:
            db.execute("UPDATE runs SET status='partial' WHERE id=?", (run_id,))
        return snapshot
    meta = {
        "name": "Game",
        "trackName": "Game",
        "description": "merge puzzle",
        "status": "complete",
        "installs": "1M+",
        "min_installs": 1000000,
        "average_rating": 4.5,
        "rating_count": 20,
    }
    versions = repo.save_metadata(
        "vn", {package: meta}, response, provider=chart.provider, platform=platform
    )
    repo.bind_metadata(snapshot, versions)
    with repo._write_connection() as db:
        db.execute("UPDATE runs SET status='partial' WHERE id=?", (run_id,))
    return snapshot


@pytest.fixture
def repo(tmp_path):
    result = Repository(tmp_path)
    result.initialize()
    return result


def test_date_filter_uses_requested_snapshot(repo):
    older = seed_snapshot(repo, "2026-09-27")
    seed_snapshot(repo, "2026-09-28")
    view = get_data_view(repo, platform="android", date="2026-09-27")
    assert view["selected_snapshot"]["id"] == older


def test_supplied_snapshot_cannot_cross_platform(repo):
    ios = seed_snapshot(repo, "2026-09-27", platform="ios", package="123")
    with pytest.raises((KeyError, ValueError)):
        get_data_view(repo, platform="android", snapshot_id=ios)


def test_unknown_game_returns_none(repo):
    assert get_game_view(repo, "com.example.missing", platform="android") is None


def test_game_does_not_fallback_to_another_country_or_snapshot(repo):
    seed_snapshot(repo, "2026-09-28")
    assert get_game_view(repo, "com.example.game", country="us", platform="android") is None
    other = seed_snapshot(repo, "2026-09-27", package="com.example.other")
    assert get_game_view(repo, "com.example.game", snapshot_id=other, platform="android") is None
    response = HttpResult(
        "https://play.google.com/fixture",
        datetime(2026, 9, 29, tzinfo=UTC),
        1,
        200,
        b"new",
        {},
        None,
    )
    repo.save_metadata(
        "vn",
        {
            "com.example.game": {
                "name": "Unbound future",
                "status": "complete",
                "installs": "50M+",
                "min_installs": 50000000,
            }
        },
        response,
        provider="google",
        platform="android",
    )
    game = get_game_view(repo, "com.example.game", platform="android")
    assert game["metadata"]["min_installs"] == 1000000


def test_game_without_analytics_keeps_bound_metadata_and_calendar(repo):
    snapshot = seed_snapshot(repo, "2026-09-28")
    game = get_game_view(repo, "com.example.game", platform="android", snapshot_id=snapshot)
    assert game["metadata"]["min_installs"] == 1000000
    assert len(game["chart_history"]) == 14
    assert game["chart_history"][-1]["date"] == "2026-09-28"


def test_store_url_cannot_execute_script():
    assert app_store_url("javascript:alert(1)", "com.example.game", "android").startswith(
        "https://play.google.com/"
    )
    assert app_store_url("https://evil.example/app", "123", "ios").startswith(
        "https://apps.apple.com/"
    )


def test_switch_keeps_filters_removes_snapshot():
    url = platform_url(
        "/data", {"country": "vn", "date": "2026-09-28", "snapshot_id": "old"}, "android"
    )
    assert "date=2026-09-28" in url and "snapshot_id" not in url


def test_android_radar_scores_and_preserves_analysis_signal(repo):
    repo.save_daily_analytics(
        [
            {
                "date": "2026-09-28",
                "country": "vn",
                "platform": "android",
                "app_id": "com.example.game",
                "current_rank": 4,
                "signal": "FAST_RISER",
                "delta_1d": 30,
                "signal_reasons": [],
                "mechanic": "Merge",
                "cross_markets": ["vn"],
                "cross_market_count": 1,
            }
        ]
    )
    view = get_dashboard_view(repo, date_str="2026-09-28", country="vn", platform="android")
    row = view["radar_items"][0]
    assert row["opportunity_score"] > 0
    assert row["signal"] == "FAST_RISER"


def test_historical_dashboard_uses_snapshot_bound_identity(repo):
    seed_snapshot(repo, "2026-09-28")
    response = HttpResult(
        "https://play.google.com/fixture",
        datetime(2026, 9, 29, tzinfo=UTC),
        1,
        200,
        b"future",
        {},
        None,
    )
    repo.save_metadata(
        "vn",
        {"com.example.game": {"name": "Future name", "status": "complete"}},
        response,
        provider="google",
        platform="android",
    )
    repo.save_daily_analytics(
        [
            {
                "date": "2026-09-28",
                "country": "vn",
                "platform": "android",
                "app_id": "com.example.game",
                "current_rank": 1,
                "free_rank": 1,
                "signal": "STEADY",
                "signal_reasons": [],
                "mechanic": "Merge",
                "cross_markets": ["vn"],
                "cross_market_count": 1,
            }
        ]
    )
    view = get_dashboard_view(repo, date_str="2026-09-28", country="vn", platform="android")
    assert view["radar_items"][0]["title"] == "Game"


def test_run_snapshot_link_preserves_platform_and_feed(repo):
    import re
    from html import unescape

    seed_snapshot(repo, "2026-09-28", feed="top-grossing")
    client = TestClient(
        create_app(Settings(repo.data_dir), scheduler_factory=lambda *_: NoopScheduler())
    )
    page = client.get("/runs/android-top-grossing-2026-09-28")
    link = unescape(re.search(r'href="(/data\?[^\"]+snapshot_id=[^\"]+)"', page.text).group(1))
    assert "platform=android" in link and "feed_type=top-grossing" in link
    assert client.get(link).status_code == 200


def test_unbound_game_and_grossing_navigation_export(repo):
    import re
    from html import unescape

    snapshot = seed_snapshot(repo, "2026-09-28", feed="top-grossing", enrich=False)
    client = TestClient(
        create_app(Settings(repo.data_dir), scheduler_factory=lambda *_: NoopScheduler())
    )
    game = client.get(f"/games/com.example.game?platform=android&snapshot_id={snapshot}")
    assert game.status_code == 200
    assert "Chưa có dữ liệu" in game.text and "UNKNOWN" in game.text
    link = unescape(re.search(r'href="(/data\?country=[^\"]+)"', game.text).group(1))
    assert "feed_type=top-grossing" in link and client.get(link).status_code == 200
    download = client.get(
        f"/export/csv?platform=android&feed_type=top-grossing&snapshot_id={snapshot}"
    )
    assert download.status_code == 200 and "com.example.game" in download.text
    assert client.get(f"/export/csv?platform=ios&snapshot_id={snapshot}").status_code == 404


def test_historical_game_analytics_do_not_use_future_day(repo):
    snapshot = seed_snapshot(repo, "2026-09-27")
    seed_snapshot(repo, "2026-09-28")
    for day, mechanic in [("2026-09-27", "Merge"), ("2026-09-28", "Runner")]:
        repo.save_daily_analytics(
            [
                {
                    "date": day,
                    "country": "vn",
                    "platform": "android",
                    "app_id": "com.example.game",
                    "current_rank": 1,
                    "free_rank": 1,
                    "signal": "STEADY",
                    "signal_reasons": [],
                    "mechanic": mechanic,
                    "cross_markets": ["vn"],
                    "cross_market_count": 1,
                }
            ]
        )
    game = get_game_view(repo, "com.example.game", platform="android", snapshot_id=snapshot)
    assert game["analytics"]["mechanic"] == "Merge"
    assert all(row["date"] <= "2026-09-27" for row in game["rank_history"])


def test_android_ui_schedule_and_archived_features(repo):
    seed_snapshot(repo, "2026-09-28")
    app = create_app(Settings(repo.data_dir), scheduler_factory=lambda *_: NoopScheduler())
    client = TestClient(app)
    dashboard = client.get("/dashboard?platform=android")
    assert dashboard.status_code == 200
    assert "/api/android/schedule" in dashboard.text
    assert 'aria-current="page"' in dashboard.text
    assert "Lưu vào Shortlist" not in dashboard.text
    data = client.get("/data?platform=android")
    assert data.status_code == 200
    assert 'id="one-time-schedule-form"' not in data.text
    assert "&lt;script&gt;Game&lt;/script&gt;" in data.text
    game = client.get("/games/com.example.game?platform=android")
    assert game.status_code == 200
    assert "Google Play" in game.text and "javascript:alert" not in game.text
