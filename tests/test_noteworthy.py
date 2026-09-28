from casual_scout.stats.noteworthy import rank_noteworthy


def record(app="a", country="vn", rank=10):
    return {"app_id": app, "country": country, "current_rank": rank}


def test_multi_market_rise_is_evidence_not_score():
    items = rank_noteworthy(
        [record(), record(country="th"), record("b", rank=1)],
        {"vn": {"a": 10, "b": 1}, "th": {"a": 15}},
        {"vn": {"a": 35, "b": 1}, "th": {"a": 40}}, {},
    )
    assert len(items) == 2
    assert items[0]["noteworthy_label"] == "Tăng ở nhiều thị trường"
    assert items[0]["rising_markets"] == ["th", "vn"]
    assert items[0]["presence_count"] == items[0]["observed_market_count"] == 2
    assert "VN: +25 hạng / 1 ngày" in items[0]["noteworthy_reasons"]
    assert "opportunity_score" not in items[0]


def test_newly_collected_market_is_not_expansion():
    item = rank_noteworthy([record()], {"vn": {"a": 10}, "th": {"a": 5}},
                          {"vn": {"a": 10}}, {})[0]
    assert item["added_markets"] == []
    assert item["new_entry_markets"] == []
    assert item["comparable_markets"] == ["vn"]


def test_missing_baseline_is_unknown_not_steady_or_new():
    item = rank_noteworthy([record()], {"vn": {"a": 10}}, {}, {})[0]
    assert item["noteworthy_label"] == "Chưa đủ dữ liệu so sánh"
    assert not item["noteworthy"]
    assert item["delta_1d"] is None


def test_expansion_and_loss_are_reported_on_shared_markets():
    item = rank_noteworthy([record()],
                          {"vn": {"a": 10}, "th": {"a": 8}, "id": {}},
                          {"vn": {"a": 10}, "th": {"b": 1}, "id": {"a": 5}}, {})[0]
    assert item["added_markets"] == ["th"]
    assert item["lost_markets"] == ["id"]
    assert item["presence_count"] == 2
    assert item["observed_market_count"] == 3


def test_three_day_threshold_and_no_fake_presence_from_legacy_fields():
    source = {**record(), "cross_market_count": 11, "cross_markets": ["us"]}
    item = rank_noteworthy([source], {"vn": {"a": 10}}, {}, {"vn": {"a": 40}})[0]
    assert item["noteworthy_label"] == "Đang tăng"
    assert item["presence_markets"] == ["vn"]
    assert item["delta_3d"] == 30
    assert source["cross_market_count"] == 11


def test_first_observation_of_game_is_new_not_cross_market_expansion():
    item = rank_noteworthy([record()], {"vn": {"a": 10}}, {"vn": {"b": 1}}, {})[0]
    assert item["new_entry_markets"] == ["vn"]
    assert item["added_markets"] == []


def test_real_snapshots_drive_dashboard_api_exports_and_detail(tmp_path):
    from fastapi.testclient import TestClient
    from test_analysis_service import _create_snapshot_with_entries

    from casual_scout.analysis.service import AnalysisService
    from casual_scout.config import Settings
    from casual_scout.stats.noteworthy import observed_charts
    from casual_scout.storage import Repository
    from casual_scout.web.app import create_app

    repo = Repository(tmp_path)
    repo.initialize()
    for market, day, app_rank in [
        ("vn", "2026-09-24", 40), ("vn", "2026-09-25", 10),
        ("th", "2026-09-24", 35), ("th", "2026-09-25", 10),
        ("us", "2026-09-25", 5),
    ]:
        key = market + day
        _create_snapshot_with_entries(repo, key, key, market, day, day + "T08:00:00Z",
                                      [("a", app_rank, "A game")])
    # Grossing-only and previous-date markets cannot increase today's Free denominator.
    _create_snapshot_with_entries(repo, "gross", "gross", "id", "2026-09-25",
                                  "2026-09-25T08:00:00Z", [("a", 1, "A game")],
                                  collection="topgrossingapplications")
    _create_snapshot_with_entries(repo, "old", "old", "sg", "2026-09-23",
                                  "2026-09-23T08:00:00Z", [("a", 1, "A game")])
    # A partial SG chart today is not evidence that SG was fully observed today.
    _create_snapshot_with_entries(repo, "partial-sg", "partial-sg", "sg", "2026-09-25",
                                  "2026-09-25T09:00:00Z", [("a", 1, "A game")],
                                  quality="partial")
    assert set(observed_charts(repo, "2026-09-25")) == {"vn", "th", "us"}
    AnalysisService(repo).analyze_date("2026-09-25", ["vn", "th", "us"])
    client = TestClient(create_app(Settings(tmp_path)))
    item = client.get("/api/stats/radar?date=2026-09-25&country=vn").json()[0]
    assert item["noteworthy_label"] == "Tăng ở nhiều thị trường"
    assert item["presence_count"] == item["observed_market_count"] == 3
    assert item["added_markets"] == []  # US only started collecting today.
    assert item["comparable_markets"] == ["th", "vn"]
    assert item["delta_1d"] == 30
    assert "opportunity_score" not in item
    dashboard = client.get("/dashboard?date=2026-09-25&country=vn").text
    assert "VN: +30 hạng / 1 ngày" in dashboard
    assert "3/3 thị trường đã quan sát" in dashboard
    assert "bm_score" not in dashboard
    exported = client.get("/api/export/radar?date=2026-09-25&country=vn").text
    assert "VN: +30 hạng / 1 ngày" in exported
    assert "Opportunity Score" not in exported
    detail = client.get("/games/vn/a?snapshot_id=vn2026-09-25").text
    assert "3/3 thị trường đã quan sát" in detail
    assert "Độ phủ ASEAN" not in detail
    assert "3/3 thị trường đã quan sát" in client.get("/data?country=vn").text


def test_below_threshold_is_not_a_riser_and_current_rank_cannot_replace_missing_history():
    item = rank_noteworthy([record(rank=1)], {"vn": {"a": 1}},
                          {"vn": {"a": 20}}, {"vn": {"a": 30}})[0]
    assert not item["noteworthy"]
    assert item["rising_markets"] == []
    assert item["noteworthy_label"] == "Chưa có tín hiệu nổi bật"
