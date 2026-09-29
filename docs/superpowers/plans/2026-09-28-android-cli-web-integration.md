# Android CLI and Web Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép chọn iOS/Android trong CLI, dashboard và API, với crawl đúng nền tảng, installs badges, game detail và radar v1.5.

**Architecture:** CLI và web cùng tạo core JobService runs và chạy pipeline theo platform của charts đã lưu. Read models truyền platform từ route đến SQL và analytics; Jinja dùng URL query để duy trì lựa chọn. Android legacy giữ lịch sử nhưng không còn tạo crawl Selenium mới sau cutover.

**Tech Stack:** Python 3.12, argparse, FastAPI, Pydantic 2, Jinja2, SQLite, existing CSS/JavaScript, pytest/TestClient.

**Spec:** [SPEC-AND-03](../specs/2026-09-28-android-cli-web-integration-spec.md)

## Execution status — 2026-09-29

Authoritative progress: [platform acceptance](../../operations/2026-09-28-android-platform-acceptance.md).
The user accepted operational partial charts and measured crawl times on 2026-09-29.
Original step recipes remain below; separate RED/commit executions are not implied.

- [x] Task 1: platform CLI flags, shared dispatch and sequential `all` verified.
- [x] Task 2: platform/date/snapshot read scope and historical evidence verified.
- [x] Task 3: validated JSON API, CSRF/origin, scope idempotency, single launch and recovery verified.
- [x] Task 4 implementation: switchers, installs, radar v1.5 and 14-day dual game history delivered.
- [x] Task 5: HTTP core cutover, atomic nine-market schedules and dead Selenium provider removal verified.
- [x] Task 6 offline: API → core collection → analysis → data/radar/game, cache and iOS preservation pass.
- [ ] Browser visual QA at 390px and 1440px: no browser exposed in this environment.
- [ ] Original live release gate: full Top100 matrix and six runs each <60 seconds.

Full regression suite: 507 passed. Two completed live measurements and acceptance limits
are linked above. No production data or Gemini calls were used for acceptance.

## Global Constraints

- `--platform` (hoặc `-p`), collect choices `{all,ios,android}`.
- “Cào tuần tự cả iOS và Android”: `all` chạy iOS trước, Android sau; không chạy hai platform đồng thời.
- `--markets` mặc định “vn,th,id,my,ph,sg,la,kh,us”; `--chart-type` mặc định “all”.
- Chọn **ios** làm mặc định collect/analyze/radar để giữ tương thích, nằm trong lựa chọn spec cho phép.
- “?platform=android”: dùng URL query làm nguồn trạng thái, không thêm cookie ưu tiên mâu thuẫn URL.
- `/dashboard`, `/data`, `/games/{app_id}`, `/api/data`, `/api/stats/radar`, `/api/crawl`.
- “Biểu đồ biến động thứ hạng (Top Free & Top Grossing) 14 ngày qua.”
- API thành công trả “HTTP 200”; input sai trả 422, không có game trả 404, crawl bận trả 409, CSRF/origin sai trả 403.
- Installs thresholds: `50,000,000`, `10,000,000`, `1,000,000`, `100,000`; unknown không được hiển thị như `<100K`.
- “Opportunity Radar v1.5”: tái dùng scoring hiện có; không tự đổi trọng số.

---

## Dependencies và phạm vi

Thực hiện sau [HTTP plan](2026-09-28-android-http-scraper-engine.md) Tasks 1–4 và [storage plan](2026-09-28-android-storage-schema-evolution.md) Tasks 1–5. Đọc các acceptance reports trước cutover. Không gọi Gemini, không tự mở rộng shortlist/AI sang Android; các nút hiện có chỉ hoạt động với platform được hỗ trợ và không được gửi package Android vào flow iOS.

Hiện trạng baseline `2dbd118`: `/api/stats/radar` đã có; `/api/data` và `/api/crawl` chưa có. `/runs` POST kiểm tra CSRF; `LocalOriginMiddleware` bảo vệ mutation. `launch_pipeline` chạy subprocess ẩn trên Windows. `AndroidCoordinator` đang quản lý lịch Android riêng và dùng legacy worker.

