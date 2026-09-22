# Web Daily Collection Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a running local web dashboard collect and analyze the iOS Top Free Vietnam chart on demand or once daily at 07:00 Asia/Ho_Chi_Minh, without routine CLI use.

**Architecture:** A SQLite singleton stores the enabled state and the last local date triggered. A pure scheduler service decides whether 07:00 is due, creates a `daily` Top Free VN run through `JobService`, and delegates collection plus analysis to a background pipeline process. FastAPI starts/stops the scheduler with the app and exposes CSRF-protected schedule controls; the dashboard renders its state and an immediate-crawl form.

**Tech Stack:** Python 3.12, SQLite WAL, FastAPI, Jinja2, `zoneinfo.ZoneInfo`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-web-daily-collection-scheduler-design.md`

## Global Constraints

- Schedule only iOS Apple **Top Free VN** at 07:00 `Asia/Ho_Chi_Minh`.
- The scheduler only runs while `casual_scout serve` is running; never backfill missed days.
- Persist `enabled` and the last triggered local date in SQLite.
- Reuse `collector_lock`/active-run behavior; never create a competing collection run.
- Schedule settings changes require existing local-origin and CSRF controls.
- A scheduled run must execute collect followed by analyze for VN.
- Leave Windows Task Scheduler and Top Grossing outside this feature.

---

### Task 1: Persist the single daily-schedule configuration

**Files:**
- Modify: `src/casual_scout/storage/schema.sql`
- Modify: `src/casual_scout/storage/repository.py`
- Test: `tests/test_scheduler_storage.py`

**Interfaces:**
- Produces `Repository.get_daily_schedule() -> dict[str, object]`.
- Produces `Repository.set_daily_schedule_enabled(enabled: bool) -> dict[str, object]`.
- Produces `Repository.claim_daily_schedule_date(local_date: str) -> bool` that atomically returns `True` once per date.

- [ ] **Step 1: Write the failing storage tests**

```python
def test_daily_schedule_defaults_disabled_and_claims_each_date_once(repo):
    schedule = repo.get_daily_schedule()
    assert schedule == {
        "enabled": False,
        "time": "07:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "country": "vn",
        "chart_type": "top-free",
        "last_triggered_local_date": None,
    }
    assert repo.claim_daily_schedule_date("2026-09-23") is True
    assert repo.claim_daily_schedule_date("2026-09-23") is False
    assert repo.claim_daily_schedule_date("2026-09-24") is True
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_scheduler_storage.py -v`

Expected: FAIL because the repository API does not exist.

- [ ] **Step 3: Add schema and repository methods**

Add one-row table to `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS daily_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    time_local TEXT NOT NULL DEFAULT '07:00' CHECK (time_local = '07:00'),
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    country TEXT NOT NULL DEFAULT 'vn' REFERENCES markets(country),
    chart_type TEXT NOT NULL DEFAULT 'top-free' CHECK (chart_type = 'top-free'),
    last_triggered_local_date TEXT,
    updated_at TEXT NOT NULL
);
```

In `Repository.initialize()`, insert `id=1` with `INSERT OR IGNORE`. Implement `claim_daily_schedule_date()` as a single conditional update:

```python
cursor = conn.execute(
    """UPDATE daily_schedule SET last_triggered_local_date = ?, updated_at = ?
       WHERE id = 1 AND (last_triggered_local_date IS NULL OR last_triggered_local_date <> ?)""",
    (local_date, now, local_date),
)
return cursor.rowcount == 1
```

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_scheduler_storage.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/storage/schema.sql src/casual_scout/storage/repository.py tests/test_scheduler_storage.py
git commit -m "feat: persist web daily schedule"
```

### Task 2: Run collection then analysis in a background pipeline process

**Files:**
- Modify: `src/casual_scout/collection/processes.py`
- Modify: `src/casual_scout/cli.py`
- Test: `tests/test_cli_pipeline.py`

**Interfaces:**
- Produces `launch_pipeline(run_id: str, data_dir: Path) -> int`.
- Adds `casual_scout pipeline --run-id <uuid> --data-dir <path>`.
- Pipeline calls `Collector.execute(run_id)` then `AnalysisService.analyze_date(today_utc, ["vn"])` only after collection is `succeeded` or `partial`.

