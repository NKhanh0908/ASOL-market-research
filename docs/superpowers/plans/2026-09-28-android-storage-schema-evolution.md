# Android Core Storage and Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ghi Android vào core SQLite, lưu installs, cache metadata 48 giờ và phân tích riêng từng nền tảng mà giữ nguyên lịch sử iOS.

**Architecture:** Mở rộng Repository hiện có bằng migration cộng thêm cột; giữ snapshot/raw/binding bất biến. Android dùng chung core charts/apps/snapshots/metadata/analytics; collector dành riêng cho Google xử lý HTTP batches nhưng mọi ghi SQLite chạy ở thread điều phối. Canonical selection phải có khóa nền tảng và feed, thay vì tái dùng khóa `(date,country)` hiện tại.

**Tech Stack:** Python 3.12, SQLite WAL, existing Repository/JobService/AnalysisService, pytest.

**Spec:** [SPEC-AND-02](../specs/2026-09-28-android-storage-schema-evolution-spec.md)

## Execution status — 2026-09-29

Authoritative progress: [storage acceptance](../../operations/2026-09-28-android-core-storage-acceptance.md).
Original step recipes below are retained; RED and commit commands are not retroactively
claimed as individual executions. Work is consolidated on `feat/android-http-plan-completion`.

- [x] Tasks 1–2: identity/schema migration, installs, immutable snapshot bindings verified.
- [x] Task 3: core Android collection, incremental persistence, errors, interruption and heartbeat verified.
- [x] Task 4: complete same-country metadata cache expires at exactly 48 hours; partial refetched.
- [x] Task 5: free/grossing union, same-feed deltas, platform isolation and monetization verified.
- [x] Task 6: mixed-platform backup/restore, hash/FK preservation and acceptance report delivered.

Observed partial Android charts can be analyzed without marking them complete; a partial
historical baseline cannot prove NEW_ENTRY. Existing iOS behavior is regression-tested.
Live source/speed acceptance remains tracked in the HTTP plan.

## Global Constraints

- “Bất biến (Immutability)”: snapshot, entries, metadata versions và bindings đã ghi không sửa/xóa.
- “Non-destructive Migration”: cột mới dùng `ALTER TABLE ADD COLUMN` có kiểm tra; không rebuild/drop bảng dữ liệu đang có.
- “(provider, platform, source_app_id)”: `('apple','ios',numeric_id)` hoặc `('google','android',package)`.
- `metadata_versions`: “installs TEXT”; “min_installs INTEGER”; iOS giữ `NULL`.
- `daily_rank_analytics`: “platform TEXT NOT NULL DEFAULT 'ios'”, “installs TEXT”, “min_installs INTEGER”.
- “idx_analytics_date_platform_country” trên `(date, platform, country)`.
- “fetched_at >= now - 48h”: cache Android cùng country/platform, chỉ complete, không dùng timestamp tương lai.
- `google`, `android`, `GAME_CASUAL`, depth `100`, collections `top-free` / `top-grossing`.
- Giữ iOS cache **24 giờ** như test hiện tại; yêu cầu 48 giờ áp dụng Android.

---

## Dependencies và quyết định triển khai

Baseline `2dbd118`. Chạy sau Tasks 1–4 của [HTTP plan](2026-09-28-android-http-scraper-engine.md). Storage migrations/cache có thể test với synthetic HttpResult trước khi có network; không dùng synthetic fixtures làm bằng chứng nguồn live.

Các điểm spec chưa mô tả nhưng code bắt buộc xử lý:

