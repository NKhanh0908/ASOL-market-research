import asyncio
import json
import sqlite3
import pytest
from pathlib import Path
from casual_scout.mcp.server import create_mcp_server

@pytest.fixture
def populated_db(tmp_path: Path):
    db_file = tmp_path / "test_mcp.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE markets (country TEXT PRIMARY KEY, name TEXT);
        INSERT INTO markets VALUES ('vn', 'Vietnam');
        CREATE TABLE charts (
            id TEXT PRIMARY KEY, provider TEXT, platform TEXT, country TEXT,
            collection TEXT, genre TEXT, depth INTEGER, version INTEGER
        );
        INSERT INTO charts VALUES ('c_ios', 'apple', 'ios', 'vn', 'topfreeapplications', '7003', 100, 1);
        INSERT INTO charts VALUES ('c_and', 'google', 'android', 'vn', 'top-free', 'GAME_CASUAL', 100, 1);

        CREATE TABLE snapshots (
            id TEXT PRIMARY KEY, chart_id TEXT, observed_at TEXT, quality TEXT, raw_hash TEXT
        );
        INSERT INTO snapshots VALUES ('s_ios', 'c_ios', '2026-09-30T07:00:00Z', 'complete', 'h_ios');
        INSERT INTO snapshots VALUES ('s_and', 'c_and', '2026-09-30T07:00:00Z', 'complete', 'h_and');

        CREATE TABLE snapshot_entries (
            snapshot_id TEXT, app_id TEXT, rank INTEGER, name TEXT, store_url TEXT,
            PRIMARY KEY(snapshot_id, app_id)
        );
        INSERT INTO snapshot_entries VALUES ('s_ios', 'app_ios_1', 1, 'iOS Game 1', 'https://apple.com/1');
        INSERT INTO snapshot_entries VALUES ('s_and', 'app_and_1', 1, 'Android Game 1', 'https://play.google.com/1');
    """)
    conn.commit()
    conn.close()
    return db_file

@pytest.mark.anyio
async def test_mcp_server_lists_tools(populated_db):
    server = create_mcp_server(populated_db)
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "get_daily_market_brief" in tool_names
    assert "get_game_rank_history" in tool_names
    assert "get_coverage" in tool_names

@pytest.mark.anyio
async def test_mcp_server_calls_get_daily_market_brief(populated_db):
    server = create_mcp_server(populated_db)
    res = await server.call_tool("get_daily_market_brief", {"country": "VN", "date": "2026-09-30"})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["country"] == "vn"
    assert data["date"] == "2026-09-30"
    assert "ios" in data["platforms"]
    assert "android" in data["platforms"]
    assert len(data["platforms"]["ios"]["top_10"]) == 1
    assert data["platforms"]["ios"]["top_10"][0]["app_id"] == "app_ios_1"
    assert len(data["platforms"]["android"]["top_10"]) == 1
    assert data["platforms"]["android"]["top_10"][0]["app_id"] == "app_and_1"

@pytest.mark.anyio
async def test_mcp_server_calls_get_game_rank_history(populated_db):
    server = create_mcp_server(populated_db)
    res = await server.call_tool("get_game_rank_history", {
        "country": "vn",
        "platform": "ios",
        "app_id": "app_ios_1",
        "date": "2026-09-30",
    })
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["app_id"] == "app_ios_1"
    assert data["game_status"] == "observed"
    assert len(data["rank_history"]) == 7

@pytest.mark.anyio
async def test_mcp_server_calls_get_coverage(populated_db):
    server = create_mcp_server(populated_db)
    res = await server.call_tool("get_coverage", {"country": "vn"})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["country"] == "vn"
    assert "ios" in data["platforms"]
    assert "android" in data["platforms"]