## File map

| File | Vai trò |
|---|---|
| `collection/platforms.py` (new) | Platform validation, provider factory, core worker dispatch |
| `cli.py` | Flags, collect ordering, analyze/radar filters, progress |
| `collection/processes.py` | Existing hidden subprocess launch; preserve signature |
| `web/views.py` | Platform-scoped data/dashboard/game read models |
| `web/platform_api.py` (new) | Crawl request validation, new JSON endpoints |
| `web/app.py` | Route query params, API registration, form submission |
| `web/presentation.py` (new) | Installs badge and navigation URL formatting |
| `web/templates/{base,data,dashboard,game}.html`, `web/static/app.css` | Switcher, installs, game history and states |
| `android/coordinator.py`, `android/worker.py`, `web/android.py` | Retire new browser crawl paths, preserve legacy history |
| `tests/test_platform_cli.py`, `tests/test_platform_web.py`, `tests/test_platform_cutover.py` (new) | Cross-platform integration coverage |
| `README.md`, `pyproject.toml`, `requirements.lock.txt` | Final usage and dependency removal |

### Task 1: Shared dispatch và CLI flags

**Files:** Create `collection/platforms.py`, `tests/test_platform_cli.py`; modify CLI collect/work/pipeline/analyze/stats branches and `config.py`.

**Interfaces:**

```python
# platforms.py
# collect_platform(repo: Repository, platform: str, countries: list[str],
#                  feeds: list[str], request_key: str, *, enrich: bool=True,
#                  on_progress=None) -> tuple[str,str]  # run ID, status
# execute_run(repo: Repository, run_id: str, *, enrich: bool=True,
#             on_progress=None) -> str
# execute_run loads platform from core charts; uses existing Collector for iOS,
# AndroidCollector for Android; mixed-platform core run raises ValueError.
# selected_platforms(value: str) -> tuple[str,...]
```

`launch_pipeline(run_id, data_dir) -> int` remains unchanged. Child process reconstructs platform from DB, not an optional CLI flag that could disagree with stored run identity.

- [ ] **Step 1: Write failing CLI dispatch test:**

```python
from casual_scout.cli import main

def test_all_collects_in_order(monkeypatch,tmp_path,capsys):
    calls=[]
    def collect(repo,platform,countries,feeds,request_key,*,enrich=True,on_progress=None):
        calls.append((platform,countries,feeds))
        if on_progress: on_progress(f'{platform}: succeeded')
        return f'run-{platform}','succeeded'
    monkeypatch.setattr('casual_scout.collection.platforms.collect_platform',collect)
    assert main(['collect','--platform','all','--markets','vn,us',
                 '--data-dir',str(tmp_path)]) == 0
    assert [x[0] for x in calls] == ['ios','android']
    assert all(x[1] == ['vn','us'] for x in calls)
    assert all(x[2] == ['top-free','top-grossing'] for x in calls)
    assert 'android: succeeded' in capsys.readouterr().out
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_platform_cli.py -v` → flag/helper missing.
- [ ] **Step 3: Implement choices and sequential dispatch:**

```python
def selected_platforms(value):
    if value == 'all': return ('ios','android')
    if value in ('ios','android'): return (value,)
    raise ValueError('unsupported platform')

collect_parser.add_argument('--platform','-p',choices=['all','ios','android'],default='ios')
# In the collect command branch:
from casual_scout.collection import platforms
statuses=[]
for platform in platforms.selected_platforms(args.platform):
    run_id,status=platforms.collect_platform(
        repo,platform,countries,feeds,f'cli-{platform}-{uuid4()}',
        enrich=not args.no_enrich,on_progress=lambda message: print(message,flush=True))
    statuses.append(status)
return 1 if any(s in ('failed','interrupted') for s in statuses) else 0
```

Implement collect_platform through `jobs.submit(...,platform=platform)` then execute_run; build HTTP client inside context and close after Android run. Reuse AppleProvider(Settings) and Collector behavior for iOS. `execute_run` performs one DISTINCT platform query joining charts→market_runs for run, validates cardinality=1 and supported value. Factory uses `GoogleHttpClient(httpx.Client(timeout=15, limits=httpx.Limits(max_connections=10,max_keepalive_connections=10)))` owned by a context manager. Use the shared concurrency gate from HTTP plan.

