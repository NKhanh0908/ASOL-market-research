from __future__ import annotations

import re
from datetime import UTC, datetime, date as Date
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

ALLOWED_COUNTRIES = {"vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"}

def normalize_country(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in ALLOWED_COUNTRIES:
        raise ValueError(f"Country must be one of {sorted(ALLOWED_COUNTRIES)}, got '{value}'")
    return cleaned

def validate_iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = Date.fromisoformat(value)
        return parsed.isoformat()
    except ValueError:
        raise ValueError(f"Date must be in YYYY-MM-DD format, got '{value}'")

class MarketBriefRequest(BaseModel):
    country: str
    date: str | None = None

    @field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        return normalize_country(v)

    @field_validator("date")
    @classmethod
    def validate_date_field(cls, v: str | None) -> str | None:
        return validate_iso_date(v)

class GameHistoryRequest(BaseModel):
    country: str
    platform: Literal["ios", "android"]
    app_id: str
    date: str | None = None

    @field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        return normalize_country(v)

    @field_validator("app_id")
    @classmethod
    def validate_app_id_field(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("app_id cannot be empty")
        return s

    @field_validator("date")
    @classmethod
    def validate_date_field(cls, v: str | None) -> str | None:
        return validate_iso_date(v)

class CoverageRequest(BaseModel):
    country: str

    @field_validator("country")
    @classmethod
    def validate_country_field(cls, v: str) -> str:
        return normalize_country(v)

class StrongMove(BaseModel):
    window_days: int
    delta: int
    direction: Literal["up", "down"]
    threshold: int

class RankHistoryPoint(BaseModel):
    date: str
    rank: int | None
    status: Literal["observed", "not_in_observed_chart", "no_complete_snapshot", "incompatible_chart", "expired"]

class BriefGameEntry(BaseModel):
    app_id: str
    name: str
    store_url: str | None
    rank: int
    rank_1d_ago: int | None
    rank_3d_ago: int | None
    delta_1d: int | None
    delta_3d: int | None
    movement_1d: Literal["up", "down", "unchanged", "new_entry", "unknown"]
    comparison_1d: Literal["available", "no_baseline", "partial", "unavailable"]
    comparison_3d: Literal["available", "no_baseline", "partial", "unavailable"]
    strong_moves: list[StrongMove]
    rank_history: list[RankHistoryPoint]
    developer: str | None = None
    genre: str | None = None
    metadata_fetched_at: str | None = None

class PlatformBrief(BaseModel):
    data_status: Literal["available", "partial", "unavailable"]
    comparison_status: Literal["available", "partial", "unavailable"]
    warnings: list[dict[str, str]] = Field(default_factory=list)
    snapshots: dict[str, Any] = Field(default_factory=dict)
    top_10: list[BriefGameEntry] = Field(default_factory=list)
    strong_movers_outside_top_10: list[BriefGameEntry] = Field(default_factory=list)
    total_top_10: int = 0
    total_strong_movers: int = 0

class DailyMarketBriefResponse(BaseModel):
    schema_version: str = "market-brief.v1"
    rules_version: str = "market-brief-selection.v1"
    generated_at: str
    country: str
    date: str
    date_timezone: str = "UTC"
    feed_type: str = "top-free-casual"
    history_days: int = 7
    platforms: dict[str, PlatformBrief]

class GameRankHistoryResponse(BaseModel):
    schema_version: str = "game-history.v1"
    country: str
    platform: Literal["ios", "android"]
    app_id: str
    date: str
    history_days: int = 7
    game_status: Literal["observed", "not_observed_in_window"]
    name: str | None
    rank_history: list[RankHistoryPoint]

class PlatformCoverage(BaseModel):
    platform: Literal["ios", "android"]
    days_complete: int
    latest_complete_date: str | None
    days: dict[str, dict[str, Any]]

class CoverageResponse(BaseModel):
    schema_version: str = "coverage.v1"
    country: str
    history_days: int = 7
    platforms: dict[str, PlatformCoverage]
