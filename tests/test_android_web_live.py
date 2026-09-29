from fastapi.testclient import TestClient

from casual_scout.android.storage import AndroidStore
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


def test_android_web_csrf_and_batch_api_while_run_active(tmp_path):
    app = create_app(Settings(tmp_path), android_launcher=lambda *_: None)
    client = TestClient(app)
    page = client.get("/android")
    assert page.status_code == 200
    assert client.post("/api/android/runs").status_code == 403
    headers = {"Origin": "http://testserver", "X-CSRF-Token": client.cookies["csrftoken"]}
    first = client.post("/api/android/runs", headers=headers)
    assert first.status_code == 202
    job_id = first.json()["job_id"]
    assert client.post("/api/android/runs", headers=headers).json()["job_id"] == job_id
    store = AndroidStore(Repository(tmp_path))
    with store.repo._connect() as db:
        assert db.execute("SELECT count(*) FROM market_runs WHERE run_id=?", (job_id,)).fetchone()[0] == 18
        assert db.execute("SELECT count(*) FROM android_jobs").fetchone()[0] == 0
    assert client.get("/api/android/data?job_id=missing").status_code == 404
    assert (
        client.patch("/api/android/schedule", headers=headers, json={"enabled": "yes"}).status_code
        == 422
    )
    assert (
        client.patch("/api/android/schedule", headers=headers, json={"enabled": True}).json()[
            "enabled"
        ]
        is True
    )


def test_android_page_exposes_progressive_results_and_announced_batch_count(tmp_path):
    app = create_app(Settings(tmp_path), android_launcher=lambda *_: None)
    store = AndroidStore(Repository(tmp_path))
    archived_id = store.enqueue()
    response = TestClient(app).get("/android", params={"job_id": archived_id})

    assert response.status_code == 200
    assert 'id="android-crawl"' in response.text
    assert 'id="android-progress"' in response.text
    assert 'id="android-count" role="status"' in response.text
    assert 'id="android-results" class="android-grid" role="region"' in response.text
    assert response.text.index('id="android-results"') < response.text.index('id="android-empty"')


def test_android_does_not_replace_ios_one_time_scheduler(tmp_path):
    from datetime import UTC, datetime

    from casual_scout.android.coordinator import AndroidCoordinator

    repo = Repository(tmp_path)
    repo.initialize()
    store = AndroidStore(repo)
    store.initialize()
    due = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
    repo.schedule_one_time_collection(due, "2026-09-24T15:00")
    launched = []
    scheduler = AndroidCoordinator(repo, lambda rid, _: launched.append(rid), now=lambda: due)
    scheduler.check_once()
    assert launched == [repo.get_one_time_collection()["run_id"]]
    assert store.view()["job"] is None


def test_explicit_lan_host_allows_mobile_page_and_same_origin_csrf(tmp_path, monkeypatch):
    monkeypatch.setenv("CASUAL_SCOUT_LAN_HOSTS", "192.168.1.4")
    app = create_app(Settings(tmp_path), android_launcher=lambda *_: None)
    client = TestClient(app, base_url="http://192.168.1.4:8002")
    assert client.get("/android").status_code == 200
    headers = {"Origin": "http://192.168.1.4:8002", "X-CSRF-Token": client.cookies["csrftoken"]}
    assert (
        client.patch("/api/android/schedule", headers=headers, json={"enabled": False}).status_code
        == 200
    )
    headers["Origin"] = "http://192.168.1.55:8002"
    assert (
        client.patch("/api/android/schedule", headers=headers, json={"enabled": True}).status_code
        == 403
    )