1. `daily_canonical_snapshots` có primary key `(date,country)` và các cột snapshot NOT NULL; chỉ thêm `platform` không loại bỏ xung đột. **Quyết định đề xuất:** thêm bảng core `platform_canonical_snapshots` với khóa `(date,platform,country,feed_type)`, copy canonical iOS bằng INSERT OR IGNORE, giữ nguyên bảng cũ để tương thích. Đây là phần bổ sung schema ngoài các cột liệt kê trong spec, cần chốt khi duyệt plan; không rebuild hoặc chỉnh snapshot cũ. Nếu yêu cầu “chỉ ALTER ADD COLUMN” được hiểu là cấm cả CREATE TABLE mới, Task 4 cần sửa spec trước khi thực thi.
2. `daily_rank_analytics` có `UNIQUE(date,country,app_id)`. Giữ constraint hiện tại để tránh rebuild; validate Apple source ID là số và Android package có ít nhất một dấu chấm, nên hai tập ID hiện hỗ trợ không trùng nhau. UPSERT phải thêm điều kiện platform bằng nhau để không ghi đè nhầm nền tảng. Việc hỗ trợ provider với tập source ID chồng nhau nằm ngoài ba specs này.
3. Không tự nhập dữ liệu legacy `android_*` vào snapshot core: evidence cũ HTML/PNG không tương đương raw HTTP snapshot mới. Giữ các bảng/evidence cũ có thể xem lại; mọi lượt crawl mới sau cutover đi vào core.
4. Thiếu metadata không có nghĩa “không ads/IAP”. Trường không biết là `None`; classification trả `UNKNOWN` khi bằng chứng không đủ. Không đổi hành vi classifier iOS.

## File map

| File | Responsibility |
|---|---|
| `storage/migrations_android.py` (new) | Additive column/index/canonical schema migration |
| `storage/repository.py`, `storage/schema.sql` | Persist/read typed metadata, platform queries and identity |
| `collection/jobs.py` | Submit core jobs for explicit platform without reusing unrelated run |
| `android/collector.py` (new) | Core Android collection, cache binding, progress and status |
| `analysis/service.py`, `analysis/monetization.py` | Platform/feed-separated analysis and Android monetization |
| `tests/android_core_support.py` (new) | Deterministic core snapshot fixtures |
| `tests/test_android_core_storage.py`, `tests/test_android_core_collection.py`, `tests/test_android_core_analysis.py` (new) | Migration/cache/collection/isolation regressions |

### Task 1: Idempotent columns và regression fixture trên database cũ

**Files:** Create `storage/migrations_android.py`, `tests/test_android_core_storage.py`; modify `Repository.initialize`, `storage/schema.sql`.

**Interfaces:** `migrate_android_columns(conn: sqlite3.Connection) -> None`; no caller transaction commit; initialize invokes it after existing schema and before any query/index using new columns.

- [ ] **Step 1: Write failing test:**

```python
import sqlite3
from casual_scout.storage import Repository

def test_additive_migration_is_repeatable(tmp_path):
    db = tmp_path / 'casual-scout.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE metadata_versions(id TEXT PRIMARY KEY, platform TEXT, country TEXT, fetched_at TEXT)')
        conn.execute("INSERT INTO metadata_versions VALUES('old-meta','ios','vn','2026-09-27T00:00:00Z')")
        conn.execute('CREATE TABLE daily_rank_analytics(id TEXT PRIMARY KEY, date TEXT, country TEXT)')
        conn.execute("INSERT INTO daily_rank_analytics VALUES('old-row','2026-09-27','vn')")
        from casual_scout.storage.migrations_android import migrate_android_columns
        migrate_android_columns(conn)
        migrate_android_columns(conn)
        assert conn.execute('SELECT installs,min_installs FROM metadata_versions').fetchone() == (None,None)
        assert conn.execute('SELECT id,platform FROM daily_rank_analytics').fetchone() == ('old-row','ios')
        assert 'idx_analytics_date_platform_country' in {
            r[1] for r in conn.execute('PRAGMA index_list(daily_rank_analytics)')}
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_android_core_storage.py -v` → missing migration module.
- [ ] **Step 3: Implement fixed-list migration:**

