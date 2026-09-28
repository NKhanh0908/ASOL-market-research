import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from casual_scout.config import Settings
from casual_scout.models import Chart, HttpResult
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


@pytest.fixture
def launcher_calls() -> list[tuple[str, Path]]:
    return []


@pytest.fixture
def fake_launcher(launcher_calls: list[tuple[str, Path]]) -> Callable[[str, Path], int]:
    def _launcher(run_id: str, data_dir: Path) -> int:
        launcher_calls.append((run_id, data_dir))
        return 12345

    return _launcher


@pytest.fixture
def web_setup(
    tmp_path: Path,
    fake_launcher: Callable[[str, Path], int],
    launcher_calls: list[tuple[str, Path]],
):
    settings = Settings(tmp_path)
    repo = Repository(tmp_path)
    repo.initialize()
    app = create_app(settings, launcher=fake_launcher)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    return repo, client, fake_launcher, launcher_calls


def test_get_root_empty_state(web_setup):
    _repo, client, _launcher, _calls = web_setup
    response = client.get("/")
    assert response.status_code == 200
    assert "Casual theo Apple" in response.text
    assert "Không có số lượt tải" in response.text


def test_post_runs_with_csrf_redirects_and_launches(web_setup):
    _repo, client, _launcher, calls = web_setup
    # GET / to obtain session cookie and csrf token
    get_res = client.get("/")
    assert get_res.status_code == 200

    # Extract csrf token from form or cookie
    csrf_token = client.cookies.get("csrftoken") or ""
    # Look for csrf_token input in html
    import re
    match = re.search(r'name="csrf_token" value="([^"]+)"', get_res.text)
    if match:
        csrf_token = match.group(1)

    post_res = client.post(
        "/runs",
        headers={"Origin": "http://127.0.0.1:8000"},
        data={
            "country": "vn",
            "request_key": "req-web-1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert post_res.status_code == 303
    assert "/runs/" in post_res.headers["location"]
    assert len(calls) == 1


def test_schedule_api_persists_enabled_state_and_manages_scheduler_lifecycle(
    tmp_path: Path,
    fake_launcher: Callable[[str, Path], int],
):
    lifecycle: list[str] = []

    class FakeScheduler:
        def start(self) -> None:
            lifecycle.append("start")

        def stop(self) -> None:
            lifecycle.append("stop")

    settings = Settings(tmp_path)
    app = create_app(
        settings,
        launcher=fake_launcher,
        scheduler_factory=lambda _repo, _launcher: FakeScheduler(),
    )

    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert lifecycle == ["start"]
        client.get("/")
        csrf_token = client.cookies.get("csrftoken") or ""

        schedule = client.get("/api/schedule")
        assert schedule.status_code == 200
        assert schedule.json()["enabled"] is False

        updated = client.patch(
            "/api/schedule",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "X-CSRF-Token": csrf_token,
            },
            json={"enabled": True},
        )
        assert updated.status_code == 200
        assert updated.json()["enabled"] is True

    assert lifecycle == ["start", "stop"]


def test_one_time_schedule_api_persists_future_ios_collection(web_setup):
    _repo, client, _launcher, _calls = web_setup
    client.get("/data")
    csrf_token = client.cookies.get("csrftoken") or ""
    scheduled_for = (datetime.now(UTC) + timedelta(hours=1)).astimezone().replace(
        second=0, microsecond=0
    )

    created = client.post(
        "/api/one-time-schedule",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "X-CSRF-Token": csrf_token,
        },
        json={"scheduled_for": scheduled_for.isoformat(timespec="minutes")},
    )

    assert created.status_code == 200
    assert created.json()["status"] == "pending"
    assert client.get("/api/one-time-schedule").json()["status"] == "pending"