- [ ] **Step 1: Write the failing CLI behavior test**

```python
def test_pipeline_analyzes_vn_after_a_successful_collection(tmp_path, monkeypatch):
    with patch("casual_scout.cli.Collector.execute", return_value="succeeded"), patch(
        "casual_scout.cli.AnalysisService.analyze_date"
    ) as analyze:
        rc = main(["pipeline", "--run-id", "run-1", "--data-dir", str(tmp_path)])
    assert rc == 0
    analyze.assert_called_once()
    assert analyze.call_args.args[1] == ["vn"]
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cli_pipeline.py -v`

Expected: FAIL because `pipeline` is not an argparse command.

- [ ] **Step 3: Implement the pipeline command and launcher**

Add the parser branch and invoke existing services. The command must return nonzero without analysis when the collector result is `failed` or `interrupted`.

Add `launch_pipeline()` in `collection/processes.py`, modeled on `launch_collector()` but invoking:

```python
[sys.executable, "-m", "casual_scout", "pipeline", "--run-id", run_id,
 "--data-dir", str(resolved_dir)]
```

Keep `shell=False`, the hidden Windows process flag, and per-run log file behavior.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cli_pipeline.py tests\test_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/cli.py src/casual_scout/collection/processes.py tests/test_cli_pipeline.py
git commit -m "feat: run collection and analysis as a pipeline"
```

### Task 3: Implement deterministic 07:00 scheduler decisions

**Files:**
- Create: `src/casual_scout/operations/daily_scheduler.py`
- Test: `tests/test_daily_scheduler.py`

**Interfaces:**
- Produces `DailyScheduler(repo: Repository, launch: Callable[[str, Path], int], now: Callable[[], datetime])`.
- Produces `DailyScheduler.check_once() -> str`, returning one of `"disabled"`, `"not_due"`, `"already_triggered"`, `"active_run"`, or a created run ID.
- Produces `DailyScheduler.start() -> None` and `DailyScheduler.stop() -> None` for the web lifecycle.

- [ ] **Step 1: Write failing decision tests**

```python
def test_check_once_launches_vn_pipeline_at_0700_local(repo, fake_launch):
    repo.set_daily_schedule_enabled(True)
    scheduler = DailyScheduler(repo, fake_launch, now=lambda: datetime(2026, 9, 23, 0, 0, tzinfo=UTC))
    run_id = scheduler.check_once()
    assert run_id.startswith("daily-") is False
    assert fake_launch.calls == [run_id]

def test_check_once_does_not_backfill_or_duplicate(repo, fake_launch):
    repo.set_daily_schedule_enabled(True)
    at_0659_vn = datetime(2026, 9, 22, 23, 59, tzinfo=UTC)
    assert DailyScheduler(repo, fake_launch, now=lambda: at_0659_vn).check_once() == "not_due"
    at_0700_vn = datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
    scheduler = DailyScheduler(repo, fake_launch, now=lambda: at_0700_vn)
    assert scheduler.check_once() not in {"not_due", "already_triggered"}
    assert scheduler.check_once() == "already_triggered"
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_daily_scheduler.py -v`

Expected: FAIL because `DailyScheduler` is missing.

- [ ] **Step 3: Implement scheduler with an injectable clock**

Use `ZoneInfo("Asia/Ho_Chi_Minh")`. `check_once()` must only act when `now_local.hour == 7 and now_local.minute == 0`; a server started after that minute returns `not_due`. Before submitting, check the schedule enabled flag and use `claim_daily_schedule_date(now_local.date().isoformat())`. Submit exactly:

```python
run_id = JobService(repo).submit("daily", ["vn"], f"daily-vn-{local_date}", chart_types=["top-free"])
```

If an active run exists, return `active_run` without claiming the date. `start()` runs a daemon thread that calls `check_once()` every 30 seconds; `stop()` signals and joins that thread.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_daily_scheduler.py tests\test_scheduler_storage.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/operations/daily_scheduler.py tests/test_daily_scheduler.py
git commit -m "feat: schedule daily web collection at 0700"
```

### Task 4: Expose schedule controls and immediate crawl through FastAPI

