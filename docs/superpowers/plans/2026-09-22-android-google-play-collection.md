# Android Google Play Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect Google Play Top Free Casual Vietnam from the web dashboard, preserve raw evidence and metadata, analyze Android ranks separately from iOS, and schedule both platforms sequentially at 07:00 Vietnam time.

**Architecture:** Add a `GooglePlayProvider` behind a provider registry and generalize collection identity to preserve provider/platform. Migrate analytics keys to include platform, then replace the single iOS scheduler with a persistent coordinator queue that dispatches iOS and Android workers one at a time. Dashboard is the only user-facing control surface; worker entry points remain internal subprocess mechanics.

**Tech Stack:** Python 3.12, FastAPI/Jinja, SQLite WAL, pytest, Ruff, stdlib HTML parsing, existing `HttpClient`/raw store.

**Spec:** `docs/superpowers/specs/2026-09-22-android-google-play-collection-design.md`

## Global Constraints

- Support only Google Play Android `GAME_CASUAL` Top Free Vietnam (`gl=VN`, `hl=vi`) in this MVP.
- Collect every valid item the public page exposes; store actual received/valid counts and never claim Top 100.
- Do not use paid APIs, Developer API, login, CAPTCHA bypass, geo-bypass, or Windows Task Scheduler.
- Persist raw HTML and request observations; unknown ads/IAP must remain unknown rather than false.
- Scheduler runs only while `serve` runs, never backfills a missed 07:00 slot, and never starts concurrent collector workers.
- Preserve iOS behavior and default existing user-facing views to iOS.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/casual_scout/models.py` | Provider-neutral chart and metadata-fetch value objects. |
| `src/casual_scout/providers/base.py` | `MarketProvider` protocol and provider registry factory. |
| `src/casual_scout/providers/google_play.py` | Google Play chart/metadata HTTP and HTML parsing. |
| `src/casual_scout/providers/apple.py` | Adapt Apple metadata output to the common provider protocol. |
| `src/casual_scout/collection/jobs.py` | Submit explicit `Chart` objects and preserve existing iOS adapter. |
| `src/casual_scout/collection/service.py` | Rebuild complete chart identity, select provider, persist per-app metadata evidence. |
| `src/casual_scout/storage/schema.sql` | New schedule/queue tables and v2 analytics schemas. |
| `src/casual_scout/storage/repository.py` | Idempotent SQLite migrations, platform-scoped data methods, queue persistence. |
| `src/casual_scout/analysis/service.py` | Platform-context analysis and Android-safe rank calculations. |
| `src/casual_scout/operations/daily_coordinator.py` | Persistent iOS→Android queue coordinator. |
| `src/casual_scout/collection/processes.py` | Internal Android worker launcher. |
| `src/casual_scout/cli.py` | Hidden/internal `android-work` worker dispatch only. |
| `src/casual_scout/web/app.py` | Coordinator lifespan, Android schedule/API/run routes. |
| `src/casual_scout/web/views.py` | Platform-aware data/dashboard/game query contexts. |
| `src/casual_scout/web/templates/*.html` | Android collection card and platform selector. |

### Task 1: Make models and provider dispatch platform-aware

**Files:**
- Create: `src/casual_scout/providers/base.py`
- Modify: `src/casual_scout/models.py`
- Modify: `src/casual_scout/providers/apple.py`
- Test: `tests/test_provider_registry.py`

**Interfaces:**
- Produces `MetadataFetch(app_id: str, result: HttpResult, values: dict[str, object] | None)`.
- Produces `MarketProvider` with `fetch_chart(chart)` and `fetch_metadata(country, app_ids) -> list[MetadataFetch]`.
- Produces `provider_for(chart: Chart, settings: Settings) -> MarketProvider`.

- [ ] **Step 1: Write failing model/registry tests**

```python
def test_android_chart_preserves_google_play_identity() -> None:
    chart = Chart("vn", provider="google-play", platform="android",
                  collection="top-free-casual", genre="GAME_CASUAL")
    assert chart.collection == "top-free-casual"
    assert chart.genre == "GAME_CASUAL"

def test_provider_registry_rejects_unknown_pair(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported provider/platform"):
        provider_for(Chart("vn", provider="unknown", platform="android"), Settings(tmp_path))
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_provider_registry.py -q --basetemp .test-tmp-android-task1-red -p no:cacheprovider`

Expected: `Chart` rewrites Android collection to Apple Top Free and `provider_for` is unavailable.

- [ ] **Step 3: Implement neutral model/protocol boundary**

```python
@dataclass(frozen=True, slots=True)
class MetadataFetch:
    app_id: str
    result: HttpResult
    values: dict[str, object] | None

def provider_for(chart: Chart, settings: Settings) -> MarketProvider:
    try:
        return PROVIDERS[(chart.provider, chart.platform)](settings)
    except KeyError as error:
        raise ValueError(f"unsupported provider/platform: {chart.provider}/{chart.platform}") from error
```

Make `Chart.__post_init__()` normalize only `provider == "apple"`. Adapt `AppleProvider.fetch_metadata()` to return one `MetadataFetch` per requested app, sharing the Apple batch response while retaining the parsed values for that app.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_provider_registry.py tests/test_apple.py -q --basetemp .test-tmp-android-task1-green -p no:cacheprovider`

Expected: provider registry tests and Apple regression tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/models.py src/casual_scout/providers/base.py src/casual_scout/providers/apple.py tests/test_provider_registry.py
git commit -m "refactor: add platform provider registry"
```

### Task 2: Implement evidence-backed Google Play parser and metadata provider

**Files:**
- Create: `src/casual_scout/providers/google_play.py`
- Create: `tests/fixtures/google-play/vn-casual-top-free.html`
- Create: `tests/fixtures/google-play/vn-casual-malformed.html`
- Create: `tests/fixtures/google-play/app-with-monetization.html`
- Create: `tests/fixtures/google-play/app-unknown-monetization.html`
- Test: `tests/test_google_play.py`

**Interfaces:**
- Produces `GooglePlayProvider.fetch_chart()` with `Chart(provider="google-play", platform="android")` only.
- Produces `GooglePlayProvider.fetch_metadata()` returning one `MetadataFetch` per input package.
- Consumes `HttpClient` through injectable `SupportsGet` for deterministic tests.

- [ ] **Step 1: Write failing parser/provider tests**

```python
def test_parse_google_play_top_free_casual_chart(evidence_dir) -> None:
    parsed = parse_google_play_chart((evidence_dir / "vn-casual-top-free.html").read_bytes(), android_chart())
    assert [(e.app_id, e.rank) for e in parsed.entries] == [
        ("com.example.alpha", 1), ("com.example.beta", 2), ("com.example.gamma", 3)
    ]
    assert parsed.quality == "complete"

def test_parser_marks_missing_section_invalid(evidence_dir) -> None:
    parsed = parse_google_play_chart((evidence_dir / "vn-casual-malformed.html").read_bytes(), android_chart())
    assert parsed.quality == "invalid"
    assert parsed.issues == ["top_free_casual_section_missing"]
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_google_play.py -q --basetemp .test-tmp-android-task2-red -p no:cacheprovider`

Expected: import fails because Google Play provider/parser does not exist.

- [ ] **Step 3: Implement parser and guarded requests**

Implement constants `GOOGLE_PLAY_CASUAL_URL`, `_PACKAGE_RE`, a standard request header map, and `parse_google_play_chart(body, chart)`. Locate the Top Free section by its semantic heading and app-detail links rather than CSS classes; strip duplicate package links and assign ranks after validation. Use `HttpClient` retry behavior and reject 403/login/captcha HTML with an invalid `ParsedChart` issue.

Implement metadata parsing so output values always include:

```python
{
    "name": name_or_none,
    "developer": developer_or_none,
    "genres": genres,
    "description": description_or_none,
    "averageUserRating": rating_or_none,
    "userRatingCount": rating_count_or_none,
    "trackViewUrl": canonical_url,
    "price": price_or_none,
    "currency": currency_or_none,
    "inAppPurchases": [],
    "ads_observed": True | False | None,
    "iap_observed": True | False | None,
}
```

Set `has_in_app_purchases` only when `iap_observed is True`; preserve unknown as `None` in `values_json`.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_google_play.py -q --basetemp .test-tmp-android-task2-green -p no:cacheprovider`

Expected: fixtures verify rank/package parsing, malformed evidence behavior, duplicate suppression, and ads/IAP observation states.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/providers/google_play.py tests/test_google_play.py tests/fixtures/google-play
git commit -m "feat: collect Google Play casual charts"
```

### Task 3: Generalize collection and metadata persistence without losing Apple evidence

**Files:**
- Modify: `src/casual_scout/collection/jobs.py`
- Modify: `src/casual_scout/collection/service.py`
- Modify: `src/casual_scout/storage/repository.py`
- Test: `tests/test_collection_platforms.py`
- Test: `tests/test_metadata.py`

**Interfaces:**
- Produces `JobService.submit_charts(trigger: str, charts: list[Chart], request_key: str) -> str`.
- Keeps `JobService.submit()` as an iOS-compatible adapter.
- `Collector.execute()` selects provider by full chart identity and saves each `MetadataFetch.result` separately.

- [ ] **Step 1: Write failing cross-platform collection tests**

```python
def test_collector_keeps_ios_and_android_same_source_id_separate(repo, fake_providers) -> None:
    run_id = JobService(repo).submit_charts("manual", [ios_chart("123"), android_chart("123")], "dual-id")
    assert Collector(repo, fake_providers, JobService(repo)).execute(run_id) == "succeeded"
    with repo._connect() as connection:
        assert connection.execute("SELECT count(*) FROM apps WHERE source_app_id = '123'").fetchone()[0] == 2

def test_android_metadata_failure_keeps_chart_and_marks_partial(repo, android_partial_provider) -> None:
    run_id = JobService(repo).submit_charts("manual", [android_chart()], "android-partial")
    assert Collector(repo, android_partial_provider, JobService(repo)).execute(run_id) == "partial"
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_collection_platforms.py -q --basetemp .test-tmp-android-task3-red -p no:cacheprovider`

Expected: `submit_charts` is absent and collector reconstructs charts as Apple/iOS.

- [ ] **Step 3: Implement platform-neutral collection**

Persist every `Chart` field in `JobService.submit_charts()` and generate endpoints with the selected provider instead of Apple RSS strings. In `Collector`, select `c.provider` and `c.platform` in the market-run query, reconstruct `Chart` with those values, and resolve the provider through the registry. Replace one batch metadata save with a loop over `MetadataFetch`: call `save_metadata(country, {fetch.app_id: fetch.values}, fetch.result)` only for non-null body/values; then bind cached/new versions exactly as today.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_collection_platforms.py tests/test_collection.py tests/test_metadata.py -q --basetemp .test-tmp-android-task3-green -p no:cacheprovider`

Expected: Android evidence is stored separately, partial metadata preserves chart snapshot, and existing iOS tests remain green.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/collection/jobs.py src/casual_scout/collection/service.py src/casual_scout/storage/repository.py tests/test_collection_platforms.py tests/test_metadata.py
git commit -m "refactor: collect charts by provider platform"
```

### Task 4: Migrate canonical and analytics storage to platform-scoped keys

**Files:**
- Modify: `src/casual_scout/storage/schema.sql`
- Modify: `src/casual_scout/storage/repository.py`
- Modify: `src/casual_scout/analysis/service.py`
- Test: `tests/test_platform_analytics_migration.py`
- Test: `tests/test_analysis_service.py`

**Interfaces:**
- `get_canonical_snapshot(date_str: str, country: str, *, provider: str, platform: str, collection: str) -> dict[str, Any] | None` and `save_canonical_snapshot(date_str: str, country: str, snapshot_id: str, observed_at: str, *, provider: str, platform: str, collection: str) -> None` use full context.
- `find_latest_complete_snapshot_for_date(date_str: str, country: str, *, provider: str, platform: str, collection: str) -> dict[str, Any] | None` filters by full identity.
- `save_daily_analytics(records: list[dict[str, Any]]) -> None` writes provider/platform per record.
- `AnalysisService.analyze_date(date_str: str, countries: list[str] | None = None, *, provider: str = "apple", platform: str = "ios", collection: str = "topfreeapplications") -> dict[str, object]`.

- [ ] **Step 1: Write failing migration and analysis isolation tests**

```python
def test_initialize_migrates_legacy_ios_analytics_and_accepts_android_same_id(tmp_path) -> None:
    create_pre_platform_analytics_database(tmp_path)
    repository = Repository(tmp_path)
    repository.initialize()
    assert repository.get_daily_analytics("2026-09-22", "vn", platform="ios")[0]["provider"] == "apple"
    repository.save_daily_analytics([android_record(app_id="123", date="2026-09-22")])
    assert len(repository.get_daily_analytics("2026-09-22", "vn", platform="all")) == 2
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_platform_analytics_migration.py -q --basetemp .test-tmp-android-task4-red -p no:cacheprovider`

Expected: legacy table cannot accept duplicate `(date, country, app_id)` and platform query APIs are absent.

- [ ] **Step 3: Implement idempotent v2 migration and contextual analysis**

Create replacement canonical/analytics tables, copy every legacy row as Apple/iOS, swap only after copy succeeds inside a write transaction, and recreate all indexes. Add `provider/platform/collection` parameters to repository reads and thread them through analysis current/past/canonical logic. Android analysis passes Google Play context and skips grossing lookup; never generate a grossing rank for Android.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_platform_analytics_migration.py tests/test_analysis_service.py tests/test_monetization_storage.py -q --basetemp .test-tmp-android-task4-green -p no:cacheprovider`

Expected: legacy values remain queryable as iOS, Android same app ID/date is isolated, and iOS grossing analytics regressions pass.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/storage/schema.sql src/casual_scout/storage/repository.py src/casual_scout/analysis/service.py tests/test_platform_analytics_migration.py tests/test_analysis_service.py
git commit -m "feat: scope analytics by platform"
```

### Task 5: Add persisted Android schedule and sequential dispatch coordinator

**Files:**
- Create: `src/casual_scout/operations/daily_coordinator.py`
- Modify: `src/casual_scout/storage/schema.sql`
- Modify: `src/casual_scout/storage/repository.py`
- Modify: `src/casual_scout/collection/processes.py`
- Test: `tests/test_daily_coordinator.py`
- Test: `tests/test_android_schedule_storage.py`

**Interfaces:**
- Produces `get_android_daily_schedule()`, `set_android_daily_schedule_enabled(bool)`, and atomic daily queue repository methods.
- Produces `DailyCollectionCoordinator(repo, launch_ios, launch_android, now)` with `check_once()`, `enqueue_android_manual(request_key)`, `start()`, and `stop()`.

- [ ] **Step 1: Write failing schedule/queue tests**

```python
def test_coordinator_dispatches_ios_then_android_at_seven(tmp_path) -> None:
    repo = initialized_repo_with_both_schedules_enabled(tmp_path)
    launched: list[tuple[str, str]] = []
    coordinator = DailyCollectionCoordinator(repo, ios_launcher(launched), android_launcher(launched), now=at_vn_0700())
    coordinator.check_once()
    assert [row["platform"] for row in repo.daily_queue("2026-09-22")] == ["ios", "android"]
    assert launched == [("ios", repo.daily_queue("2026-09-22")[0]["run_id"])]

def test_android_dispatches_after_failed_ios_and_restart(tmp_path) -> None:
    repo = initialized_repo_with_both_schedules_enabled(tmp_path)
    first = DailyCollectionCoordinator(repo, ios_launcher([]), android_launcher([]), now=at_vn_0700())
    first.check_once()
    ios_run_id = repo.daily_queue("2026-09-22")[0]["run_id"]
    JobService(repo).finish(ios_run_id, "failed", {"error": "fixture"})
    launched: list[tuple[str, str]] = []
    restarted = DailyCollectionCoordinator(repo, ios_launcher(launched), android_launcher(launched), now=at_vn_0701())
    restarted.check_once()
    assert launched[0][0] == "android"
    assert len(repo.daily_queue("2026-09-22")) == 2
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_android_schedule_storage.py tests/test_daily_coordinator.py -q --basetemp .test-tmp-android-task5-red -p no:cacheprovider`

Expected: Android schedule/queue tables and coordinator do not exist.

- [ ] **Step 3: Implement schedule persistence and coordinator state machine**

Initialize one Android schedule row disabled at 07:00. Add `daily_dispatch_queue` methods that insert with `INSERT OR IGNORE`, select oldest pending using `BEGIN IMMEDIATE`, store a run ID only once, and mark dispatched rows terminal when linked run terminal. At exact local 07:00, claim enabled schedules and enqueue iOS before Android. On every 30-second tick, settle dispatched rows then dispatch one pending item only when no active run exists. Android manual enqueue returns its existing queued/running Android run. Launch only after transaction commit; on exception finish run as failed and terminalize queue.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_android_schedule_storage.py tests/test_daily_coordinator.py tests/test_daily_scheduler.py -q --basetemp .test-tmp-android-task5-green -p no:cacheprovider`

Expected: no backfill, exactly one daily entry/platform, iOS then Android sequencing, failed-iOS continuation, restart recovery, and legacy iOS scheduler behavior transition tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/operations/daily_coordinator.py src/casual_scout/storage/schema.sql src/casual_scout/storage/repository.py src/casual_scout/collection/processes.py tests/test_android_schedule_storage.py tests/test_daily_coordinator.py
git commit -m "feat: queue daily iOS and Android collection"
```

### Task 6: Wire internal Android worker and platform analysis pipeline

**Files:**
- Modify: `src/casual_scout/cli.py`
- Modify: `src/casual_scout/collection/processes.py`
- Test: `tests/test_android_worker.py`

**Interfaces:**
- Internal command `android-work --run-id UUID --data-dir PATH` is invoked only by `launch_android_pipeline()`.
- Worker executes `Collector` for Android then `AnalysisService.analyze_date(date_str, ["vn"], provider="google-play", platform="android", collection="top-free-casual")` only after `succeeded`/`partial`.

- [ ] **Step 1: Write failing internal-worker tests**

```python
def test_android_worker_runs_android_analysis_after_partial_collection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "Collector", PartialAndroidCollector)
    monkeypatch.setattr(cli, "AnalysisService", RecordingAnalysis)
    assert cli.main(["android-work", "--run-id", "run-1", "--data-dir", str(tmp_path)]) == 0
    assert RecordingAnalysis.calls == [("google-play", "android", "top-free-casual", ["vn"])]
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_android_worker.py -q --basetemp .test-tmp-android-task6-red -p no:cacheprovider`

Expected: parser rejects internal `android-work` command.

- [ ] **Step 3: Implement internal worker/launcher**

Add a non-documented parser command and `launch_android_pipeline()` using the existing detached process/log convention. Resolve `GooglePlayProvider`, execute one Android run, and analyze only after successful or partial terminal collection. Never add the command to README or Dashboard copy.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_android_worker.py tests/test_cli_pipeline.py -q --basetemp .test-tmp-android-task6-green -p no:cacheprovider`

Expected: Android worker passes context correctly and iOS pipeline remains unchanged.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/cli.py src/casual_scout/collection/processes.py tests/test_android_worker.py
git commit -m "feat: run Android collection worker internally"
```

### Task 7: Add Android web controls and platform-safe views

**Files:**
- Modify: `src/casual_scout/web/app.py`
- Modify: `src/casual_scout/web/views.py`
- Modify: `src/casual_scout/web/templates/dashboard.html`
- Modify: `src/casual_scout/web/templates/data.html`
- Modify: `src/casual_scout/web/templates/game.html`
- Test: `tests/test_web_android.py`

**Interfaces:**
- `GET/PATCH /api/android/schedule` and `POST /android/runs` enforce local origin + CSRF.
- `get_data_view(repo: Repository, country: str = "vn", feed_type: str = "top-free", snapshot_id: str | None = None, signal: str | None = None, date: str | None = None, platform: str = "ios") -> dict[str, Any]` and `get_dashboard_view(repo: Repository, date_str: str | None = None, country: str = "all", platform: str = "ios") -> dict[str, Any]` validate `ios|android|all`.

- [ ] **Step 1: Write failing FastAPI/render tests**

```python
def test_android_schedule_toggle_requires_csrf_and_persists(web_setup) -> None:
    _repo, client, _launcher, _calls = web_setup
    assert client.patch("/api/android/schedule", json={"enabled": True}).status_code == 403
    token = obtain_dashboard_csrf(client)
    response = client.patch("/api/android/schedule", headers=csrf_headers(token), json={"enabled": True})
    assert response.json()["enabled"] is True

def test_dashboard_android_crawl_uses_fixed_chart_and_platform_filter(web_setup) -> None:
    page = web_setup.client.get("/dashboard?platform=android")
    assert "Crawl Android ngay" in page.text
    assert 'name="platform" value="android"' in page.text
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_android.py -q --basetemp .test-tmp-android-task7-red -p no:cacheprovider`

Expected: Android routes/card and platform argument are unavailable.

- [ ] **Step 3: Implement API, lifespan and UI**

Replace `DailyScheduler` construction in `create_app()` with `DailyCollectionCoordinator`, injecting fake coordinator/launchers in tests. Implement Android schedule GET/PATCH and manual POST with fixed Google Play chart. Add a Dashboard card that shows schedule/run/queue status, disabled crawl control only while Android is active, CSRF toggle and the required running-server warning. Thread platform through data/dashboard/game views and SQL joins. Default platform remains iOS; `all` renders tagged independent rows rather than merged analytics.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_android.py tests/test_web.py tests/test_web_security.py -q --basetemp .test-tmp-android-task7-green -p no:cacheprovider`

Expected: Android controls work with CSRF, iOS defaults remain intact, and all-platform views keep records separated.

- [ ] **Step 5: Commit**

```powershell
git add src/casual_scout/web/app.py src/casual_scout/web/views.py src/casual_scout/web/templates/dashboard.html src/casual_scout/web/templates/data.html src/casual_scout/web/templates/game.html tests/test_web_android.py
git commit -m "feat: control Android collection from dashboard"
```

### Task 8: Document operation and perform full acceptance verification

**Files:**
- Modify: `README.md`
- Create: `docs/operations/android-collection-acceptance.md`
- Test: `tests/test_android_acceptance.py`

**Interfaces:**
- User-facing documentation exposes only the web server command and Dashboard controls.
- Acceptance test proves raw chart/metadata evidence, Android analysis isolation, and no iOS regression.

- [ ] **Step 1: Write failing end-to-end acceptance test**

```python
def test_android_vn_collection_preserves_evidence_and_does_not_mix_ios(tmp_path, google_play_fixture_provider) -> None:
    repo, run_id = run_android_pipeline(tmp_path, google_play_fixture_provider)
    assert repo.get_snapshot_for_run(run_id)["chart"]["platform"] == "android"
    assert repo.get_snapshot_metadata_for_run(run_id)
    assert android_analytics(repo, "2026-09-22")[0]["platform"] == "android"
    assert ios_analytics(repo, "2026-09-22") == []
```

- [ ] **Step 2: Verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_android_acceptance.py -q --basetemp .test-tmp-android-task8-red -p no:cacheprovider`

Expected: acceptance helpers and Android provider pipeline are absent until prior tasks land.

- [ ] **Step 3: Add operation guidance and acceptance evidence**

Document only:

```powershell
python -m casual_scout.cli serve --host 127.0.0.1 --port 8000 --data-dir .\data
```

Explain Android schedule is disabled by default, runs sequentially after iOS at 07:00 only while server runs, and uses Google Play public data with variable list depth. Add the acceptance report with commands, observed expected states, and explicit non-claims for downloads/revenue.

- [ ] **Step 4: Verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest -q --basetemp .test-tmp-android-final -p no:cacheprovider`

Expected: complete suite passes without failures.

Run: `./.venv/Scripts/python.exe -m ruff check src tests`

Expected: no new lint errors in Android-touched files; document any existing unrelated lint debt separately.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/operations/android-collection-acceptance.md tests/test_android_acceptance.py
git commit -m "docs: add Android collection operation guide"
```

## Plan Self-Review

- Spec coverage: Tasks 1–3 cover provider identity, public HTML, evidence and metadata; Task 4 isolates analytics; Tasks 5–6 cover sequential scheduling/internal worker; Task 7 covers CSRF/UI/platform filtering; Task 8 covers operation and acceptance evidence.
- Placeholder scan: no unresolved design placeholders; every implementation task includes a concrete test, command, implementation contract and commit.
- Type consistency: provider key is `("google-play", "android")`; Android collection is `top-free-casual`; Android scheduler table is `android_daily_schedule`; queue table is `daily_dispatch_queue`; analysis context uses provider/platform/collection consistently.
