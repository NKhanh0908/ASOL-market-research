from collections.abc import Callable
from datetime import UTC, datetime
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
    assert "<script>alert" not in game_res.text
    assert "&lt;script&gt;alert" in game_res.text
