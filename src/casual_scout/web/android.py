from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request

from casual_scout.android.coordinator import dispatch_pending, launch_android


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
    def page(request: Request):
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
        job_id = store.enqueue()
        dispatch_pending(store, launcher)
        return {"job_id": job_id}

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
