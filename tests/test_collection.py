

from casual_scout.models import Chart


def test_lookup_failure_preserves_chart(collection_fixture):
    repo, provider, jobs, collector = collection_fixture
    provider.fail_lookup = True

    run_id = jobs.submit("manual", ["vn"], "request-1")
    status = collector.execute(run_id)

    assert status == "partial"
    latest = repo.latest_complete(Chart("vn"))
    assert latest is not None
    assert latest["quality"] == "complete"
    assert "tl" not in provider.requested_countries


def test_collector_successful_run(collection_fixture):
    repo, _provider, jobs, collector = collection_fixture

    run_id = jobs.submit("manual", ["vn", "us"], "request-success")
    status = collector.execute(run_id)

    assert status == "succeeded"
    assert repo.latest_complete(Chart("vn")) is not None
    assert repo.latest_complete(Chart("us")) is not None


def test_collector_without_enrichment(collection_fixture):
    repo, provider, jobs, collector = collection_fixture

    run_id = jobs.submit("manual", ["vn"], "request-no-enrich")
    status = collector.execute(run_id, enrich=False)

    assert status == "succeeded"
    assert provider.lookup_call_count == 0

    with repo._connect() as conn:
        mr = conn.execute(
            "SELECT enrichment_status FROM market_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert mr["enrichment_status"] == "not_requested"


def test_collector_unverified_market_tl_is_not_called_via_network(collection_fixture):
    repo, provider, jobs, collector = collection_fixture

    run_id = jobs.submit("manual", ["vn", "tl"], "request-tl")
    status = collector.execute(run_id)

    # VN succeeds, TL fails as unverified -> overall run is partial
    assert status == "partial"
    assert "tl" not in provider.requested_countries
    with repo._connect() as conn:
        tl_mr = conn.execute(
            """
            SELECT mr.* FROM market_runs mr
            JOIN charts c ON c.id = mr.chart_id
            WHERE mr.run_id = ? AND c.country = 'tl'
            """,
            (run_id,),
        ).fetchone()
        assert tl_mr["chart_status"] == "failed"
        assert "Apple source not verified" in (tl_mr["error"] or "")


def test_collector_caches_metadata_and_skips_fetch(collection_fixture):
    _repo, provider, jobs, collector = collection_fixture

    run1 = jobs.submit("manual", ["vn"], "req-1")
    collector.execute(run1, enrich=True)
    first_lookup_count = provider.lookup_call_count
    assert first_lookup_count > 0

    run2 = jobs.submit("manual", ["vn"], "req-2")
    collector.execute(run2, enrich=True)
    # Second run should reuse the cache (fresh for 24 hours) and make 0 new lookup calls
    assert provider.lookup_call_count == first_lookup_count