Add `--platform {ios,android}` default ios to analyze and stats radar; pass it through AnalysisService and dashboard/radar queries. Keep current aliases `--countries`, `--chart-type` and `--no-enrich`. Validate all requested markets before the first job (Android only nine locales; `all` accepts their intersection). Print start platform/run ID/markets/feed selection and final status; collector reports `[i/18]`, cache/new count and errors. A failed iOS run still permits the subsequent Android run if its lock has been released; KeyboardInterrupt stops the whole command and must not start another platform. Busy error prints clear message and exits nonzero.

Pipeline performs post-analysis for complete snapshots' UTC observation dates and their platform, preserving original summary and per-market failures. No hardcoded “today” if crawl crosses UTC midnight. Unit tests use spies around AnalysisService to assert dates/countries/platform.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_platform_cli.py tests/test_cli.py tests/test_cli_pipeline.py tests/test_cli_analysis.py tests/test_cli_stats.py -v`. Include default iOS, `-p android`, invalid platform/market, only grossing, no-enrich, partial status and child dispatch tests.
- [ ] **Step 5: Commit:** stage platforms/CLI/config/tests; `git commit -m "feat: add platform-aware collection and analysis CLI"`.

### Task 2: Read models không lẫn dữ liệu nền tảng

**Files:** Modify `web/views.py`, Repository query methods as needed; create `tests/test_platform_web.py`.

**Interfaces:** Add keyword-only `platform='ios'` to `get_data_view`, `get_dashboard_view`, `get_game_view`. Existing parameters and return keys remain; add `platform`, row `installs`, `min_installs`, `has_ads`, `has_iap`, `free_rank`, `grossing_rank`; game view gains `history` with both rank series for exact 14-day window.

- [ ] **Step 1: Write failing read-model test:**

```python
from casual_scout.storage import Repository
from casual_scout.web.views import get_data_view

def test_empty_android_view_keeps_platform(tmp_path):
    repo=Repository(tmp_path); repo.initialize()
    view=get_data_view(repo,country='vn',platform='android')
    assert view['platform'] == 'android'
    assert view['entries'] == []
```

The existing return key is `entries` (`web/views.py`); retain it in view, template and API. Create mixed-platform test records using `CoreGoogleFake` plus existing `collection_fixture`/Apple evidence; do not merely mock read models for isolation tests.
- [ ] **Step 2: RED:** `python -m pytest tests/test_platform_web.py -v`.
- [ ] **Step 3: Scope every query, including snapshot selection and date discovery:**

```python
provider = 'google' if platform == 'android' else 'apple'
chart = Chart(country,provider=provider,platform=platform,
              genre='GAME_CASUAL' if platform == 'android' else '7003',feed_type=feed_type)
# Snapshot SQL must bind all three scope predicates:
# WHERE c.country=? AND c.platform=? AND c.collection=?
# params=(country,platform,chart.collection)
records = repo.get_daily_analytics(date_str,country,platform=platform)
```

For supplied `snapshot_id`, validate its chart matches selected country/platform/feed instead of displaying another platform's snapshot. Wrong-scope ID gives 404 at route. Dashboard KPI/heatmap/distribution/radar use only selected platform records and available dates. `stats/noteworthy.py` helpers receive a platform parameter if dashboard relies on them; apply it to every SQL join. Existing iOS-only AI/shortlist calls remain explicitly iOS.

Keep `calculate_opportunity_score_v15` and `rank_opportunities` unchanged; supply platform-scoped records. Join latest metadata by **snapshot binding**, not app ID alone. For Android game detail prefer explicit platform query; if absent, numeric ID infers iOS and dotted package infers Android. Country remains explicit/default vn. Generate canonical Google store URL with encoded package/country; reject untrusted link schemes. History queries bound by UTC date range `[end-13 days,end]`, create missing-day nulls, use both free/grossing series, and do not draw fabricated ranks across gaps.

