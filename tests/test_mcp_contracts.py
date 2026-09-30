import pytest
from pydantic import ValidationError
from casual_scout.mcp.contracts import (
    MarketBriefRequest,
    GameHistoryRequest,
    CoverageRequest,
    StrongMove,
    RankHistoryPoint,
)

def test_market_brief_request_validates_country():
    req = MarketBriefRequest(country="VN")
    assert req.country == "vn"

    with pytest.raises(ValidationError):
        MarketBriefRequest(country="invalid_code")

def test_market_brief_request_validates_date():
    req = MarketBriefRequest(country="vn", date="2026-09-30")
    assert req.date == "2026-09-30"

    with pytest.raises(ValidationError):
        MarketBriefRequest(country="vn", date="30-09-2026")

def test_game_history_request_validates_platform():
    req = GameHistoryRequest(country="us", platform="ios", app_id="123456")
    assert req.platform == "ios"

    with pytest.raises(ValidationError):
        GameHistoryRequest(country="us", platform="windows", app_id="123456")

def test_strong_move_contract():
    move = StrongMove(window_days=1, delta=25, direction="up", threshold=20)
    assert move.window_days == 1
    assert move.delta == 25
    assert move.direction == "up"
