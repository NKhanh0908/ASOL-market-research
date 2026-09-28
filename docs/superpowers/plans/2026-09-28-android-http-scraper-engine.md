# Android HTTP Scraper Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thu thập Google Play Casual Top Free và Top Grossing bằng HTTP, có evidence, metadata installs và kiểm chứng đủ 100 hạng tại chín thị trường.

**Architecture:** Provider HTTP độc lập với SQLite, dùng `httpx.Client` và tối đa 10 request đồng thời. Parser chuyển response công khai đã được kiểm chứng thành `ParsedChart` và metadata; mỗi response giữ `HttpResult` riêng để không mất nguồn gốc. Collector/cache và chuyển các entry point khỏi Selenium thuộc hai plan kế tiếp.

**Tech Stack:** Python 3.12, httpx hiện có, concurrent.futures, pytest, coverage (dev-only).

**Spec:** [SPEC-AND-01](../specs/2026-09-28-android-http-scraper-engine-spec.md)

## Global Constraints

- “Chi phí: **$0.00**.” Không API key, đăng nhập hoặc dịch vụ trả phí.
- “Mỗi HTTP request có timeout tối đa 15 giây.”
- “retry tối đa 3 lần” với “(1s, 2s, 4s)”: hiểu là một lần đầu + ba retry, tổng tối đa bốn attempts.
- “batching 10 app đồng thời”: dùng một giới hạn tổng 10 request, không nhân giới hạn theo thị trường.
- “48 giờ”: cache do Repository/collector xử lý, không cache ngầm trong provider.
- “Top 100”, `top-free`, `top-grossing`, `GAME_CASUAL`.
- “dưới 60 giây” là tiêu chí nghiệm thu end-to-end, không phải kết luận suy ra từ unit test.
- “100% test coverage cho module `GooglePlayProvider` với mock HTTP responses.” Đo statement và branch cho provider, parser, transport riêng của Google.
- App thiếu metadata giữ ranking và `status='partial'`; không thay installs chưa biết bằng 0.

---

## Thứ tự và hiện trạng đã xác nhận

Đọc cả ba specs. Thực hiện plan này trước, tiếp theo `2026-09-28-android-storage-schema-evolution.md`, cuối cùng `2026-09-28-android-cli-web-integration.md`. Plan này cho ra provider có thể kiểm thử độc lập; chưa đổi worker đang chạy.

Baseline: commit `2dbd118`. `android/provider.py` là Selenium; `models.Chart.__post_init__` luôn đổi collection sang tên Apple. Báo cáo `docs/operations/2026-09-24-google-play-feasibility.md` xác nhận HTML category có 27 package nhưng **không** xác nhận chúng là chart. Không dùng thứ tự anchor toàn trang làm thứ hạng.

Không thể viết parser chart production đúng từ bằng chứng hiện có. Task 1 là cổng khả thi bắt buộc có deliverable cụ thể; nếu endpoint public GET không cung cấp Top 100, dừng các task phụ thuộc và báo sai khác spec. Không tự đổi sang RPC POST, Selenium, feed khác hoặc giảm depth. Không coi plan này là bằng chứng nguồn đã khả thi.

## File map và contract

| File | Trách nhiệm |
|---|---|
| `scripts/probe_google_play_http.py` | Probe chỉ đọc, lưu response và manifest, không mở DB |
| `docs/operations/2026-09-28-google-play-http-contract.md` | Endpoint/parser contract được xác minh trong Task 1 |
| `tests/fixtures/google_play/` | Response public thực tế và expected records đã đối chiếu |
| `src/casual_scout/providers/google_http.py` | Retry, pooling, HttpResult, injected clock/sleep |
| `src/casual_scout/providers/google_parser.py` | Parse chart và detail theo evidence contract |
| `src/casual_scout/providers/google.py` | GooglePlayProvider, locales, metadata batching |
| `src/casual_scout/models.py` | Giữ nguyên Google collection, tương thích Apple |
| `tests/test_google_http.py`, `tests/test_google_parser.py`, `tests/test_google_provider.py` | Offline contract/error/concurrency tests |
| `scripts/benchmark_google_play_http.py` | Đo cold/warm full pipeline sau storage plan |