Tests seed iOS/Android same market/date with different counts and verify no KPI/radar/chart/history/metadata leakage; check grossing-only Android game, unknown package, wrong snapshot scope, missing metadata, installs NULL, and 14 calendar days with missing observations.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_platform_web.py tests/test_web_analysis.py tests/test_web_stats.py tests/test_web_monetization.py tests/test_noteworthy.py -v`.
- [ ] **Step 5: Commit:** stage read models/required query helpers/tests; `git commit -m "feat: scope market views and radar by platform"`.

### Task 3: JSON API và background crawl theo platform

**Files:** Create `web/platform_api.py`; modify route registration in `web/app.py`; extend `tests/test_platform_web.py`, `tests/test_web_security.py`.

**Interfaces:** `platform_router(repo, security, launcher) -> APIRouter`. `CrawlRequest` accepts one platform ios/android (no `all` in web), markets list, chart_type all/free/grossing. Responses: data object `{platform,country,feed_type,date,entries}`, radar existing list shape, crawl `{run_id,status:'queued',platform}`. Successful crawl returns 200 immediately, not after completion.

- [ ] **Step 1: Write failing route test:**

```python
from fastapi.testclient import TestClient
from casual_scout.config import Settings
from casual_scout.web.app import create_app

def test_api_reads_validate_platform(tmp_path):
    app=create_app(Settings(tmp_path),launcher=lambda run,path: 123)
    client=TestClient(app)
    response=client.get('/api/data?platform=android&country=vn&feed_type=top-free&date=2026-09-28')
    assert response.status_code == 200
    assert response.json()['platform'] == 'android'
    assert response.json()['entries'] == []
    assert client.get('/api/data?platform=windows').status_code == 422
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_platform_web.py -v` → 404 for new API.
- [ ] **Step 3: Implement validated body and handlers:**

```python
from typing import Literal
from pydantic import BaseModel,Field,field_validator

class CrawlRequest(BaseModel):
    platform: Literal['ios','android'] = 'ios'
    markets: list[str] = Field(default_factory=lambda: ['vn','th','id','my','ph','sg','la','kh','us'],min_length=1,max_length=9)
    chart_type: Literal['all','free','grossing'] = 'all'

    @field_validator('markets')
    @classmethod
    def valid_markets(cls,values):
        allowed={'vn','th','id','my','ph','sg','la','kh','us'}
        normalized=list(dict.fromkeys(v.lower().strip() for v in values))
        if not set(normalized) <= allowed: raise ValueError('unsupported market')
        return normalized
```

GET handlers type platform/feed as Literal, date as `datetime.date | None`; validate country, then use Task 2 read models. `/api/stats/radar` extends existing route instead of registering a duplicate; pass platform in summary/heatmap/monetization/export routes used by dashboard JavaScript as well, otherwise switching page still leaks iOS AJAX results.

POST handler checks `security.validate_csrf_token(request.headers.get('X-CSRF-Token',''),request.cookies.get('session_id',''))`; invalid→403. Keep LocalOriginMiddleware. Build request_key from optional `Idempotency-Key` prefixed by platform, or UUID if absent. JobService validates reused-key scope. On `CollectionBusyError` return 409 and do not launch. Launch only newly submitted queued run once; implement an atomic `launch_claims` field/claim in runs (nullable additive `launch_claimed_at TEXT`) or use a JobService method `claim_launch(run_id: str) -> bool` updating queued run conditionally. Required method must reset claim on launch failure and mark failed; abandoned claim recovery uses existing dead-worker grace period. Implement and test it within this task, not as an undefined helper. Do not launch twice for an idempotent retry.

After valid claim call existing launcher(run_id,data_dir), return 200 with ID; subprocess launch failure returns 503 and persisted failed status. GET run-status endpoint remains polling source. Form POST `/runs` accepts hidden platform and delegates to the same submission service; redirect to `/runs/{id}`. Form crawl uses all nine markets independent of view country and both feeds for Android; preserve existing iOS top-free web scope and schedule behavior unless explicitly changed later. API request markets subset is honored, unlike fixed-scope button.

Test valid origin+CSRF obtained from GET `/data` cookies; missing/invalid CSRF, foreign origin, unsupported platform/country/feed, repeated idempotency key, conflicting scope, active other-platform run, launch failure, only one launcher invocation and JSON 200. Parameterize data/radar endpoints over platforms with real SQLite fixtures.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_platform_web.py tests/test_web_security.py tests/test_jobs.py tests/test_ios_collection_scope.py -v`.
- [ ] **Step 5: Commit:** stage API/app/launch-claim migration/jobs/tests; `git commit -m "feat: add platform-scoped data and crawl APIs"`.