```python
def migrate_android_columns(conn):
    additions = {
        'metadata_versions': {'installs':'TEXT', 'min_installs':'INTEGER',
                              'has_ads':'INTEGER', 'has_iap':'INTEGER'},
        'daily_rank_analytics': {'platform':"TEXT NOT NULL DEFAULT 'ios'",
                                 'installs':'TEXT', 'min_installs':'INTEGER'},
    }
    for table, columns in additions.items():
        existing = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_analytics_date_platform_country '
                 'ON daily_rank_analytics(date,platform,country)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_metadata_cache_platform '
                 'ON metadata_versions(platform,country,fetched_at)')
```

Add columns to fresh schema too, but create the new analytics index in migration **after** old DB gains platform; placing it unconditionally at the top of schema execution breaks upgrades. Nullable `has_ads`/`has_iap` are additional columns necessary to retain unknown vs false; do not reinterpret old iOS defaults.

For production-shaped regression, save baseline schema from `git show 2dbd118:src/casual_scout/storage/schema.sql` into `tests/fixtures/storage/pre_android_core.sql` (read output and write UTF-8 without PowerShell UTF-16 redirection). Seed iOS through public methods before upgrading, then run initialize twice and compare every existing column value, FK integrity, immutable triggers and raw hashes. Keep fixture setup and tests in this task.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_android_core_storage.py tests/test_storage.py tests/test_metadata.py tests/test_analytics_storage.py -v`.
- [ ] **Step 5: Commit:** stage migration/schema/repository/tests/old schema fixture; `git commit -m "feat: add non-destructive Android core columns"`.

### Task 2: Platform metadata persistence, 48-hour cache và binding status

**Files:** Modify Repository `save_metadata`, `cached_metadata`, `bind_metadata`, `get_snapshot_metadata`; extend storage tests.

**Interfaces:** Keep existing positional arguments, add keyword-only:

```python
# save_metadata(country, values, result, *, provider='apple', platform='ios') -> dict[str,str]
# cached_metadata(country, app_ids, now, *, provider='apple', platform='ios') -> dict[str,str]
# get_snapshot_metadata(snapshot_id) -> dict[str,dict] includes installs/min_installs/has_ads/has_iap/status
```

- [ ] **Step 1: Write failing test:**

```python
from datetime import UTC, datetime, timedelta
from casual_scout.models import HttpResult
from casual_scout.storage import Repository

def test_android_cache_boundary_and_country(tmp_path):
    repo = Repository(tmp_path); repo.initialize()
    stamp = datetime(2026,9,28,tzinfo=UTC)
    result = HttpResult('https://play.google.com/test',stamp,1,200,b'{}',{},None)
    versions = repo.save_metadata('vn', {'com.example.game': {
        'name':'Game','status':'complete','installs':'10M+', 'min_installs':10000000,
        'has_ads':True,'has_iap':False}}, result, provider='google',platform='android')
    kwargs = {'provider':'google','platform':'android'}
    assert repo.cached_metadata('vn',['com.example.game'],stamp+timedelta(hours=48),**kwargs) == versions
    assert repo.cached_metadata('vn',['com.example.game'],stamp+timedelta(hours=48,microseconds=1),**kwargs) == {}
    assert repo.cached_metadata('us',['com.example.game'],stamp,**kwargs) == {}
    assert repo.cached_metadata('vn',['com.example.game'],stamp-timedelta(seconds=1),**kwargs) == {}