def test_data_page_shows_one_time_ios_schedule_controls(web_setup):
    _repo, client, _launcher, _calls = web_setup

    response = client.get("/data")

    assert response.status_code == 200
    assert 'id="one-time-schedule-at"' in response.text
    assert "Đặt lịch crawl iOS một lần" in response.text
    assert 'href="/android"' in response.text
    assert "/api/one-time-schedule" in response.text


def test_dashboard_shows_daily_group_collection_controls(web_setup):
    _repo, client, _launcher, _calls = web_setup

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Thu thập iOS · 9 thị trường" in response.text
    assert "Crawl ngay" in response.text
    assert "07:00" in response.text


def test_runs_list_and_detail(web_setup):
    repo, client, _launcher, _calls = web_setup
    from casual_scout.collection.jobs import JobService

    jobs = JobService(repo)
    run_id = jobs.submit("manual", ["vn"], "req-test-view")

    runs_res = client.get("/runs")
    assert runs_res.status_code == 200
    assert run_id in runs_res.text

    run_res = client.get(f"/runs/{run_id}")
    assert run_res.status_code == 200
    assert "Vietnam" in run_res.text

    status_res = client.get(f"/runs/{run_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "queued"


def test_game_detail_escapes_script_tags(web_setup, evidence_dir: Path):
    repo, client, _launcher, _calls = web_setup
    from casual_scout.collection.jobs import JobService
    from casual_scout.providers.apple import parse_chart

    jobs = JobService(repo)
    run_id = jobs.submit("manual", ["vn"], "req-game-view")
    now = datetime.now(UTC)

    body = (evidence_dir / "vn-casual-100.json").read_bytes()
    parsed = parse_chart(body, Chart("vn"))
    http_res = HttpResult(
        url="https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json",
        started_at=now,
        elapsed_ms=50,
        status=200,
        body=body,
        headers={"content-type": "application/json"},
        error=None,
    )
    snapshot_id = repo.save_snapshot(run_id, http_res, parsed)

    # Save metadata with malicious <script> tag
    app_id = parsed.entries[0].app_id
    malicious_meta = {
        app_id: {
            "trackName": "<script>alert('xss')</script>",
            "artistName": "Evil Dev",
            "primaryGenreName": "Casual",
            "genres": [{"genreId": "7003", "name": "Casual"}],
            "description": "<script>alert('pwned')</script>",
            "averageUserRating": 5.0,
            "userRatingCount": 10,
            "trackViewUrl": "https://apps.apple.com/vn/app/id123",
            "price": 0.0,
            "currency": "VND",
        }
    }
    lookup_res = HttpResult(
        url=f"https://itunes.apple.com/lookup?country=vn&id={app_id}",
        started_at=now,
        elapsed_ms=50,
        status=200,
        body=b'{"resultCount": 1}',
        headers={"content-type": "application/json"},
        error=None,
    )
    versions = repo.save_metadata("vn", malicious_meta, lookup_res)
    repo.bind_metadata(snapshot_id, versions)

    game_res = client.get(f"/games/{app_id}?country=vn&snapshot_id={snapshot_id}")
    assert game_res.status_code == 200
    assert 'class="page-heading"' in game_res.text
    assert 'href="/data"' in game_res.text
    assert "<script>alert" not in game_res.text
    assert "&lt;script&gt;alert" in game_res.text


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/", "/data", "/android", "/shortlist", "/runs"],
)
def test_primary_pages_keep_existing_routes_and_navigation_targets(web_setup, path):
    _repo, client, _launcher, _calls = web_setup

    response = client.get(path)

    assert response.status_code == 200
    for destination in ("/dashboard", "/data", "/android", "/shortlist", "/runs"):
        assert f'href="{destination}"' in response.text


def test_shared_navigation_uses_galaxy_labels_and_semantic_active_state(web_setup):
    _repo, client, _launcher, _calls = web_setup

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert re.search(r'<nav(?=[^>]*aria-label="Điều hướng chính")[^>]*>', response.text)
    for label in ("Tổng quan", "iOS", "Android", "Shortlist", "Lịch sử"):
        assert label in response.text
    assert re.search(
        r'<a(?=[^>]*href="/dashboard")(?=[^>]*aria-current="page")[^>]*>',
        response.text,
    )


