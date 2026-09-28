from datetime import UTC, datetime, timedelta

from casual_scout.android.storage import AndroidStore
from casual_scout.collection.jobs import JobService
from casual_scout.storage import Repository


def store_at(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    store = AndroidStore(repo)
    store.initialize()
    return repo, store


def test_android_queue_deduplicates_but_allows_another_manual_run(tmp_path):
    _repo, store = store_at(tmp_path)
    first = store.enqueue()
    assert store.enqueue() == first
    assert store.dispatch() == first
    store.finish(first, "failed", "fixture")
    assert store.enqueue() != first


def test_android_waits_for_ios_before_creating_core_run(tmp_path):
    repo, store = store_at(tmp_path)
    ios = JobService(repo).submit("manual", ["vn"], "ios-test")
    android = store.enqueue()
    assert store.dispatch() is None
    assert store.view(android)["job"]["status"] == "pending"
    JobService(repo).finish(ios, "succeeded")
    assert store.dispatch() == android


def test_committed_batch_visible_from_another_connection_with_unknown_baseline(tmp_path):
    _repo, store = store_at(tmp_path)
    run = store.enqueue()
    store.dispatch()
    store.save_chart(
        run,
        "top-free",
        [
            {"package": "com.example.one", "rank": 1, "name": "One"},
            {"package": "com.example.two", "rank": 2, "name": "Two"},
        ],
        "evidence.html",
    )
    store.save_batch(
        run,
        [
            {
                "package": "com.example.one",
                "developer": "Studio",
                "description": "Match 3 puzzle",
                "metadata_status": "complete",
            }
        ],
    )
    independent = AndroidStore(Repository(tmp_path)).view(run)
    assert independent["job"]["processed"] == 1
    assert independent["job"]["batches"] == 1
    assert independent["job"]["status"] == "queued"
    assert independent["entries"][0]["developer"] == "Studio"
    assert independent["entries"][0]["delta_free_1d"] is None
    assert independent["entries"][1]["metadata_status"] == "pending"


def test_google_play_category_controls_casual_classification_and_subgenre(tmp_path):
    _repo, store = store_at(tmp_path)
    job = store.enqueue()
    store.dispatch()
    store.save_chart(
        job,
        "top-free",
        [
            {"package": "com.example.casual", "rank": 1, "name": "Casual"},
            {"package": "com.example.other", "rank": 2, "name": "Other"},
            {"package": "com.example.unknown", "rank": 3, "name": "Unknown"},
        ],
        "fixture.html",
    )

    store.save_batch(
        job,
        [
            {
                "package": "com.example.casual",
                "metadata_status": "complete",
                "application_category": "GAME_CASUAL",
                "google_play_genres": [{"label": "Mô phỏng", "code": "GAME_SIMULATION"}],
                "developer": "Example Studio",
                "description": "A simulation game",
            },
            {
                "package": "com.example.other",
                "metadata_status": "complete",
                "application_category": "GAME_ACTION",
                "google_play_genres": [{"label": "Hành động", "code": "GAME_ACTION"}],
            },
            {"package": "com.example.unknown", "metadata_status": "complete"},
        ],
    )

    rows = {entry["package"]: entry for entry in store.view(job)["entries"]}
    assert rows["com.example.casual"]["casual_status"] == "casual"
    assert rows["com.example.casual"]["subgenre"] == "Simulation"
    assert rows["com.example.casual"]["developer"] == "Example Studio"
    assert rows["com.example.other"]["casual_status"] == "not_casual"
    assert rows["com.example.other"]["subgenre"] == "Action"
    assert rows["com.example.unknown"]["casual_status"] == "unknown"


def test_schedule_only_claims_seven_am_once_and_preserves_pending(tmp_path):
    _repo, store = store_at(tmp_path)
    store.set_schedule(True)
    assert store.enqueue_daily(datetime(2026, 9, 25, 0, 1, tzinfo=UTC)) is None
    first = store.enqueue_daily(datetime(2026, 9, 26, 0, 0, tzinfo=UTC))
    assert first
    assert store.enqueue_daily(datetime(2026, 9, 26, 0, 0, 30, tzinfo=UTC)) is None
    assert AndroidStore(Repository(tmp_path)).view(first)["job"]["status"] == "pending"


def test_delta_uses_chart_observation_day_not_queue_day(tmp_path):
    _repo, store = store_at(tmp_path)
    old = store.enqueue(local_date="2026-09-20")
    store.dispatch()
    store.save_chart(
        old,
        "top-free",
        [
            {"package": "com.example.other", "rank": 1, "name": "Other"},
            {"package": "com.example.one", "rank": 2, "name": "One"},
        ],
        "fixture",
        observed_at=datetime(2026, 9, 23, 18, 0, tzinfo=UTC),
    )
    store.finish(old, "succeeded")
    current = store.enqueue(local_date="2026-09-24")
    store.dispatch()
    store.save_chart(
        current,
        "top-free",
        [{"package": "com.example.one", "rank": 1, "name": "One"}],
        "fixture",
        observed_at=datetime(2026, 9, 24, 18, 0, tzinfo=UTC),
    )
    assert store.view(current)["entries"][0]["delta_free_1d"] == 1


def test_ios_schedule_race_does_not_launch_android_or_consume_ios_schedule(tmp_path, monkeypatch):
    from casual_scout.operations.daily_scheduler import DailyScheduler

    repo, store = store_at(tmp_path)
    due = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
    repo.schedule_one_time_collection(due, "2026-09-24T15:00")
    android = store.enqueue()
    launched = []
    scheduler = DailyScheduler(repo, lambda rid, _: launched.append(rid), now=lambda: due)

    def racing_check():
        store.dispatch()
        return False

    monkeypatch.setattr(scheduler, "_has_active_run", racing_check)
    scheduler.check_once()
    assert launched == []
    assert repo.get_one_time_collection()["status"] == "pending"
    assert store.view(android)["job"]["status"] == "queued"


def test_cache_reuses_only_recent_metadata_and_never_old_ranks(tmp_path):
    _repo, store = store_at(tmp_path)
    job = store.enqueue()
    store.dispatch()
    store.save_chart(
        job, "top-free", [{"package": "com.example.one", "rank": 1, "name": "One"}], "fixture"
    )
    store.save_batch(
        job,
        [
            {
                "package": "com.example.one",
                "developer": "Studio",
                "metadata_status": "complete",
                "fetched_at": datetime.now(UTC).isoformat(),
                "application_category": "GAME_CASUAL",
                "google_play_genres": [{"label": "Puzzle", "code": "GAME_PUZZLE"}],
            }
        ],
    )
    cached = store.cached_metadata("com.example.one")
    assert cached["developer"] == "Studio"
    assert cached["metadata_status"] == "cached"
    assert "free_rank" not in cached
    store.save_batch(
        job,
        [
            {
                "package": "com.example.one",
                "metadata_status": "complete",
                "fetched_at": (datetime.now(UTC) - timedelta(hours=49)).isoformat(),
            }
        ],
    )
    assert store.cached_metadata("com.example.one") is None


def test_dead_worker_recovery_preserves_committed_batch(tmp_path, monkeypatch):
    from casual_scout.android.coordinator import recover_android

    repo, store = store_at(tmp_path)
    job = store.enqueue()
    store.dispatch()
    store.started(job, 123, 1.0)
    store.save_chart(
        job, "top-free", [{"package": "com.example.one", "rank": 1, "name": "One"}], "fixture"
    )
    store.save_batch(
        job, [{"package": "com.example.one", "metadata_status": "complete", "developer": "Studio"}]
    )
    monkeypatch.setattr("casual_scout.android.coordinator._is_process_alive", lambda *_: False)
    recover_android(store)
    assert store.view(job)["job"]["status"] == "interrupted"
    assert store.view(job)["entries"][0]["developer"] == "Studio"
    with repo._connect() as connection:
        assert (
            connection.execute("SELECT status FROM runs WHERE id=?", (job,)).fetchone()[0]
            == "interrupted"
        )


def test_launcher_failure_does_not_leave_queue_blocked(tmp_path):
    from casual_scout.android.coordinator import dispatch_pending

    _repo, store = store_at(tmp_path)
    job = store.enqueue()

    def broken_launcher(*_):
        raise OSError("fixture cannot launch")

    dispatch_pending(store, broken_launcher)
    assert store.view(job)["job"]["status"] == "failed"
    assert store.enqueue() != job


def test_daily_ios_race_leaves_claim_unconsumed(tmp_path, monkeypatch):
    from casual_scout.operations.daily_scheduler import DailyScheduler

    repo, store = store_at(tmp_path)
    repo.set_daily_schedule_enabled(True)
    store.enqueue()
    launched = []
    scheduler = DailyScheduler(
        repo,
        lambda rid, _: launched.append(rid),
        now=lambda: datetime(2026, 9, 24, 0, 0, tzinfo=UTC),
    )

    def racing_check():
        store.dispatch()
        return False

    monkeypatch.setattr(scheduler, "_has_active_run", racing_check)
    scheduler.check_once()
    assert launched == []
    assert repo.get_daily_schedule()["last_triggered_local_date"] is None
