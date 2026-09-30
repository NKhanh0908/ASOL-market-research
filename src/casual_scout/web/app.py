from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from datetime import date as Date
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from casual_scout.android.coordinator import AndroidCoordinator, launch_android
from casual_scout.android.storage import AndroidStore
from casual_scout.collection.jobs import CollectionBusyError, JobService
from casual_scout.collection.processes import launch_pipeline
from casual_scout.config import (
    IOS_COLLECTION_COUNTRIES,
    IOS_COLLECTION_LABEL,
    IOS_COLLECTION_SCOPE,
    Settings,
)
from casual_scout.storage import Repository
from casual_scout.web.android import android_router
from casual_scout.web.platform_api import create_platform_router
from casual_scout.web.presentation import (
    app_store_url,
    installs_badge,
    platform_url,
    render_installs_badge,
)
from casual_scout.web.security import (
    LocalOriginMiddleware,
    SecurityManager,
    allowed_hosts,
    get_or_create_secret,
)
from casual_scout.web.views import (
    format_vn_time,
    get_dashboard_view,
    get_data_view,
    get_game_view,
    get_run_detail_view,
    get_runs_view,
    get_shortlist_view,
)

_ALL_MARKETS = ["vn", "us", "bn", "kh", "id", "la", "my", "mm", "ph", "sg", "th", "tl"]
_VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