@pytest.mark.parametrize("page", ["/dashboard", "/data", "/android", "/shortlist", "/runs"])
def test_pages_load_content_versioned_static_assets(web_setup, page):
    _repo, client, _launcher, _calls = web_setup
    html = client.get(page).text
    asset_urls = re.findall(r'(?:href|src)="(/static/[^" ]+)"', html)
    assert len(asset_urls) == (3 if page == "/android" else 1)
    for url in asset_urls:
        asset = client.get(url)
        assert asset.status_code == 200
        expected_version = sha256(asset.content).hexdigest()[:12]
        assert url.endswith(f"?v={expected_version}")
    stylesheet = client.get(asset_urls[0]).text
    assert "--color-space:" in stylesheet
    assert ".nav-link svg" in stylesheet


def test_stylesheet_url_changes_when_css_changes_without_server_restart(web_setup, monkeypatch):
    _repo, client, _launcher, _calls = web_setup

    def stylesheet_url():
        return re.search(r'href="(/static/app\.css[^" ]*)"', client.get("/data").text)[1]

    previous_url = stylesheet_url()
    read_bytes = Path.read_bytes

    def changed_css(path):
        content = read_bytes(path)
        return content + b"\n/* new stylesheet revision */" if path.name == "app.css" else content

    monkeypatch.setattr(Path, "read_bytes", changed_css)
    assert stylesheet_url() != previous_url


def test_header_icons_have_intrinsic_dimensions_when_stylesheet_is_unavailable(web_setup):
    _repo, client, _launcher, _calls = web_setup
    header = re.search(r"<header\b.*?</header>", client.get("/data").text, re.DOTALL)[0]
    icons = re.findall(r"<svg\b[^>]*>", header)
    assert len(icons) == 6
    for icon in icons:
        for dimension in ("width", "height"):
            value = re.search(rf'{dimension}="(\d+)"', icon)
            assert value is not None
            assert 0 < int(value[1]) <= 32


def test_dashboard_and_ios_data_distinguish_saved_dates_from_future_collection(web_setup):
    _repo, client, _launcher, _calls = web_setup

    dashboard = client.get("/dashboard")
    data = client.get("/data")

    assert dashboard.status_code == data.status_code == 200
    assert "Ngày dữ liệu" in dashboard.text
    assert "Dữ liệu đã lưu" in dashboard.text
    assert "Bản chụp đã lưu" in data.text
    assert "Lên lịch crawl" in data.text
    assert "Thời điểm chạy" in data.text
    assert "Top Free Casual · cùng 9 thị trường" in data.text
    assert 'action="/runs"' in data.text
    assert 'id="one-time-schedule-at"' in data.text
    assert "/api/one-time-schedule" in data.text


def test_shortlist_and_run_pages_keep_primary_actions_and_page_hierarchy(web_setup):
    repo, client, _launcher, _calls = web_setup
    from casual_scout.collection.jobs import JobService

    run_id = JobService(repo).submit("manual", ["vn"], "req-ui-history")
    shortlist = client.get("/shortlist")
    runs = client.get("/runs")
    run_detail = client.get(f"/runs/{run_id}")

    assert shortlist.status_code == runs.status_code == run_detail.status_code == 200
    assert 'class="page-heading"' in shortlist.text
    assert "/api/export/shortlist?format=csv" in shortlist.text
    assert "/api/export/shortlist?format=json" in shortlist.text
    assert f'href="/runs/{run_id}"' in runs.text
    assert 'class="page-heading"' in runs.text
    assert 'class="page-heading"' in run_detail.text
    assert "/runs/${runId}/status" in run_detail.text
