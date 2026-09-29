from datetime import UTC, datetime

from casual_scout.android.collector import AndroidCollector
from casual_scout.collection.jobs import JobService
from casual_scout.models import Entry, HttpResult, ParsedChart
from casual_scout.storage import Repository


class Fake:
    def __init__(self, fail_chart=False, fail_metadata=False):
        self.fail_chart, self.fail_metadata = fail_chart, fail_metadata
        self.calls = []

    def fetch_chart(self, chart):
        if self.fail_chart and chart.feed_type == "top-grossing":
            raise ValueError("source unavailable")
        result = HttpResult("https://fixture", datetime.now(UTC), 0, 200, b"chart", {}, None)
        return result, ParsedChart(
            chart,
            [Entry("com.game", 1, "Game", "https://fixture", None, None, [])],
            None,
            "partial",
            ["short source"],
        )

    def fetch_metadata(self, country, ids):
        self.calls.extend((country, package) for package in ids)
        if self.fail_metadata:
            raise ValueError("detail unavailable")
        result = HttpResult("https://fixture", datetime.now(UTC), 0, 200, b"meta", {}, None)
        return [
            (
                result,
                {
                    package: {
                        "name": "Game",
                        "status": "complete",
                        "installs": "10+",
                        "min_installs": 10,
                    }
                    for package in ids
                },
            )
        ]


def collect(tmp_path, provider, enrich=True):
    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)
    run = jobs.submit("manual", ["vn"], "test", ["top-free", "top-grossing"], platform="android")
    return repo, run, AndroidCollector(repo, provider, jobs).execute(run, enrich=enrich)


def test_partial_only_rankings_finish_partial(tmp_path):
    repo, _run, status = collect(tmp_path, Fake(), False)
    assert status == "partial"
    with repo._connect() as conn:
        assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == 2
        assert {r[0] for r in conn.execute("SELECT enrichment_status FROM market_runs")} == {
            "not_requested"
        }


def test_chart_failure_preserves_previous_ranking(tmp_path):
    repo, _run, status = collect(tmp_path, Fake(fail_chart=True))
    assert status == "partial"
    with repo._connect() as conn:
        assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == 1
        assert {r[0] for r in conn.execute("SELECT chart_status FROM market_runs")} == {
            "partial",
            "failed",
        }


def test_metadata_exception_preserves_rankings_and_continues(tmp_path):
    repo, _run, status = collect(tmp_path, Fake(fail_metadata=True))
    assert status == "partial"
    with repo._connect() as conn:
        assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == 2


def test_metadata_shared_feeds_reuse_cache(tmp_path):
    provider = Fake()
    repo, _run, _status = collect(tmp_path, provider)
    assert provider.calls == [("vn", "com.game")]
    with repo._connect() as conn:
        assert conn.execute("SELECT count(*) FROM snapshot_metadata").fetchone()[0] == 2


def test_failed_all_charts_finish_failed(tmp_path):
    class Broken(Fake):
        def fetch_chart(self, chart):
            raise ValueError("unavailable")

    repo, _run, status = collect(tmp_path, Broken())
    assert status == "failed"
    with repo._connect() as conn:
        assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == 0


def test_wait_heartbeats_without_worker_database_writes(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, get_ident

    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)
    run = jobs.submit("manual", ["vn"], "wait", ["top-free"], platform="android")
    done = Event()
    caller = get_ident()
    heartbeats = []

    class Heartbeats:
        def heartbeat(self, run_id):
            heartbeats.append(get_ident())
            done.set()

    collector = AndroidCollector(repo, Fake(), Heartbeats())
    collector.heartbeat_interval = 0.01
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert collector._wait(pool, run, lambda: done.wait(1))
    assert heartbeats == [caller]


def test_bodyless_metadata_records_error_and_attempts(tmp_path):
    class Bodyless(Fake):
        def fetch_metadata(self, country, ids):
            result = HttpResult(
                "https://fixture/detail", datetime.now(UTC), 1, None, None, {}, "timeout"
            )
            return [(result, {ids[0]: {"status": "partial", "error": "timeout"}})]

    repo, _run, status = collect(tmp_path, Bodyless())
    assert status == "partial"
    with repo._connect() as conn:
        assert all("timeout" in row[0] for row in conn.execute("SELECT error FROM market_runs"))
        assert (
            conn.execute(
                "SELECT count(*) FROM request_observations WHERE error='timeout' AND market_run_id IS NOT NULL"
            ).fetchone()[0]
            == 2
        )


def test_keyboard_interrupt_marks_run_interrupted_and_releases_lock(tmp_path):
    import pytest

    class Interrupted(Fake):
        def fetch_chart(self, chart):
            raise KeyboardInterrupt()

    repo = Repository(tmp_path)
    repo.initialize()
    jobs = JobService(repo)
    run = jobs.submit("manual", ["vn"], "interrupt", ["top-free"], platform="android")
    with pytest.raises(KeyboardInterrupt):
        AndroidCollector(repo, Interrupted(), jobs).execute(run)
    with repo._connect() as conn:
        assert (
            conn.execute("SELECT status FROM runs WHERE id=?", (run,)).fetchone()[0]
            == "interrupted"
        )
        assert conn.execute("SELECT count(*) FROM collector_lock").fetchone()[0] == 0


def test_bodyless_chart_keeps_failed_request_observations(tmp_path):
    class BodylessChart(Fake):
        def fetch_chart(self, chart):
            attempt = HttpResult(
                "https://fixture/chart", datetime.now(UTC), 1, None, None, {}, "timeout"
            )
            result = HttpResult(
                "https://fixture/chart", datetime.now(UTC), 1, None, None, {}, "timeout", (attempt,)
            )
            return result, ParsedChart(chart, [], None, "invalid", ["timeout"])

    repo, run, status = collect(tmp_path, BodylessChart())
    assert status == "failed"
    with repo._connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM request_observations WHERE run_id=?", (run,)
            ).fetchone()[0]
            == 4
        )