Contract mới, các plan sau phải dùng đúng:

```python
# providers/google.py
LOCALES = {'vn': 'vi', 'th': 'th', 'id': 'id', 'my': 'en',
           'ph': 'en', 'sg': 'en', 'la': 'en', 'kh': 'en', 'us': 'en'}
# GooglePlayProvider(client: GoogleHttpClient)
# fetch_chart(chart: Chart) -> tuple[HttpResult, ParsedChart]
# fetch_metadata(country: str, ids: list[str])
#     -> list[tuple[HttpResult, dict[str, dict]]]
# Each metadata tuple contains exactly one requested package, even partial results.
# GoogleHttpClient(client: httpx.Client, sleep=time.sleep)
# get(url: str) -> HttpResult
# parse_google_chart(body: bytes, chart: Chart) -> ParsedChart
# parse_google_metadata(body: bytes, package: str) -> dict
```

Metadata keys: `name`, `developer`, `description`, `genres` (list of `{name: str}` for existing taxonomy), `average_rating`, `rating_count`, `price`, `currency`, `store_url`, `icon_url`, `installs`, `min_installs`, `has_ads`, `has_iap`, `status`, `error`. Map source `rating` to `average_rating`; retain raw original fields in evidence. Unknown values are `None`, `status='partial'`; booleans must come from explicit source evidence. `Entry.app_id` is the package, not an invented numeric ID.

### Task 1: Xác minh public GET chart contract trước khi viết parser

**Files:** Create probe, contract document, fixture directory and `tests/test_google_contract.py`.

**Interfaces:** Consumes existing probe report; produces `manifest.json` per captured chart with `country`, `language`, `feed`, `category`, `method`, `url`, `sha256`, `expected_entries`, `body_file`. `expected_entries` contains exact package/rank/name/developer/icon/store URL in source chart order.

- [ ] **Step 1: Viết test hợp đồng evidence** trong `tests/test_google_contract.py`:

```python
import hashlib
import json
from pathlib import Path

def test_verified_chart_matrix():
    root = Path(__file__).parent / 'fixtures' / 'google_play'
    cases = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    markets = {'vn','th','id','my','ph','sg','la','kh','us'}
    assert {(x['country'], x['feed']) for x in cases} == {
        (c, f) for c in markets for f in ('top-free', 'top-grossing')}
    for case in cases:
        assert case['method'] == 'GET'
        assert case['category'] == 'GAME_CASUAL'
        assert hashlib.sha256((root / case['body_file']).read_bytes()).hexdigest() == case['sha256']
        entries = case['expected_entries']
        assert [x['rank'] for x in entries] == list(range(1, 101))
        assert len({x['package'] for x in entries}) == 100
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_google_contract.py -v`; thiếu fixture phải FAIL, không skip.
- [ ] **Step 3: Tạo probe dựa trên `scripts/probe_google_play.py`**, dùng phần lưu response sau cho từng URL được khảo sát; không hardcode endpoint chưa được chứng minh:

```python
def capture(client, url, output):
    import hashlib, json
    output.mkdir(parents=True, exist_ok=False)
    response = client.get(url)
    response.raise_for_status()
    (output / 'response.bin').write_bytes(response.content)
    manifest = {'method': 'GET', 'url': str(response.url),
                'sha256': hashlib.sha256(response.content).hexdigest(),
                'status': response.status_code}
    (output / 'request.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return response.content
```