```

- [ ] **Step 2: RED:** targeted test → unexpected keyword `provider`.
- [ ] **Step 3: Generalize SQL parameters and metadata mapping:**

```python
ttl_hours = 48 if platform == 'android' else 24
fresh_after = _utc_text(now.astimezone(UTC) - timedelta(hours=ttl_hours))
# cached_metadata WHERE provider=? AND platform=? AND country=?
# AND status='complete' AND fetched_at>=? AND fetched_at<=?
# parameters: provider, platform, country, fresh_after, now_text, *unique_ids
name = metadata.get('name') if platform == 'android' else metadata.get('trackName')
rating = metadata.get('average_rating') if platform == 'android' else metadata.get('averageUserRating')
status = metadata.get('status', 'complete') if platform == 'android' else 'complete'
installs = metadata.get('installs') if platform == 'android' else None
minimum = metadata.get('min_installs') if platform == 'android' else None
```

Map developer/store/rating_count/genres/description/price/currency similarly; `_ensure_app` receives provider/platform, INSERT and duplicate-version SELECT bind them. Retain original `values_json`. Validate installs minimum integer >=0 (bool rejected), pair identity, and metadata status before opening write transaction. Validate Android package `r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+'`; keep legacy Apple call compatibility. For network failure with no body, do not fabricate raw bytes: leave ranking unbound and record request/error at market-run level. Body-backed partial records may be persisted and bound, but cannot enter cache. `bind_metadata` enrichment counts must count only bound `mv.status='complete'`; bound partial does not mean complete. Preserve closed-run binding rejection and identity checks.

Add tests for fresh complete vs newer partial, zero installs, iOS NULL/24h, Google/Apple metadata separation, out-of-country binding rejection, failed-body observation, and immutable snapshot binding after close.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_android_core_storage.py tests/test_metadata.py tests/test_monetization_storage.py -v`.
- [ ] **Step 5: Commit:** stage repository/tests; `git commit -m "feat: persist Android metadata with country-scoped 48h cache"`.

### Task 3: Core Android jobs và collector bảo toàn ranking

**Files:** Modify `collection/jobs.py`; create `android/collector.py`, `tests/android_core_support.py`, `tests/test_android_core_collection.py`.

**Interfaces:** `JobService.submit(trigger: str, countries: list[str], request_key: str, chart_types: list[str]|None=None, *, platform: str='ios') -> str`; new `CollectionBusyError(RuntimeError)` in jobs module when another platform is active. `AndroidCollector(repo, provider, jobs).execute(run_id, enrich=True, on_progress=None) -> str`. Provider matches HTTP plan, all DB writes happen on caller thread.

- [ ] **Step 1: Write failing test and its fake provider:**

```python
from datetime import UTC, datetime
from casual_scout.models import Entry, HttpResult, ParsedChart
from casual_scout.storage import Repository
from casual_scout.collection.jobs import JobService
from casual_scout.android.collector import AndroidCollector

class CoreGoogleFake:
    def __init__(self): self.requested = []
    def fetch_chart(self, chart):
        body = b'{"fixture":"chart"}'
        result = HttpResult('https://play.google.com/chart',datetime.now(UTC),1,200,body,{},None)
        entries = [Entry(f'com.example.g{i}',i,f'Game {i}',
                         f'https://play.google.com/store/apps/details?id=com.example.g{i}',
                         None,'Studio',[]) for i in range(1,101)]
        return result, ParsedChart(chart,entries,None,'complete')
    def fetch_metadata(self,country,ids):
        self.requested.extend((country,i) for i in ids)
        return [(HttpResult('https://play.google.com/detail',datetime.now(UTC),1,200,
                            b'{"fixture":"detail"}',{},None),
                 {i:{'status':'complete','installs':'1M+','min_installs':1000000}}) for i in ids]

def test_second_run_reuses_metadata_but_fetches_new_rankings(tmp_path):
    repo=Repository(tmp_path); repo.initialize(); jobs=JobService(repo)
    provider=CoreGoogleFake(); collector=AndroidCollector(repo,provider,jobs)
    for key in ('first','second'):
        run=jobs.submit('manual',['vn'],key,['top-free','top-grossing'],platform='android')
        assert collector.execute(run) == 'succeeded'
    assert len(provider.requested) == 100
    with repo._connect() as conn:
        assert conn.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 4
