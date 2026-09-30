from __future__ import annotations

from datetime import UTC, datetime, date as Date, timedelta
from pathlib import Path
import mcp.types
from mcp.server.mcpserver import MCPServer
from casual_scout.market_brief.reader import MarketBriefReader
from casual_scout.market_brief.service import compute_platform_brief, compute_game_history
from casual_scout.mcp.contracts import (
    DailyMarketBriefResponse,
    GameRankHistoryResponse,
    CoverageResponse,
    PlatformCoverage,
    normalize_country,
    validate_iso_date,
)

READ_ONLY_ANNOTATIONS = mcp.types.ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

def create_mcp_server(db_path: Path) -> MCPServer:
    """Create and configure a read-only MCPServer with market brief tools."""
    server = MCPServer(
        "Casual Scout Market Brief",
        instructions="Read-only market intelligence for iOS and Android Top Free Casual charts across ASEAN and US.",
    )
    reader = MarketBriefReader(db_path)

    @server.tool(
        name="get_daily_market_brief",
        description="Fetch Top Free Casual daily market brief for iOS and Android across 9 allowed markets (vn, th, id, my, ph, sg, la, kh, us).",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_daily_market_brief(country: str, date: str | None = None) -> str:
        norm_country = normalize_country(country)
        target_date = validate_iso_date(date) or datetime.now(UTC).strftime("%Y-%m-%d")

        ios_snaps = reader.get_window_snapshots(norm_country, "ios", target_date)
        android_snaps = reader.get_window_snapshots(norm_country, "android", target_date)

        ios_brief = compute_platform_brief(norm_country, "ios", target_date, ios_snaps)
        android_brief = compute_platform_brief(norm_country, "android", target_date, android_snaps)

        response = DailyMarketBriefResponse(
            generated_at=datetime.now(UTC).isoformat(),
            country=norm_country,
            date=target_date,
            platforms={"ios": ios_brief, "android": android_brief},
        )
        return response.model_dump_json(indent=2)

    @server.tool(
        name="get_game_rank_history",
        description="Fetch 7-day rank history for a single game in a target market on iOS or Android.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_game_rank_history(country: str, platform: str, app_id: str, date: str | None = None) -> str:
        norm_country = normalize_country(country)
        plat = "ios" if platform.lower() == "ios" else "android"
        target_date = validate_iso_date(date) or datetime.now(UTC).strftime("%Y-%m-%d")

        snaps = reader.get_window_snapshots(norm_country, plat, target_date)
        history = compute_game_history(app_id, target_date, snaps)
        observed = any(p.rank is not None for p in history)

        response = GameRankHistoryResponse(
            country=norm_country,
            platform=plat,
            app_id=app_id,
            date=target_date,
            game_status="observed" if observed else "not_observed_in_window",
            name=None,
            rank_history=history,
        )
        return response.model_dump_json(indent=2)

    @server.tool(
        name="get_coverage",
        description="Inspect complete snapshot coverage for the last 7 UTC days across iOS and Android.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_coverage(country: str) -> str:
        norm_country = normalize_country(country)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        ios_snaps = reader.get_window_snapshots(norm_country, "ios", today)
        android_snaps = reader.get_window_snapshots(norm_country, "android", today)

        response = CoverageResponse(
            country=norm_country,
            platforms={
                "ios": PlatformCoverage(
                    platform="ios",
                    days_complete=len(ios_snaps),
                    latest_complete_date=max(ios_snaps.keys()) if ios_snaps else None,
                    days={d: {"quality": s.quality, "entries": len(s.entries)} for d, s in ios_snaps.items()},
                ),
                "android": PlatformCoverage(
                    platform="android",
                    days_complete=len(android_snaps),
                    latest_complete_date=max(android_snaps.keys()) if android_snaps else None,
                    days={d: {"quality": s.quality, "entries": len(s.entries)} for d, s in android_snaps.items()},
                ),
            },
        )
        return response.model_dump_json(indent=2)

    return server