### Task 4: Platform switcher, installs badges và Android game detail

**Files:** Create `web/presentation.py`; modify `web/app.py`, templates base/data/dashboard/game and CSS; extend `tests/test_platform_web.py`.

**Interfaces:** `installs_badge(min_installs: int|None) -> tuple[str,str]` gives text/CSS class; `platform_url(path: str, query: dict, platform: str) -> str` preserves country/date/feed and resets platform-specific snapshot_id. Register helpers in Jinja globals; all rendered view contexts carry platform.

- [ ] **Step 1: Write boundary test:**

```python
import pytest
from casual_scout.web.presentation import installs_badge

@pytest.mark.parametrize('value,label',[
    (None,'Chưa có dữ liệu'),(0,'👀 <100K'),(99999,'👀 <100K'),
    (100000,'🌱 100K+'),(999999,'🌱 100K+'),(1000000,'⚡ 1M+'),
    (9999999,'⚡ 1M+'),(10000000,'🔥 10M+'),(49999999,'🔥 10M+'),
    (50000000,'💎 50M+')])
def test_installs_badges(value,label):
    assert installs_badge(value)[0] == label
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_platform_web.py -v`.
- [ ] **Step 3: Implement formatting and accessible templates:**

```python
def installs_badge(min_installs):
    if min_installs is None: return 'Chưa có dữ liệu','installs-unknown'
    for floor,label,style in (
        (50000000,'💎 50M+','installs-global'),(10000000,'🔥 10M+','installs-popular'),
        (1000000,'⚡ 1M+','installs-growing'),(100000,'🌱 100K+','installs-emerging')):
        if min_installs >= floor: return label,style
    return '👀 <100K','installs-small'
```

```html
<nav aria-label="Nền tảng" class="platform-switcher">
  {% for value,label in [('ios','🍎 Apple iOS'),('android','🤖 Google Android')] %}
  <a href="{{ platform_url(request.url.path, dict(request.query_params), value) }}"
     {% if platform == value %}aria-current="page"{% endif %}>{{ label }}</a>
  {% endfor %}
</nav>
<!-- Inside crawl form -->
<input type="hidden" name="platform" value="{{ platform }}">
<!-- Android row only; raw store text stays available in title/detail -->
{% if platform == 'android' %}
{% set label,style = installs_badge(row.min_installs) %}
<td><span class="{{ style }}" title="{{ row.installs or 'Chưa có dữ liệu' }}">{{ label }}</span></td>
{% endif %}
```

Implement `platform_url` with `urllib.parse.urlencode`, copy query, set platform, remove snapshot_id; navigation to data/dashboard preserves platform. Switcher appears on dashboard/data; do not create a wrong-ID game URL when switching platform on detail page (link to matching data page instead). Add matching Android-only header/colspan and monetization column, badge colors following existing CSS palette with visible text and keyboard focus.

Game detail shows package, official Google Play link, original installs text/numeric minimum, stars/count, taxonomy, and chart with two 14-day series; existing Chart.js handles null gaps and reversed rank axis. Add `target='_blank' rel='noopener noreferrer'` to external store link. Jinja autoescape stays enabled. Unknown data renders “Chưa có dữ liệu”. Empty/loading/crawl-busy/failed/partial states preserve selected platform. Android AI and shortlist actions are not rendered until supported; shared global shortlist navigation remains explicitly iOS. Update export links and any filter JS to carry platform, country, feed and date.