```

Move fake to `tests/android_core_support.py`, import it in later tests. It represents synthetic persistence data only.
- [ ] **Step 2: RED:** `python -m pytest tests/test_android_core_collection.py -v`.
- [ ] **Step 3: Implement core run path.** Submit constructs `Chart(country,provider='google',platform='android',genre='GAME_CASUAL',feed_type=feed)` for Google. Store chart endpoint from verified provider URL builder; add `chart_url(chart: Chart) -> str` to `providers/google.py` using the Task 1 endpoint contract, and use that same function in provider and jobs. Active same-request key is idempotent only if stored chart identities match requested scope; reject reuse with different country/platform/feed. Do not hand an iOS run to AndroidCollector. Existing same-platform active-run behavior may remain only if scopes match.

Collector claims PID/process-created lock, loads **all** chart identity fields from DB, obtains fresh ranks, saves snapshot first, checks cache, and persists each metadata HTTP result individually:

```python
versions = repo.cached_metadata(chart.country, ids, datetime.now(UTC),
                                provider='google',platform='android')
missing = [app_id for app_id in ids if app_id not in versions]
repo.bind_metadata(snapshot_id, versions)
for result, values in provider.fetch_metadata(chart.country, missing):
    if result.body is not None:
        new = repo.save_metadata(chart.country,values,result,
                                 provider='google',platform='android')
        repo.bind_metadata(snapshot_id,new)
    jobs.heartbeat(run_id)
```

Network parallelism lives inside provider; do not share SQLite connections with executor threads. Heartbeat before/after each chart and each bounded metadata batch (size 10); no metadata call may block across all 100 packages without heartbeat opportunities. Progress callback prints chart ordinal/count, country/feed, cache/missing counts and final status. Per-chart failure proceeds to next chart; no metadata failure deletes a snapshot. Result status: all chart+metadata complete → succeeded; any saved valid ranking with gaps → partial; zero valid rankings → failed. `--no-enrich` uses not_requested. Unexpected process-level exceptions mark interrupted and release lock through existing JobService lifecycle. Never overwrite final summary while adding analysis output later.

Add tests: same package in two countries fetches twice; shared feeds reuse cache; metadata 404 retains 100 entries and partial; one chart failure preserves other charts; no charts failed; no-enrich; repeat request not relaunching; iOS active run rejects Android; lock recovered after dead process.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_android_core_collection.py tests/test_jobs.py tests/test_collection.py tests/test_ios_collection_scope.py -v`.
- [ ] **Step 5: Commit:** stage exact files; `git commit -m "feat: collect Android into immutable core snapshots"`.

### Task 4: Canonical selection và analytics queries tách platform/feed

**Files:** Modify migrations, Repository canonical/analytics/history methods; extend `tests/test_android_core_storage.py`.

**Interfaces:** Add keyword-only `platform='ios'` to `get_daily_analytics`, `get_app_rank_history`, `get_available_analytics_dates`, `find_latest_complete_snapshot_for_date`; add `platform='ios', feed_type='top-free'` to `save_canonical_snapshot` / `get_canonical_snapshot`. Return rows include platform/installs/min_installs. iOS callers without keyword keep old behavior.

- [ ] **Step 1: Write failing isolation test:**

```python
def test_analytics_filters_platform(tmp_path):
    from casual_scout.storage import Repository
    repo=Repository(tmp_path); repo.initialize()
    base={'date':'2026-09-28','country':'vn','current_rank':1,'signal':'STEADY',
          'signal_reasons':[],'mechanic':'Unknown','cross_markets':['vn']}
    repo.save_daily_analytics([
        dict(base,app_id='123',platform='ios'),
        dict(base,app_id='com.example.game',platform='android',installs='1M+',min_installs=1000000)])
    assert [r['app_id'] for r in repo.get_daily_analytics('2026-09-28','vn')] == ['123']
    android=repo.get_daily_analytics('2026-09-28','vn',platform='android')
    assert android[0]['min_installs'] == 1000000
```

