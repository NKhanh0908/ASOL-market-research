"""Platform-scoped REST APIs for data, opportunity radar, and background crawls."""
from __future__ import annotations

from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from casual_scout.collection.jobs import JobService
from casual_scout.storage import Repository
from casual_scout.web.views import get_dashboard_view, get_data_view


class CrawlRequest(BaseModel):
    platform: Literal["ios", "android"] = "ios"
    markets: list[str] = Field(
        default_factory=lambda: ["vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"],
        min_length=1,
        max_length=9,
    )
    chart_type: Literal["all", "free", "grossing"] = "all"

    @field_validator("markets")
    @classmethod
    def valid_markets(cls, values: list[str]) -> list[str]:
        allowed = {"vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"}
        normalized = list(dict.fromkeys(v.lower().strip() for v in values))
        if not set(normalized) <= allowed:
            raise ValueError("unsupported market")
        return normalized


def create_platform_router(
    repo: Repository,
    launcher: Callable[[str, str], int] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["Platform API"])

    @router.get("/data")
    def get_api_data(
        platform: Literal["ios", "android"] = "ios",
        country: str = "vn",
        feed_type: str = "top-free",
        date: str | None = None,
    ) -> dict[str, Any]:
        """Query top 100 casual game rankings and metadata for a given platform and country."""
        country_norm = country.lower().strip()
        allowed = {"vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"}
        if country_norm not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unsupported country: {country}",
            )

        data = get_data_view(
            repo,
            country=country_norm,
            feed_type=feed_type,
            date=date,
            platform=platform,
        )
        return {
            "platform": platform,
            "country": country_norm,
            "feed_type": feed_type,
            "date": date,
            "entries": data.get("entries", []),
        }

    @router.get("/stats/radar")
    def get_api_radar(
        platform: Literal["ios", "android"] = "ios",
        country: str = "vn",
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query opportunity radar ranking games for a given platform and country."""
        country_norm = country.lower().strip()
        data = get_dashboard_view(repo, date_str=date, country=country_norm, platform=platform)
        return data.get("radar_items", [])

    @router.post("/crawl", status_code=status.HTTP_200_OK)
    def trigger_crawl(
        request: Request,
        crawl_req: CrawlRequest,
    ) -> dict[str, Any]:
        """Trigger an asynchronous background collection run for the selected platform."""
        chart_types = None
        if crawl_req.chart_type == "free":
            chart_types = ["top-free"]
        elif crawl_req.chart_type == "grossing":
            chart_types = ["top-grossing"]
        else:
            chart_types = ["top-free", "top-grossing"]

        jobs = JobService(repo)
        idempotency_key = request.headers.get("Idempotency-Key") or str(uuid4())
        req_key = f"web-api-{crawl_req.platform}-{idempotency_key}"

        run_id = jobs.submit(
            trigger="manual",
            countries=crawl_req.markets,
            request_key=req_key,
            chart_types=chart_types,
            platform=crawl_req.platform,
        )

        if launcher:
            launcher(run_id, str(repo.data_dir))

        return {
            "run_id": run_id,
            "status": "queued",
            "platform": crawl_req.platform,
            "markets": crawl_req.markets,
            "chart_type": crawl_req.chart_type,
        }

    return router