def create_app(
    settings: Settings,
    launcher: Callable[[str, Path], int] = launch_pipeline,
    scheduler_factory: Callable[[Repository, Callable[[str, Path], int]], object] | None = None,
    android_launcher=launch_android,
) -> FastAPI:
    repo = Repository(settings.data_dir)
    repo.initialize()
    android_store = AndroidStore(repo)
    android_store.initialize()
    jobs = JobService(repo)
    scheduler = (
        scheduler_factory(repo, launcher)
        if scheduler_factory is not None
        else AndroidCoordinator(repo, launcher, android_launcher=android_launcher)
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        jobs.recover_dead_processes()
        scheduler.start()
        try:
            yield
        finally:
            scheduler.stop()

    app = FastAPI(title="Casual Scout", lifespan=lifespan)
    app.state.repo = repo

    secret = get_or_create_secret(settings.data_dir)
    sec_mgr = SecurityManager(secret)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts(),
    )
    app.add_middleware(LocalOriginMiddleware, hosts=allowed_hosts())

    static_dir = Path(__file__).parent / "static"

    def static_asset(filename: str) -> str:
        # Match each rendered page to its CSS/JS, even after an in-place update.
        version = sha256((static_dir / filename).read_bytes()).hexdigest()[:12]
        return f"/static/{filename}?v={version}"

    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))
    templates.env.autoescape = True
    templates.env.globals["static_asset"] = static_asset
    templates.env.globals["ios_collection_scope"] = IOS_COLLECTION_SCOPE
    templates.env.globals["ios_collection_label"] = IOS_COLLECTION_LABEL
    templates.env.globals["ios_collection_count"] = len(IOS_COLLECTION_COUNTRIES)
    templates.env.globals["mock_demo"] = (settings.data_dir / "MOCK_DATA.json").is_file()
    templates.env.globals["installs_badge"] = installs_badge
    templates.env.globals["render_installs_badge"] = render_installs_badge
    templates.env.globals["platform_url"] = platform_url
    templates.env.globals["app_store_url"] = app_store_url
    app.include_router(android_router(android_store, templates, sec_mgr, android_launcher))
    app.include_router(create_platform_router(repo, launcher, sec_mgr))

    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def _get_or_create_session(request: Request) -> tuple[str, bool]:
        session_id = request.cookies.get("session_id")
        if not session_id:
            return secrets.token_hex(16), True
        return session_id, False

    def _attach_cookies(
        response: Response,
        session_id: str,
        is_new_session: bool,
        csrf_token: str | None = None,
    ) -> None:
        if is_new_session:
            response.set_cookie(
                "session_id",
                session_id,
                httponly=True,
                samesite="strict",
            )
        if csrf_token is not None:
            response.set_cookie("csrftoken", csrf_token, httponly=False, samesite="strict")

    @app.get("/")
    @app.get("/data")
    def index_view(
        request: Request,
        country: Literal[
            "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "vn",
        feed_type: Literal["top-free", "top-grossing"] = "top-free",
        snapshot_id: str | None = None,
        signal: str | None = None,
        date: Date | None = None,
        platform: Literal["ios", "android"] = "ios",
    ):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)

        try:
            data = get_data_view(
                repo,
                country=country,
                feed_type=feed_type,
                snapshot_id=snapshot_id,
                signal=signal,
                date=date.isoformat() if date else None,
                platform=platform,
            )
        except (ValueError, KeyError) as error:
            raise HTTPException(404, "Snapshot not found in selected scope") from error
        context = {
            "request": request,
            "active_tab": "data",
            "csrf_token": csrf_token,
            "now_key": str(uuid4())[:8],
            "platform": platform,
            **data,
        }
        rendered = templates.TemplateResponse(request=request, name="data.html", context=context)
        _attach_cookies(rendered, session_id, is_new, csrf_token)
        return rendered

    @app.post("/runs")
    def post_runs(
        request: Request,
        country: str = Form(default=IOS_COLLECTION_SCOPE),
        request_key: str = Form(default=""),
        csrf_token: str = Form(default=""),
        platform: str = Form(default="ios"),
    ):
        session_id = request.cookies.get("session_id") or ""
        if not sec_mgr.validate_csrf_token(csrf_token, session_id):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        if country == IOS_COLLECTION_SCOPE:
            countries = list(IOS_COLLECTION_COUNTRIES)
        elif country == "all":
            countries = _ALL_MARKETS
        else:
            countries = [c.strip().lower() for c in country.split(",") if c.strip()]

        if not request_key:
            request_key = f"web-{uuid4()}"

        if platform == "android":
            countries = ["vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"]
        try:
            run_id = jobs.submit(
                "manual",
                countries,
                request_key,
                chart_types=["top-free", "top-grossing"] if platform == "android" else ["top-free"],
                platform=platform,
            )
        except CollectionBusyError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        try:
            jobs.launch(run_id, launcher)
        except Exception as error:
            raise HTTPException(503, "Worker launch failed") from error

        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @app.get("/runs")
    def runs_list_view(request: Request):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)

        runs = get_runs_view(repo)
        context = {
            "request": request,
            "active_tab": "runs",
            "csrf_token": csrf_token,
            "now_key": str(uuid4())[:8],
            **runs,
        }
        rendered = templates.TemplateResponse(request=request, name="runs.html", context=context)
        _attach_cookies(rendered, session_id, is_new, csrf_token)
        return rendered

    @app.get("/runs/{run_id}")
    def run_detail_view(request: Request, run_id: str):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)

        run = get_run_detail_view(repo, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")

        context = {
            "request": request,
            "active_tab": "runs",
            "csrf_token": csrf_token,
            **run,
        }
        rendered = templates.TemplateResponse(request=request, name="run.html", context=context)
        _attach_cookies(rendered, session_id, is_new, csrf_token)
        return rendered

    @app.get("/runs/{run_id}/status")
    def run_status_endpoint(run_id: str):
        with closing(repo._connect()) as conn:
            row = conn.execute(
                "SELECT id, status, started_at, ended_at FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Run not found")

            mr_rows = conn.execute(
                """
                SELECT mr.*, c.country, c.platform, c.collection, m.name as market_name, s.id as snapshot_id, s.quality
                FROM market_runs mr
                JOIN charts c ON c.id = mr.chart_id
                LEFT JOIN markets m ON m.country = c.country
                LEFT JOIN snapshots s ON s.market_run_id = mr.id
                WHERE mr.run_id = ?
                ORDER BY c.country ASC, mr.id ASC
                """,
                (run_id,),
            ).fetchall()

        market_runs = []
        total_markets = len(mr_rows)
        completed_markets = 0
        current_market = None

        for r in mr_rows:
            mr_d = dict(r)
            chart_st = mr_d.get("chart_status") or "pending"
            enrich_st = mr_d.get("enrichment_status") or "pending"
            is_done = bool(mr_d.get("ended_at")) or (
                chart_st in ("complete", "completed", "failed", "partial", "skipped")
                and enrich_st in ("complete", "completed", "failed", "partial", "skipped")
            )
            is_running = (chart_st == "running" or enrich_st == "running") and not is_done

            market_display = mr_d.get("market_name") or mr_d.get("country", "").upper()
            if is_done:
                completed_markets += 1
            elif is_running and not current_market:
                current_market = market_display

            market_runs.append({
                "country": mr_d.get("country", ""),
                "country_name": market_display,
                "platform": mr_d.get("platform", "ios"),
                "collection": mr_d.get("collection", "top-free"),
                "chart_status": chart_st,
                "enrichment_status": enrich_st,
                "valid_count": int(mr_d.get("valid_count") or 0),
                "received_count": int(mr_d.get("received_count") or 0),
                "error": mr_d.get("error") or "",
                "ended_at_vn": format_vn_time(mr_d.get("ended_at")),
                "snapshot_id": mr_d.get("snapshot_id"),
                "is_done": is_done,
                "is_running": is_running,
            })

        if not current_market and completed_markets < total_markets:
            for m in market_runs:
                if not m["is_done"]:
                    current_market = m["country_name"]
                    break

        percent = int(completed_markets / total_markets * 100) if total_markets > 0 else 0
        status_str = str(row["status"])
        if status_str in ("succeeded", "completed", "partial"):
            percent = 100
            if completed_markets == 0 and total_markets > 0:
                completed_markets = total_markets

        return {
            "id": str(row["id"]),
            "status": status_str,
            "started_at_vn": format_vn_time(str(row["started_at"])) if row["started_at"] else "—",
            "ended_at": str(row["ended_at"]) if row["ended_at"] else None,
            "ended_at_vn": format_vn_time(str(row["ended_at"])) if row["ended_at"] else None,
            "total_markets": total_markets,
            "completed_markets": completed_markets,
            "percent": percent,
            "current_market": current_market or "",
            "market_runs": market_runs,
        }

    @app.get("/api/charts/grossing")
    def grossing_chart_endpoint(
        country: Literal[
            "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "vn",
        date: Date | None = None,
    ):
        if not date:
            raise HTTPException(status_code=400, detail="date is required")

        snapshot_ref = repo.find_latest_complete_snapshot_for_date(
            date.isoformat(), country, collection="topgrossingapplications"
        )
        if snapshot_ref is None:
            raise HTTPException(status_code=404, detail="No complete Top Grossing snapshot found")

        snapshot = repo.get_snapshot(snapshot_ref["id"])
        return {
            "snapshot_id": snapshot["id"],
            "country": snapshot["chart"]["country"],
            "date": date,
            "observed_at": snapshot["observed_at"],
            "entries": [
                {"app_id": entry["app_id"], "rank": entry["rank"], "name": entry["name"]}
                for entry in snapshot["entries"]
            ],
        }

    @app.get("/api/schedule")
    def get_daily_schedule():
        schedule = repo.get_daily_schedule()
        with closing(repo._connect()) as connection:
            last_run = connection.execute(
                """
                SELECT r.id, r.status, r.started_at, r.ended_at
                FROM runs r
                JOIN market_runs mr ON mr.run_id = r.id
                JOIN charts c ON c.id = mr.chart_id
                WHERE c.country = 'vn'
                GROUP BY r.id
                ORDER BY r.started_at DESC
                LIMIT 1
                """
            ).fetchone()
        schedule["last_run"] = dict(last_run) if last_run else None
        return schedule

    @app.patch("/api/schedule")
    async def update_daily_schedule(request: Request):
        session_id = request.cookies.get("session_id") or ""
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not sec_mgr.validate_csrf_token(csrf_token, session_id):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        body = await request.json()
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=422, detail="enabled must be a boolean")
        return repo.set_daily_schedule_enabled(enabled)

    @app.get("/api/one-time-schedule")
    def get_one_time_schedule():
        return repo.get_one_time_collection()

    @app.post("/api/one-time-schedule")
    async def create_one_time_schedule(request: Request):
        session_id = request.cookies.get("session_id") or ""
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not sec_mgr.validate_csrf_token(csrf_token, session_id):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        body = await request.json()
        scheduled_for = body.get("scheduled_for")
        if not isinstance(scheduled_for, str):
            raise HTTPException(status_code=422, detail="scheduled_for must be an ISO datetime")
        try:
            parsed = datetime.fromisoformat(scheduled_for)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="scheduled_for must be an ISO datetime"
            ) from exc

        local_time = (
            parsed.astimezone(_VIETNAM)
            if parsed.tzinfo is not None and parsed.utcoffset() is not None
            else parsed.replace(tzinfo=_VIETNAM)
        )
        if local_time.astimezone(UTC) <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="scheduled_for must be in the future")
        try:
            return repo.schedule_one_time_collection(
                local_time,
                local_time.replace(tzinfo=None).isoformat(timespec="minutes"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/games/{country}/{app_id}")
    @app.get("/games/{app_id}")
    def game_detail_view(
        request: Request,
        app_id: str,
        country: Literal[
            "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "vn",
        snapshot_id: str | None = None,
        platform: Literal["ios", "android"] | None = None,
    ):
        session_id, is_new = _get_or_create_session(request)

        try:
            game = get_game_view(
                repo, app_id, country=country, snapshot_id=snapshot_id, platform=platform
            )
        except (ValueError, KeyError) as error:
            raise HTTPException(404, "Game not found in selected scope") from error
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        context = {
            "request": request,
            "active_tab": "data",
            "platform": platform or game.get("platform", "ios"),
            **game,
        }
        rendered = templates.TemplateResponse(request=request, name="game.html", context=context)
        _attach_cookies(rendered, session_id, is_new)
        return rendered

    @app.get("/evidence/{raw_hash}")
    def evidence_download_endpoint(raw_hash: str):
        with closing(repo._connect()) as conn:
            row = conn.execute(
                "SELECT path, endpoint FROM raw_responses WHERE hash = ?", (raw_hash,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Evidence not found")

            file_path = settings.data_dir / str(row["path"])
            if not file_path.is_file():
                raise HTTPException(status_code=404, detail="Evidence file missing on disk")

            return FileResponse(
                path=file_path,
                media_type="application/octet-stream",
                filename=f"evidence-{raw_hash[:12]}.json",
            )

    @app.get("/export/csv")
    @app.get("/data/download")
    def data_download_endpoint(
        country: Literal[
            "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "vn",
        snapshot_id: str | None = None,
        date: Date | None = None,
        signal: str | None = None,
        platform: Literal["ios", "android"] = "ios",
        feed_type: Literal["top-free", "top-grossing"] = "top-free",
    ):
        try:
            data = get_data_view(
                repo,
                country=country,
                snapshot_id=snapshot_id,
                signal=signal,
                date=date.isoformat() if date else None,
                platform=platform,
                feed_type=feed_type,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(404, "Snapshot not found in selected scope") from error
        entries = data.get("entries", [])
        if not entries:
            raise HTTPException(status_code=404, detail="No data available for download")

        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "rank",
                "name",
                "app_id",
                "subgenre",
                "mechanic",
                "confidence",
                "delta_1d",
                "delta_3d",
                "delta_7d",
                "signal",
                "cross_market_count",
                "cross_markets",
                "observed_market_count",
                "developer",
                "rating",
                "store_url",
            ]
        )
        for e in entries:
            cm_str = ";".join(e.get("cross_markets", []))
            d1 = str(e.get("delta_1d")) if e.get("delta_1d") is not None else ""
            d3 = str(e.get("delta_3d")) if e.get("delta_3d") is not None else ""
            d7 = str(e.get("delta_7d")) if e.get("delta_7d") is not None else ""
            writer.writerow(
                [
                    e.get("rank"),
                    e.get("name"),
                    e.get("app_id"),
                    e.get("subgenre"),
                    e.get("mechanic"),
                    e.get("mechanic_confidence"),
                    d1,
                    d3,
                    d7,
                    e.get("signal"),
                    e.get("cross_market_count"),
                    cm_str,
                    e.get("observed_market_count"),
                    e.get("developer"),
                    e.get("rating_display"),
                    e.get("store_url"),
                ]
            )

        csv_content = output.getvalue()
        date_str = date or (
            data.get("selected_snapshot", {}).get("observed_at", "")[:10]
            if data.get("selected_snapshot")
            else "today"
        )
        return Response(
            content=csv_content.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="casual-scout-{country}-{date_str}.csv"'
            },
        )

    # ------------------ Phase 3 Dashboard & Shortlist Views ------------------

    @app.get("/dashboard")
    def dashboard_view(
        request: Request,
        date: Date | None = None,
        country: Literal[
            "all", "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "all",
        platform: Literal["ios", "android"] = "ios",
    ):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)

        data = get_dashboard_view(
            repo, date_str=date.isoformat() if date else None, country=country, platform=platform
        )
        data["daily_schedule"] = (
            {**android_store.view()["schedule"], "time": "07:00", "timezone": "Asia/Ho_Chi_Minh"}
            if platform == "android"
            else repo.get_daily_schedule()
        )
        context = {
            "request": request,
            "active_tab": "dashboard",
            "csrf_token": csrf_token,
            "platform": platform,
            **data,
        }
        resp = templates.TemplateResponse(request=request, name="dashboard.html", context=context)
        _attach_cookies(resp, session_id, is_new, csrf_token=csrf_token)
        return resp

    @app.get("/shortlist")
    def shortlist_view(
        request: Request,
        status: str | None = None,
        priority: str | None = None,
    ):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)

        data = get_shortlist_view(repo, status=status, priority=priority)
        context = {
            "request": request,
            "active_tab": "shortlist",
            "csrf_token": csrf_token,
            **data,
        }
        resp = templates.TemplateResponse(request=request, name="shortlist.html", context=context)
        _attach_cookies(resp, session_id, is_new, csrf_token=csrf_token)
        return resp

    # ------------------ Phase 3 REST APIs & Export ------------------

    @app.get("/api/stats/summary")
    def api_stats_summary(
        date: Date | None = None,
        country: Literal[
            "all", "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "all",
        platform: Literal["ios", "android"] = "ios",
    ):
        data = get_dashboard_view(
            repo, date_str=date.isoformat() if date else None, country=country, platform=platform
        )
        return data["summary"]

    @app.get("/api/stats/monetization")
    def api_stats_monetization(
        date: Date | None = None,
        country: Literal[
            "all", "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "all",
        platform: Literal["ios", "android"] = "ios",
    ):
        data = get_dashboard_view(
            repo, date_str=date.isoformat() if date else None, country=country, platform=platform
        )
        return {
            "date": data["selected_date"],
            "country": data["selected_country"],
            "models_breakdown": data["summary"]
            .get("monetization_distribution", {})
            .get("breakdown", {}),
            "percentages": data["summary"]
            .get("monetization_distribution", {})
            .get("percentages", {}),
        }

    @app.get("/api/stats/heatmap")
    def api_stats_heatmap(date: Date | None = None, platform: Literal["ios", "android"] = "ios"):
        data = get_dashboard_view(
            repo, date_str=date.isoformat() if date else None, country="all", platform=platform
        )
        return data["heatmap"]

    @app.get("/api/stats/trends")
    def api_stats_trends(days: int = 7, platform: Literal["ios", "android"] = "ios"):
        data = get_dashboard_view(repo, country="all", platform=platform)
        return data["trends"]

    @app.get("/api/stats/radar")
    def api_stats_radar(
        date: Date | None = None,
        country: Literal[
            "all", "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "all",
        limit: int = 50,
        platform: Literal["ios", "android"] = "ios",
    ):
        data = get_dashboard_view(
            repo, date_str=date.isoformat() if date else None, country=country, platform=platform
        )
        return data["radar_items"][:limit]

    @app.get("/api/shortlist")
    def api_get_shortlist(status: str | None = None, priority: str | None = None):
        from casual_scout.stats.shortlist import ShortlistService

        service = ShortlistService(repo)
        return service.list_shortlists(status=status, priority=priority)

    @app.post("/api/shortlist")
    async def api_post_shortlist(request: Request):
        from casual_scout.stats.shortlist import ShortlistService

        body = await request.json()
        service = ShortlistService(repo)
        item = service.bookmark_game(
            app_id=str(body["app_id"]),
            title=body.get("title", str(body["app_id"])),
            primary_country=body.get("primary_country", "vn"),
            rank_at_bookmark=int(body.get("rank_at_bookmark", 100)),
            icon_url=body.get("icon_url"),
            developer=body.get("developer"),
            subgenre=body.get("subgenre"),
            mechanic=body.get("mechanic"),
            opportunity_score=body.get("opportunity_score"),
            notes=body.get("notes"),
            priority=body.get("priority", "MEDIUM"),
            tags=body.get("tags"),
        )
        return item

    @app.patch("/api/shortlist/{app_id}")
    async def api_patch_shortlist(app_id: str, request: Request):
        from casual_scout.stats.shortlist import ShortlistService

        body = await request.json()
        service = ShortlistService(repo)
        success = service.update_item(app_id, body)
        if not success:
            raise HTTPException(
                status_code=404, detail="Shortlist item not found or no valid updates"
            )
        updated = service.get_by_app_id(app_id)
        return updated

    @app.delete("/api/shortlist/{app_id}")
    def api_delete_shortlist(app_id: str):
        from casual_scout.stats.shortlist import ShortlistService

        service = ShortlistService(repo)
        success = service.remove_item(app_id)
        return {"success": success}

    @app.get("/api/export/shortlist")
    def api_export_shortlist(format: str = "csv"):
        from casual_scout.stats.exporter import export_shortlist_to_csv, export_to_json
        from casual_scout.stats.shortlist import ShortlistService

        service = ShortlistService(repo)
        items = service.list_shortlists()
        if format.lower() == "json":
            return Response(content=export_to_json(items), media_type="application/json")
        csv_data = export_shortlist_to_csv(items)
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=shortlist.csv"},
        )

    @app.get("/api/export/radar")
    def api_export_radar(
        date: Date | None = None,
        country: Literal[
            "all", "vn", "th", "id", "my", "ph", "sg", "la", "kh", "us", "bn", "mm", "tl"
        ] = "all",
        format: str = "csv",
        platform: Literal["ios", "android"] = "ios",
    ):
        from casual_scout.stats.exporter import export_radar_to_csv, export_to_json

        data = get_dashboard_view(
            repo, date_str=date.isoformat() if date else None, country=country, platform=platform
        )
        radar_items = data["radar_items"]
        if format.lower() == "json":
            return Response(content=export_to_json(radar_items), media_type="application/json")
        csv_data = export_radar_to_csv(radar_items)
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=radar_{data['selected_date']}.csv"
            },
        )

    return app
