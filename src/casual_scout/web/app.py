from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from casual_scout.android.coordinator import AndroidCoordinator, launch_android
from casual_scout.android.storage import AndroidStore
from casual_scout.collection.jobs import JobService
from casual_scout.collection.processes import launch_pipeline
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.android import android_router
from casual_scout.web.security import (
    LocalOriginMiddleware,
    SecurityManager,
    allowed_hosts,
    get_or_create_secret,
)
from casual_scout.web.views import (
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
        scheduler.start()
        try:
            yield
        finally:
            scheduler.stop()

    app = FastAPI(title="Casual Scout", lifespan=lifespan)

    secret = get_or_create_secret(settings.data_dir)
    sec_mgr = SecurityManager(secret)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts(),
    )
    app.add_middleware(LocalOriginMiddleware, hosts=allowed_hosts())

    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))
    templates.env.autoescape = True
    templates.env.globals["mock_demo"] = (settings.data_dir / "MOCK_DATA.json").is_file()
    app.include_router(android_router(android_store, templates, sec_mgr, android_launcher))

    static_dir = Path(__file__).parent / "static"
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
        country: str = "vn",
        feed_type: str = "top-free",
        snapshot_id: str | None = None,
        signal: str | None = None,
        date: str | None = None,
    ):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)

        data = get_data_view(
            repo,
            country=country,
            feed_type=feed_type,
            snapshot_id=snapshot_id,
            signal=signal,
            date=date,
        )
        context = {
            "request": request,
            "active_tab": "data",
            "csrf_token": csrf_token,
            "now_key": str(uuid4())[:8],
            **data,
        }
        rendered = templates.TemplateResponse(
            request=request, name="data.html", context=context
        )
        _attach_cookies(rendered, session_id, is_new, csrf_token)
        return rendered

    @app.post("/runs")
    def post_runs(
        request: Request,
        country: str = Form(default="vn"),
        request_key: str = Form(default=""),
        csrf_token: str = Form(default=""),
    ):
        session_id = request.cookies.get("session_id") or ""
        if not sec_mgr.validate_csrf_token(csrf_token, session_id):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        if country == "all":
            countries = _ALL_MARKETS
        else:
            countries = [c.strip().lower() for c in country.split(",") if c.strip()]

        if not request_key:
            request_key = f"web-{uuid4()}"

        run_id = jobs.submit("manual", countries, request_key)

        with closing(repo._connect()) as connection:
            android_run = connection.execute('SELECT id FROM android_jobs WHERE core_run_id=?', (run_id,)).fetchone()
        if android_run:
            return RedirectResponse(f'/android?job_id={run_id}', status_code=303)

        # Check if run needs launching
        with closing(repo._connect()) as conn:
            lock = conn.execute("SELECT * FROM collector_lock WHERE run_id = ?", (run_id,)).fetchone()
            run_row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()

        if run_row and run_row["status"] == "queued" and lock is None:
            launcher(run_id, settings.data_dir)

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
            row = conn.execute("SELECT id, status, ended_at FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Run not found")
        return {
            "id": str(row["id"]),
            "status": str(row["status"]),
            "ended_at": str(row["ended_at"]) if row["ended_at"] else None,
        }

    @app.get("/api/charts/grossing")
    def grossing_chart_endpoint(country: str = "vn", date: str | None = None):
        if not date:
            raise HTTPException(status_code=400, detail="date is required")

        snapshot_ref = repo.find_latest_complete_snapshot_for_date(
            date, country, collection="topgrossingapplications"
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
            raise HTTPException(status_code=422, detail="scheduled_for must be an ISO datetime") from exc

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
        country: str = "vn",
        snapshot_id: str | None = None,
    ):
        session_id, is_new = _get_or_create_session(request)

        game = get_game_view(repo, app_id, country=country, snapshot_id=snapshot_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        context = {
            "request": request,
            "active_tab": "data",
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
        country: str = "vn",
        snapshot_id: str | None = None,
        date: str | None = None,
        signal: str | None = None,
    ):
        data = get_data_view(repo, country=country, snapshot_id=snapshot_id, signal=signal, date=date)
        entries = data.get("entries", [])
        if not entries:
            raise HTTPException(status_code=404, detail="No data available for download")

        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
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
            "developer",
            "rating",
            "store_url",
        ])
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
                    e.get("developer"),
                    e.get("rating_display"),
                    e.get("store_url"),
                ]
            )

        csv_content = output.getvalue()
        date_str = date or (data.get("selected_snapshot", {}).get("observed_at", "")[:10] if data.get("selected_snapshot") else "today")
        return Response(
            content=csv_content.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="casual-scout-{country}-{date_str}.csv"'},
        )

    
    # ------------------ Phase 3 Dashboard & Shortlist Views ------------------

    @app.get("/dashboard")
    def dashboard_view(
        request: Request,
        date: str | None = None,
        country: str = "all",
    ):
        session_id, is_new = _get_or_create_session(request)
        csrf_token = sec_mgr.generate_csrf_token(session_id)
        
        data = get_dashboard_view(repo, date_str=date, country=country)
        data["daily_schedule"] = repo.get_daily_schedule()
        context = {
            "request": request,
            "active_tab": "dashboard",
            "csrf_token": csrf_token,
            **data,
        }
        resp = templates.TemplateResponse(
            request=request, name="dashboard.html", context=context
        )
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
        resp = templates.TemplateResponse(
            request=request, name="shortlist.html", context=context
        )
        _attach_cookies(resp, session_id, is_new, csrf_token=csrf_token)
        return resp

    # ------------------ Phase 3 REST APIs & Export ------------------

    @app.get("/api/stats/summary")
    def api_stats_summary(date: str | None = None, country: str = "all"):
        data = get_dashboard_view(repo, date_str=date, country=country)
        return data["summary"]

    @app.get("/api/stats/monetization")
    def api_stats_monetization(date: str | None = None, country: str = "all"):
        data = get_dashboard_view(repo, date_str=date, country=country)
        return {
            "date": data["selected_date"],
            "country": data["selected_country"],
            "models_breakdown": data["summary"].get("monetization_distribution", {}).get("breakdown", {}),
            "percentages": data["summary"].get("monetization_distribution", {}).get("percentages", {}),
        }

    @app.get("/api/stats/heatmap")
    def api_stats_heatmap(date: str | None = None):
        data = get_dashboard_view(repo, date_str=date, country="all")
        return data["heatmap"]

    @app.get("/api/stats/trends")
    def api_stats_trends(days: int = 7):
        data = get_dashboard_view(repo, country="all")
        return data["trends"]

    @app.get("/api/stats/radar")
    def api_stats_radar(date: str | None = None, country: str = "all", limit: int = 50):
        data = get_dashboard_view(repo, date_str=date, country=country)
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
            raise HTTPException(status_code=404, detail="Shortlist item not found or no valid updates")
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
            headers={"Content-Disposition": "attachment; filename=shortlist.csv"}
        )

    @app.get("/api/export/radar")
    def api_export_radar(date: str | None = None, country: str = "all", format: str = "csv"):
        from casual_scout.stats.exporter import export_radar_to_csv, export_to_json
        data = get_dashboard_view(repo, date_str=date, country=country)
        radar_items = data["radar_items"]
        if format.lower() == "json":
            return Response(content=export_to_json(radar_items), media_type="application/json")
        csv_data = export_radar_to_csv(radar_items)
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=radar_{data['selected_date']}.csv"}
        )

    return app