Expose `--url` and `--output`; use `httpx.Client(timeout=15, follow_redirects=True)` and standard User-Agent. Inspect public response embedded data and documented upstream source, record exact feed/category/locale/pagination field paths in the contract. For every page, preserve raw bytes and request order; package discovery from recommendations is insufficient. Write fixtures only after independently checking source feed identity and rank order. Document whether GET pagination reaches 100, and handling of missing developer/icon fields without fabrication. Capture details for all nine locales, missing/removed app, and install display variants. If pagination is necessary, specify a deterministic evidence envelope with original page bytes encoded in base64 and ordered URLs; do not claim its hash is a single upstream response hash. Retain every page `HttpResult` in observations.
- [ ] **Step 4: GREEN:** same test command; review contract for all 18 charts. If no compliant source is found, commit probe findings, mark remaining tasks blocked by source feasibility, and request a spec decision instead of manufacturing fixture rankings.
- [ ] **Step 5: Commit:** `git add scripts/probe_google_play_http.py docs/operations/2026-09-28-google-play-http-contract.md tests/fixtures/google_play tests/test_google_contract.py`; `git commit -m "research: verify Google Play HTTP chart contracts"`.

### Task 2: HTTP transport với retry và evidence

**Files:** Create `providers/google_http.py`, `tests/test_google_http.py`.

**Interfaces:** Consumes `httpx.Client`; produces `GoogleHttpClient.get(url) -> HttpResult`, with prior attempts in `attempts`, final attempt fields on the outer result. Inject `sleep` for tests; never retry parser errors or 404.

- [ ] **Step 1: Write failing test:**

```python
import httpx
from casual_scout.providers.google_http import GoogleHttpClient

def test_retry_exhaustion_keeps_four_attempts():
    waits = []
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, content=b'rate limited')))
    result = GoogleHttpClient(client, sleep=waits.append).get('https://play.google.com/test')
    assert waits == [1, 2, 4]
    assert result.status == 429
    assert result.error
    assert len(result.attempts) == 3
    assert all(x.body == b'rate limited' for x in result.attempts)
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_google_http.py -v` → missing module.
- [ ] **Step 3: Implement attempt loop:**

```python
for index in range(4):
    if index:
        self.sleep((1, 2, 4)[index - 1])
    started = datetime.now(UTC)
    tick = time.monotonic()
    try:
        response = self.client.get(url, timeout=15)
        status, body, headers = response.status_code, response.content, dict(response.headers)
        error = None if 200 <= status < 300 else f'HTTP {status}'
        retryable = status in (429, 500, 502, 503, 504)
    except httpx.TransportError as exc:
        status, body, headers, error, retryable = None, None, {}, str(exc), True
    item = HttpResult(url, started, int((time.monotonic()-tick)*1000),
                      status, body, headers, error)
    if not retryable or index == 3:
        return dataclasses.replace(item, attempts=tuple(previous))
    previous.append(item)
```

Initialize `previous=[]`, constructor stores client/sleep. Import datetime UTC, time, dataclasses, HttpResult. Add tests for first success, retry then success, 404 without retry, network error, exhausted timeout, and final body absent. Close clients in their owning context. Request headers and connection limits are set once by the provider factory, not per thread.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_google_http.py -v`.
- [ ] **Step 5: Commit:** stage the two files; `git commit -m "feat: add bounded Google Play HTTP retries and evidence"`.

### Task 3: Platform-aware Chart và evidence-based parsers

**Files:** Modify `models.py:Chart.__post_init__`; create `providers/google_parser.py`, `tests/test_google_parser.py`; update `tests/test_google_provider.py`.

**Interfaces:** Consumes verified Task 1 fixtures; produces parser functions in file-map contract and normalized metadata keys above. Invalid/wrong-feed payload returns `quality='invalid'`, short genuine chart returns `partial`.

- [ ] **Step 1: Write failing tests:**

```python
import json
from pathlib import Path
from casual_scout.models import Chart
from casual_scout.providers.google_parser import parse_google_chart

