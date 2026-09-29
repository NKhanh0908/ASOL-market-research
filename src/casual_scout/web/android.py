from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from casual_scout.android.coordinator import launch_android
from casual_scout.collection.jobs import CollectionBusyError, JobService


def android_router(store, templates, security, launcher=launch_android):
    router = APIRouter()

    def csrf(request):
        if not security.validate_csrf_token(
            request.headers.get("X-CSRF-Token", ""), request.cookies.get("session_id", "")
        ):
            raise HTTPException(403, "Invalid CSRF token")
        if (store.repo.data_dir / "MOCK_DATA.json").exists():
            raise HTTPException(403, "Mock demo is read-only")

    @router.get("/android")
    def page(request: Request, job_id: str | None = None):
        if job_id is None:
            return RedirectResponse("/data?platform=android", status_code=303)
        session = request.cookies.get("session_id") or secrets.token_hex(16)
        token = security.generate_csrf_token(session)
        response = templates.TemplateResponse(
            request=request,
            name="android.html",
            context={
                "request": request,
                "active_tab": "android",
                "csrf_token": token,
            },
        )
        response.set_cookie("session_id", session, httponly=True, samesite="strict")
        response.set_cookie("csrftoken", token, samesite="strict")
        return response

    @router.get("/api/android/data")
    def data(job_id: str | None = None):
        try:
            return store.view(job_id)
        except KeyError as error:
            raise HTTPException(404, "Android run not found") from error

    @router.post("/api/android/runs", status_code=202)
    def create_run(request: Request):
        csrf(request)
        jobs = JobService(store.repo)
        try:
            job_id = jobs.submit(
                "manual",
                ["vn", "th", "id", "my", "ph", "sg", "la", "kh", "us"],
                f"android-web-{secrets.token_hex(16)}",
                ["top-free", "top-grossing"],
                platform="android",
            )
            jobs.launch(job_id, launcher)
        except CollectionBusyError as error:
            raise HTTPException(409, str(error)) from error
        except Exception as error:
            raise HTTPException(503, "Worker launch failed") from error
        return {"job_id": job_id, "run_id": job_id}

    @router.get("/api/android/schedule")
    def schedule():
        return {**store.view()["schedule"], "time": "07:00", "timezone": "Asia/Ho_Chi_Minh"}

    @router.patch("/api/android/schedule")
    async def update_schedule(request: Request):
        csrf(request)
        try:
            body = await request.json()
        except ValueError as error:
            raise HTTPException(422, "JSON body required") from error
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            raise HTTPException(422, "enabled must be a boolean")
        store.set_schedule(body["enabled"])
        return schedule()

    return router
