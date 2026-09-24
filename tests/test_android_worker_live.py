from casual_scout.android.storage import AndroidStore
from casual_scout.android.worker import collect
from casual_scout.storage import Repository


def test_first_batch_visible_before_second_finishes_and_failure_preserves_rows(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    store = AndroidStore(repo)
    store.initialize()
    job = store.enqueue()
    store.dispatch()

    class Provider:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def chart(self, feed):
            return (
                [
                    {"package": f"com.example.g{i}", "rank": i, "name": f"Game {i}"}
                    for i in range(1, 9)
                ],
                "fixture.html",
            )

        def metadata(self, package):
            if package == "com.example.g6":
                live = AndroidStore(Repository(tmp_path)).view(job)
                assert live["job"]["status"] == "running"
                assert live["job"]["processed"] == 5
                assert live["job"]["batches"] == 1
                assert live["entries"][0]["developer"] == "Fixture Studio"
            if package == "com.example.g8":
                raise ValueError("fixture metadata failure")
            return {
                "package": package,
                "developer": "Fixture Studio",
                "description": "match 3",
                "metadata_status": "complete",
            }

    assert collect(store, job, lambda _: Provider()) == "partial"
    view = store.view(job)
    assert len(view["entries"]) == 8
    assert view["job"]["processed"] == 8
    assert view["job"]["batches"] == 2
    assert view["entries"][-1]["metadata_status"] == "failed"
    assert view["entries"][0]["mechanic"] == "Match-3"


def test_one_chart_failure_keeps_other_chart_and_finishes_partial(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    store = AndroidStore(repo)
    store.initialize()
    job = store.enqueue()
    store.dispatch()

    class Provider:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def chart(self, feed):
            if feed == "top-free":
                raise ValueError("chart unavailable")
            return ([{"package": "com.example.one", "name": "One", "rank": 1}], "fixture")

        def metadata(self, package):
            return {"package": package, "metadata_status": "complete"}

    assert collect(store, job, lambda _: Provider()) == "partial"
    assert store.view(job)["entries"][0]["grossing_rank"] == 1