Add rendered HTML tests for selected aria-current, form platform, Android-only installs header, boundary badges, escaped names/descriptions, package detail URL, Google store link, null history gaps and two chart datasets. Perform browser inspection at 390px and 1440px on seeded temporary data; record screenshots and confirm keyboard navigation, empty state and busy state.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_platform_web.py tests/test_web.py tests/test_web_stats.py -v`; manually inspect both platform tabs before and after form submit.
- [ ] **Step 5: Commit:** stage presentation/templates/CSS/routes/tests; `git commit -m "feat: add Android platform views and install badges"`.

### Task 5: Cutover mọi crawl path khỏi Selenium, bảo toàn lịch sử và lịch chạy

**Files:** Modify `android/coordinator.py`, `android/worker.py`, `web/android.py`, `web/app.py`, `pyproject.toml`, `requirements.lock.txt`, README; extend `tests/test_platform_cutover.py`, legacy Android tests.

**Interfaces:** Existing saved Android schedule preferences remain readable. Future Android scheduled runs submit core jobs with platform android/nine countries/two feeds; `launch_android(job_id,data_dir)` legacy entry redirects only newly core-backed runs to execute_run. Old archived jobs are view-only and never implicitly recollected.

- [ ] **Step 1: Write failing no-browser import test:**

```python
import builtins
from casual_scout.collection.platforms import selected_platforms

def test_platform_dispatch_does_not_import_selenium(monkeypatch):
    original=builtins.__import__
    def guarded(name,*args,**kwargs):
        if name == 'selenium' or name.startswith('selenium.'):
            raise AssertionError('browser dependency remains in active path')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    assert selected_platforms('android') == ('android',)
```

Strengthen this test by executing a complete mock Android core run and instantiating the FastAPI app under the guarded importer, not just calling selected_platforms. Use CoreGoogleFake, no real HTTP. Add scheduled dispatch test using injected clock and launcher as existing `tests/test_android_web_live.py` patterns do.
- [ ] **Step 2: RED:** `python -m pytest tests/test_platform_cutover.py -v`; current legacy worker should expose browser path.
- [ ] **Step 3: Route future schedules to core jobs.** Preserve schedule enabled state, 07:00 Asia/Ho_Chi_Minh, iOS priority and no catch-up behavior. Implement a conditional UPDATE of last-triggered date in the same transaction that inserts the new core run/charts (pattern `submit_scheduled_ios`), then launch after transaction; do not mark a schedule consumed when collector busy. New `JobService.submit_scheduled_android(local_date: str, now: datetime) -> str|None` reads existing Android settings table; exact table/column names are taken from `android/schema.sql`. Keep method contract in jobs module and test atomic once-per-date behavior with two calls. Schedule default remains disabled.

Implement the schedule claim against the confirmed `android_schedule(id,enabled,last_date)` schema:

```sql
UPDATE android_schedule SET last_date=?
WHERE id=1 AND enabled=1 AND (last_date IS NULL OR last_date<>?);
```

Within one write transaction first check no core active run, check local time is the scheduled minute, execute this UPDATE, require rowcount=1, then insert run and 18 market_runs. If any insert fails the date claim rolls back. `AndroidStore.initialize()` remains responsible for ensuring the existing schedule table is present. Add `android/schema.sql` to the inspected files for this task; no guessed preference field names.

For `/android` without historical job_id redirect to `/data?platform=android` (303), preserve legacy job_id history pages. Legacy crawl POST delegates to core crawl submission; legacy worker command refuses archived/non-core-only job with clear message and no Selenium. Remove import/start calls to GooglePlayBrowser from active code. Move `extract_store_classification` to new pure `android/classification.py`, update `tests/test_android_provider.py` imports, then remove `android/provider.py` after `rg` confirms no live references. Keep research scripts as historical tools explicitly optional; they must not be imported by runtime/tests without optional dependencies. Update old browser-specific tests to test pure parsing or mark explicitly opt-in research tests; do not simply suppress core regression failures.

Remove selenium from default/Android runtime extras and locked runtime requirements; keep `android=[]` compatibility extra if users still install `.[android]`. README replaces Chrome instructions with platform CLI/API usage, nine-market scope, data retention, partial metadata behavior and performance results/limits. Old evidence files and DB tables are not deleted. UI historical links remain available from Runs or a labeled archive link.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_platform_cutover.py tests/test_android_web_live.py tests/test_android_worker_live.py tests/test_daily_scheduler.py tests/test_one_time_schedule.py tests/test_web_security.py -v`. In fresh venv without Selenium run mocked Android collection and web app import; verify `rg -n 'selenium|GooglePlayBrowser' src` finds no active browser path.
- [ ] **Step 5: Commit:** stage exact cutover/dependency/docs/test files; `git commit -m "feat: switch Android entry points to the HTTP core pipeline"`.