def test_google_keeps_feed_identity():
    chart = Chart('vn', provider='google', platform='android',
                  genre='GAME_CASUAL', feed_type='top-grossing')
    assert chart.collection == 'top-grossing'
    assert Chart('vn', feed_type='top-grossing').collection == 'topgrossingapplications'

def test_parse_verified_chart_fixtures():
    root = Path(__file__).parent / 'fixtures' / 'google_play'
    for case in json.loads((root / 'manifest.json').read_text(encoding='utf-8')):
        chart = Chart(case['country'], provider='google', platform='android',
                      genre='GAME_CASUAL', feed_type=case['feed'])
        parsed = parse_google_chart((root / case['body_file']).read_bytes(), chart)
        assert parsed.quality == 'complete'
        assert [(e.app_id, e.rank) for e in parsed.entries] == [
            (e['package'], e['rank']) for e in case['expected_entries']]
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_google_parser.py -v`.
- [ ] **Step 3: Implement Google branch before existing Apple branch:**

```python
if self.platform == 'android':
    if self.provider != 'google' or self.feed_type not in ('top-free', 'top-grossing'):
        raise ValueError('invalid Google chart identity')
    object.__setattr__(self, 'collection', self.feed_type)
    return
```

Translate **only the exact field paths documented by Task 1** into Entry objects; validate uniqueness, rank 1..100, feed/category/locale. Decode embedded JSON as data, never eval JavaScript. Preserve original install text; prefer source numeric minimum. For absent numeric field, accept only explicitly recognized localized numeric formats from detail fixtures; reject ambiguous formats as partial. Example invariant for numeric fallback:

```python
def minimum_from_ascii_display(text: str) -> int | None:
    import re
    match = re.fullmatch(r'([0-9]+(?:,[0-9]{3})*)\+', text)
    return int(match[1].replace(',', '')) if match else None
```

Tests must cover 10,000,000+, 50M+, 500K+, source numeric minimum, unknown text, true/false/unknown ads and IAP, rating/rating_count, paid price/currency, full description, genres, wrong package, malformed embedded JSON, duplicate and short chart, unavailable detail. For suffix/localized displays use source numeric fields where present; do not apply English punctuation rules to Thai/Indonesian/Vietnamese numbers. Return partial with an explanatory `error` when a required field cannot be extracted. Exact parser code is contingent on the recorded source contract; do not replace it with a fabricated universal JSON schema.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_google_parser.py tests/test_apple.py -v`.
- [ ] **Step 5: Commit:** stage model/parser/tests; `git commit -m "feat: parse verified Google charts and install metadata"`.

### Task 4: Provider façade, locale routing và bounded metadata concurrency

**Files:** Create `providers/google.py`; extend `tests/test_google_provider.py`.

**Interfaces:** Consumes transport/parser; produces signatures above. One provider serves multiple markets. `fetch_metadata` returns individual HTTP results; no SQLite access and no synthetic aggregate response presented as upstream bytes.

- [ ] **Step 1: Write failing tests:**

```python
from casual_scout.providers.google import LOCALES, GooglePlayProvider

def test_locale_contract():
    assert LOCALES == {'vn':'vi','th':'th','id':'id','my':'en','ph':'en',
                       'sg':'en','la':'en','kh':'en','us':'en'}

def test_empty_batch_does_not_call_network():
    class NoNetwork:
        def get(self, url):
            raise AssertionError(url)
    assert GooglePlayProvider(NoNetwork()).fetch_metadata('vn', []) == []
```

- [ ] **Step 2: RED:** `python -m pytest tests/test_google_provider.py -v`.
- [ ] **Step 3: Implement metadata fan-out:**

```python
def fetch_metadata(self, country, ids):
    language = LOCALES[country]
    def fetch(package):
        query = urlencode({'id': package, 'gl': country.upper(), 'hl': language})
        result = self.client.get('https://play.google.com/store/apps/details?' + query)
        values = (parse_google_metadata(result.body, package)
                  if result.body and not result.error else
                  {'status': 'partial', 'error': result.error or 'empty response'})
        return result, {package: values}
    with ThreadPoolExecutor(max_workers=10) as pool:
        return list(pool.map(fetch, dict.fromkeys(ids)))
```