- [ ] **Step 2: RED:** targeted storage test fails for unsupported platform or leakage.
- [ ] **Step 3: Implement additive canonical mapping proposed above:**

```sql
CREATE TABLE IF NOT EXISTS platform_canonical_snapshots (
    date TEXT NOT NULL,
    platform TEXT NOT NULL,
    country TEXT NOT NULL,
    feed_type TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(date,platform,country,feed_type)
);
```

Migration copies old canonical rows by joining their snapshots → market_runs → charts to obtain actual platform/feed; do not assume an old fallback grossing snapshot was free. Keep iOS default canonical methods using legacy table for behavior compatibility; Android calls use the new table and explicit feed. Validate snapshot identity against requested date/platform/country/feed before inserting. For Android delta selection never fallback to the other feed. All latest snapshot SQL adds platform and provider predicates; app history returns rows for exact platform and date-window, not merely the latest 14 sparse records.

Analytics INSERT includes new columns, reads select them, WHERE binds platform. Extend existing conflict clause with `WHERE daily_rank_analytics.platform=excluded.platform`; if a row would conflict across platforms, raise `ValueError` and rollback instead of silent no-op. Validate IDs at persistence boundary. Audit callers using direct analytics SQL in `web/views.py`, `stats/noteworthy.py`, CLI and AI evidence: existing iOS-only features must explicitly filter `platform='ios'` until integration adds a parameter. Do not let AI/shortlist queries start consuming Android implicitly.

Add tests: canonical iOS and Android same UTC day coexist; free and grossing canonical distinct; repeated initialization preserves both; Android earlier/later snapshot never selected by iOS; analytics repeats update only same platform; malformed cross-platform identity fails; old iOS canonical rows unchanged; `PRAGMA foreign_key_check` empty.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_android_core_storage.py tests/test_analytics_storage.py tests/test_analysis_service.py tests/test_ai_evidence.py tests/test_noteworthy.py -v`.
- [ ] **Step 5: Commit:** stage repository/migration/isolation call-sites/tests; `git commit -m "feat: isolate canonical and analytical records by platform"`.

### Task 5: Android monetization và daily analysis cho cả hai feeds

**Files:** Modify `analysis/service.py`, `analysis/monetization.py`; create `tests/test_android_core_analysis.py`.

**Interfaces:** `AnalysisService.analyze_date(date_str,countries=None,*,platform='ios') -> dict`; `classify_android_monetization(*,price: float|None,has_ads: bool|None,has_iap: bool|None,grossing_rank: int|None) -> str`.

- [ ] **Step 1: Write failing classification tests:**

```python
import pytest
from casual_scout.analysis.monetization import classify_android_monetization

@pytest.mark.parametrize('price,ads,iap,grossing,expected',[
    (1,False,False,None,'PAID_PREMIUM'),(0,True,True,None,'HYBRID'),
    (0,True,False,10,'HYBRID'),(0,False,True,None,'PURE_IAP'),
    (0,False,False,10,'PURE_IAP'),(0,True,False,None,'PURE_ADS'),
    (None,None,None,None,'UNKNOWN'),(0,False,False,None,'UNKNOWN')])
def test_android_monetization(price,ads,iap,grossing,expected):
    assert classify_android_monetization(price=price,has_ads=ads,has_iap=iap,
                                        grossing_rank=grossing) == expected
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_android_core_analysis.py -v`.
- [ ] **Step 3: Implement separate classifier:**

```python
def classify_android_monetization(*,price,has_ads,has_iap,grossing_rank):
    if price is not None and price > 0: return 'PAID_PREMIUM'
    if price != 0: return 'UNKNOWN'
    iap = has_iap is True or grossing_rank is not None
    if has_ads is True and iap: return 'HYBRID'
    if has_ads is False and iap: return 'PURE_IAP'
    if has_ads is True and has_iap is False and grossing_rank is None: return 'PURE_ADS'
    return 'UNKNOWN'