### Task 6: End-to-end acceptance, docs và release evidence

**Files:** Create `tests/test_platform_acceptance.py`, `docs/operations/2026-09-28-android-platform-acceptance.md`; finalize README and HTTP acceptance report.

**Interfaces:** Consumes real core SQLite plus mock public HTTP fixtures from HTTP Task 1, injects fake launcher that invokes core pipeline synchronously only in tests. Production remains detached.

- [ ] **Step 1: Write end-to-end assertions:**

```python
def assert_android_response(payload):
    assert payload['platform'] == 'android'
    assert len(payload['entries']) == 100
    assert all(row['min_installs'] is not None for row in payload['entries'])
    assert all('free_rank' in row and 'grossing_rank' in row for row in payload['entries'])
```

Build TestClient with temp Settings and injected launcher; mock provider HTTP using stored fixtures, submit authorized crawl API, execute captured run through execute_run and AnalysisService, then GET data/radar/game pages. Assert status 200, data identity, installs and chart history; run twice and assert zero fresh detail requests on second run (rank requests still happen). Include an iOS snapshot in the same DB and assert unchanged results and hashes.
- [ ] **Step 2: RED:** run `python -m pytest tests/test_platform_acceptance.py -v` before any missing wiring fix; report observed failure rather than weakening expectations.
- [ ] **Step 3: Fix only gaps exposed by E2E** in the owning modules. Record fixture vs live distinction in acceptance document; retain current source dates. Include commands for collect android/all, analyze android, stats radar android and web launch:

```powershell
python -m casual_scout collect --platform android --markets vn,th,id,my,ph,sg,la,kh,us --chart-type all --data-dir .\data-android-acceptance
python -m casual_scout analyze --platform android --data-dir .\data-android-acceptance
python -m casual_scout stats radar --platform android --country vn --limit 20 --data-dir .\data-android-acceptance
python -m casual_scout serve --host 127.0.0.1 --port 8002 --data-dir .\data-android-acceptance
```

Use dedicated non-production data directory. Run HTTP plan benchmark for three cold/warm full runs. Record 18 chart counts, missing installs counts, retries, elapsed seconds, no browser evidence, provider coverage and screenshots. A partial run is operationally valid but does **not** meet the full Top100/100%-installs acceptance criterion. If live source/performance gate fails, keep release acceptance open and show measured results; never report the three specs fully met solely because tests pass.
- [ ] **Step 4: Verify once:** `python -m pytest -q`; `python -m ruff check` on changed Python files; HTTP coverage command from its plan; `git diff --check`. Run browser visual checks from Task 4 and live acceptance separately from offline suite. Record commands/results, not predicted test counts.
- [ ] **Step 5: Commit:** stage acceptance/tests/README and any verified wiring changes; `git commit -m "test: verify Android CLI and dashboard integration"`.

## Coverage trace and execution order

| Spec requirement | Task |
|---|---|
| Collect --platform/-p, all ordering, markets/feed flags, live progress | 1 |
| Analyze and radar platform selection | 1, 2 |
| Dashboard/data platform persistence and crawl selection | 2, 3, 4 |
| Installs badges and monetization | 4 plus storage analysis |
| Package game detail, store link, ratings, taxonomy, 14-day dual history | 2, 4 |
| Three JSON endpoints and HTTP 200 success | 3, 6 |
| No Chrome in active Android collection | 5, 6 plus HTTP acceptance |

Recommended sequence: HTTP source gate → HTTP provider → storage/cache/analytics → CLI/API/UI → cutover → complete regression and live performance acceptance. Commits happen per task after GREEN. Use `.\.venv\Scripts\python.exe` instead of `python` on Windows without activated venv. These documents authorize planning only; do not begin implementation until the user chooses execution.