Import `urlencode`, `ThreadPoolExecutor`, parsers. Chart URL construction follows Task 1 contract, including verified pagination. A single shared semaphore of size 10 guards all network requests if charts are scheduled concurrently later. Mock transport tests record `gl`/`hl`, verify order and deduplication, and use an instrumented lock/counter to assert `1 < peak <= 10` without live timing assertions. Failed metadata remains in the result list for collector status accounting.
- [ ] **Step 4: GREEN:** `python -m pytest tests/test_google_provider.py tests/test_google_parser.py tests/test_google_http.py -v`.
- [ ] **Step 5: Commit:** `git add src/casual_scout/providers/google.py tests/test_google_provider.py`; `git commit -m "feat: add concurrent Google Play provider"`.

### Task 5: Coverage gate và performance acceptance harness

**Files:** Modify `pyproject.toml`, `requirements.lock.txt` for dev-only `coverage`; create `scripts/benchmark_google_play_http.py`, `docs/operations/2026-09-28-android-http-acceptance.md`; extend provider tests to missing branches.

**Interfaces:** Consumes provider now and `collect --platform android` from integration plan for final end-to-end measurement; produces JSON timing/counts plus captured evidence references. The benchmark runs on a dedicated temporary data directory only.

- [ ] **Step 1: Write acceptance assertions in harness:**

```python
def assert_acceptance(report):
    assert report['browser_processes_started'] == 0
    assert report['chart_count'] == 18
    assert all(n == 100 for n in report['chart_sizes'])
    assert report['missing_installs'] == 0
    assert report['missing_min_installs'] == 0
    assert report['elapsed_seconds'] < 60
```

- [ ] **Step 2: RED:** feed a report with 17 charts or elapsed 60; assert `AssertionError` in `tests/test_google_provider.py`. This checks harness thresholds, not source feasibility.
- [ ] **Step 3: Implement measurement around `subprocess.run([sys.executable, '-m', 'casual_scout', 'collect', '--platform', 'android', '--data-dir', path], check=True)`**, `time.perf_counter()` before/after, and read core DB chart counts and bound metadata after completion. Use psutil child-process sampling throughout, not just a final process list. Cold run uses an empty temporary directory; warm run reuses its DB immediately. Report total HTTP attempts, cache hits, unique package-country pairs and every chart count. Do not subtract retry time, metadata time or SQLite writes. Capture three cold and three warm runs; each must meet the target for a full pass. If source requests make the target infeasible, publish measured failure and seek spec revision; do not quietly narrow the criterion to warm cache.
- [ ] **Step 4: Verify:** `python -m coverage run --branch --source=casual_scout.providers.google,casual_scout.providers.google_http,casual_scout.providers.google_parser -m pytest tests/test_google_http.py tests/test_google_parser.py tests/test_google_provider.py`; `python -m coverage report --fail-under=100`. Run benchmark only after the two dependent plans are implemented. Until then mark end-to-end performance **not yet measured** in acceptance document.
- [ ] **Step 5: Commit:** stage harness, dev dependency updates, tests, acceptance report; `git commit -m "test: add Google provider coverage and performance gates"`.

## Coverage trace and handoff

Spec §1/§2: Tasks 1, 4, 5; §3: Task 3; §4: Tasks 2, 4 plus storage collector partial handling; §5: fixture matrix + coverage + final benchmark. Selenium removal occurs only in integration Task 5, after HTTP feasibility passes. Existing iOS requests/rate policy remain unchanged.

Self-review: no endpoint capability has been asserted without evidence. The provider can be delivered independently after Tasks 1–4; Task 5's live end-to-end acceptance depends on the storage and CLI plans. Use `.\.venv\Scripts\python.exe` in place of `python` on Windows when the venv is not activated.
