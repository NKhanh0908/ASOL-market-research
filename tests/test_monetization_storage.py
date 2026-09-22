import sqlite3
from pathlib import Path

from casual_scout.models import Chart
from casual_scout.storage.repository import Repository


def test_chart_supports_feed_type():
    c_free = Chart("vn", feed_type="top-free")
    c_grossing = Chart("vn", feed_type="top-grossing")
    assert c_free.feed_type == "top-free"
    assert c_grossing.feed_type == "top-grossing"
    assert c_free.collection == "topfreeapplications"
    assert c_grossing.collection == "topgrossingapplications"


def test_schema_migration_adds_monetization_columns(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()

    with sqlite3.connect(repo.database_path) as conn:
        # Check metadata_versions columns
        meta_cols = [r[1] for r in conn.execute("PRAGMA table_info(metadata_versions)").fetchall()]
        assert "in_app_purchases_json" in meta_cols
        assert "has_in_app_purchases" in meta_cols
        assert "monetization_model" in meta_cols

        # Check daily_rank_analytics columns
        analytics_column_info = {
            row[1]: row for row in conn.execute("PRAGMA table_info(daily_rank_analytics)").fetchall()
        }
        an_cols = list(analytics_column_info)
        assert "grossing_rank" in an_cols
        assert "free_rank" in an_cols
        assert "monetization_model" in an_cols
        assert "monetization_efficiency_flag" in an_cols
        model_column = analytics_column_info["monetization_model"]
        assert model_column[3] == 1
        assert model_column[4] == "'PURE_ADS'"


def test_schema_migration_is_idempotent_on_existing_db(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    # Call initialize again on existing database
    repo.initialize()

    with sqlite3.connect(repo.database_path) as conn:
        meta_cols = [r[1] for r in conn.execute("PRAGMA table_info(metadata_versions)").fetchall()]
        assert "in_app_purchases_json" in meta_cols