**Files:**
- Modify: `src/casual_scout/web/app.py`
- Modify: `src/casual_scout/web/views.py`
- Test: `tests/test_web_scheduler.py`

**Interfaces:**
- `GET /api/schedule` returns persisted schedule plus latest relevant run.
- `PATCH /api/schedule` accepts `{"enabled": true|false}` and requires valid CSRF/local origin.
- `POST /runs` accepts no user-provided chart type from Dashboard; it submits `["vn"]`, `chart_types=["top-free"]`, and uses `launch_pipeline`.

- [ ] **Step 1: Write failing API tests**

```python
def test_schedule_toggle_persists_with_valid_csrf(web_setup):
    _repo, client, _launcher, _calls = web_setup
    client.get("/dashboard")
    token = client.cookies["csrftoken"]
    response = client.patch("/api/schedule", headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": token}, json={"enabled": True})
    assert response.status_code == 200
    assert response.json()["enabled"] is True

def test_dashboard_crawl_submits_only_top_free_vn(web_setup):
    _repo, client, _launcher, calls = web_setup
    page = client.get("/dashboard")
    response = client.post("/runs", headers={"Origin": "http://127.0.0.1:8000"}, data={"csrf_token": client.cookies["csrftoken"]}, follow_redirects=False)
    assert response.status_code == 303
    assert len(calls) == 1
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_web_scheduler.py -v`

Expected: FAIL because `/api/schedule` is absent and manual runs do not use the pipeline launcher.

- [ ] **Step 3: Add lifecycle, API, and view state**

In `create_app()`, construct one `DailyScheduler(repo, launch_pipeline)` and start/stop it with FastAPI startup/shutdown handlers. Do not start a second scheduler under tests: inject a `scheduler_factory` into `create_app()` with a no-op fake in test setup.

Add CSRF validation for `PATCH /api/schedule`, reject bodies other than a JSON boolean `enabled`, persist with `set_daily_schedule_enabled()`, and return the stored configuration. Extend `get_dashboard_view()` with a `collection_status` object built from the newest `runs` row and `get_daily_schedule()`.

Update `/runs` to call `jobs.submit("manual", ["vn"], request_key, chart_types=["top-free"])` and `launch_pipeline()`.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_web.py tests\test_web_scheduler.py tests\test_web_security.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/web/app.py src/casual_scout/web/views.py tests/test_web_scheduler.py
git commit -m "feat: control daily collection from the web"
```

### Task 5: Render dashboard controls and document local operation

**Files:**
- Modify: `src/casual_scout/web/templates/dashboard.html`
- Modify: `README.md`
- Test: `tests/test_web_scheduler.py`

**Interfaces:**
- Dashboard consumes `collection_status` and the existing `csrf_token` context.
- The schedule toggle calls `PATCH /api/schedule`; the crawl form posts to `/runs`.

- [ ] **Step 1: Write the failing render test**

```python
def test_dashboard_shows_daily_schedule_and_crawl_control(web_setup):
    _repo, client, _launcher, _calls = web_setup
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Crawl ngay" in response.text
    assert "Mỗi ngày 07:00 (UTC+7)" in response.text
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_web_scheduler.py::test_dashboard_shows_daily_schedule_and_crawl_control -v`

Expected: FAIL because the controls are not rendered.

- [ ] **Step 3: Add minimal dashboard controls and operations guidance**

Add a dashboard card with a normal POST form containing the CSRF hidden input and `Crawl ngay` button. Add a checkbox/button for enabled state; JavaScript must send the current CSRF token in `X-CSRF-Token`, show an inline error on non-2xx, and refresh schedule status after success. Render latest run status, valid count when available, a link to `/runs`, and this exact operational warning: `Lịch chỉ chạy khi web server còn hoạt động.`

Update README with the serve command and explain that 07:00 scheduler is disabled by default and requires the web server to remain running.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_web_scheduler.py tests\test_web_stats.py -v`

Expected: PASS.

- [ ] **Step 5: Run full verification and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-web-scheduler -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check src tests
git add src/casual_scout/web/templates/dashboard.html README.md tests/test_web_scheduler.py
git commit -m "feat: add dashboard collection controls"
```

Expected: all tests pass; address any new Ruff findings in touched files before committing.