```

Keep existing iOS branch. For Android choose canonical complete snapshot separately for each feed; union package sets so grossing-only games are included. `free_rank` is free-map.get(app), `grossing_rank` grossing-map.get(app); `current_rank` uses free when present, otherwise grossing. Delta history for each game uses its selected current feed on past dates (1/3/7 days); never subtract free rank from grossing rank. Cross-market presence uses same platform across union sets. Taxonomy consumes normalized genres/title/description; installs come from bound metadata of selected canonical snapshot, fallback to same-day other feed only for the same package/country/platform. Add platform/installs/min_installs to records and use classifier above. Never use latest unbound metadata to rewrite historical evidence.

Use `CoreGoogleFake` from Task 3 to seed two dates, two countries and overlapping/disjoint feeds; vary fixture ranks and clock explicitly. Assert both ranks for overlap, grossing-only record, no cross-platform cross-market inflation, 1/3/7 deltas scoped to same feed, missing day → unknown delta, installs retained, repeat analysis deterministic, no immutable table changes.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_android_core_analysis.py tests/test_monetization_analysis.py tests/test_analysis_service.py tests/test_p2_acceptance.py tests/test_p3_5_acceptance.py -v`.
- [ ] **Step 5: Commit:** stage analysis/tests; `git commit -m "feat: analyze Android ranks installs and monetization"`.

### Task 6: Migration acceptance và storage handoff

**Files:** Create `docs/operations/2026-09-28-android-core-storage-acceptance.md`; extend `tests/test_android_core_storage.py` with backup roundtrip.

**Interfaces:** Consumes existing `create_backup`, `restore_backup`; produces measured regression results, row counts and FK/hash checks. No production DB mutation in tests.

- [ ] **Step 1: Write preservation assertion for seeded mixed-platform DB:**

```python
def snapshot_fingerprint(conn):
    return {
        table: sorted(conn.execute(f'SELECT * FROM {table}').fetchall(),key=repr)
        for table in ('snapshots','entries','snapshot_metadata','raw_responses')}
```

In the existing backup test pattern seed both platforms with core fixtures, save this fingerprint, backup/restore into another temporary directory and compare fingerprints. Attempt UPDATE/DELETE on snapshot/entries/metadata/binding and assert sqlite3 errors. This is an integration test, not a live crawl.
- [ ] **Step 2: RED:** run new regression before its needed backup adjustments; if backup already supports core tables and passes, record existing support rather than force an artificial failure.
- [ ] **Step 3: Make only necessary backup changes.** Since core tables reside in the same SQLite file and raw store, existing whole-DB backup should work unchanged. In acceptance doc record source commit, test command, test count, UTC timestamp, old/new schema fields, preserved iOS rows and any unresolved failure.
- [ ] **Step 4: Verify:** `python -m pytest tests/test_storage.py tests/test_metadata.py tests/test_analytics_storage.py tests/test_monetization_storage.py tests/test_shortlist_storage.py tests/test_daily_schedule_storage.py tests/test_ai_storage.py tests/test_android_batches.py tests/test_backup.py tests/test_ai_backup.py tests/test_android_core_storage.py tests/test_android_core_collection.py tests/test_android_core_analysis.py -v`. Then `python -m pytest -q` once integration plan completes.
- [ ] **Step 5: Commit:** stage regression/acceptance file and backup code only if changed; `git commit -m "test: verify Android core migration and iOS preservation"`.

## Spec coverage và exit criteria

§1/§2 → Tasks 1,2,4; §3 → Tasks 2,3; §4 → Task 5; §5 → Task 6. Full app identity flows through `Chart`, `_ensure_app`, metadata save/cache/binding. Storage delivered when offline migrations, collection, cache, platform isolation and monetization tests pass; live Google source/performance remains HTTP plan acceptance. Use `.\.venv\Scripts\python.exe` for the Windows venv. Do not run migration acceptance against `data/casual-scout.sqlite3`.
