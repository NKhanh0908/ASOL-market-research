# iOS P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thu thập Top 100 Free Casual theo Apple cho các thị trường đã xác minh, lưu lịch sử và cung cấp web cá nhân trên Windows.

**Architecture:** Python collector và FastAPI/Jinja dùng chung SQLite cục bộ, payload gốc lưu trên ổ đĩa. Collector chạy độc lập trình duyệt, chỉ một tiến trình thu thập tại một thời điểm; Windows Task Scheduler phục vụ khảo sát lịch sau khi collector được kiểm chứng.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Jinja2, HTTPX, SQLite qua sqlite3, psutil, itsdangerous, python-multipart, tzdata; pytest và Ruff cho kiểm chứng. Không thêm frontend build, Docker hoặc database server.

**Spec:** [Thiết kế P1 đã duyệt — ADR-P1-001](../specs/2026-09-10-ios-p1-design.md).

**Authority:** Người dùng duyệt phương án A bằng “ok phương án 1” ngày 2026-09-10. Tài liệu này là kế hoạch, các checkbox chưa đánh dấu không phải công việc đã thực hiện. Nguồn đã thử thành công không thay thế acceptance tests của ứng dụng.

## Global Constraints

- Chạy ở `127.0.0.1`, một người dùng trên máy, không publish LAN/Internet.
- P1 đáp ứng BA-R01–04, BA-R09, BA-R12; không làm delta/trend, biểu đồ thị trường, AI, Android hay thông báo.
- Chart: `topfreeapplications`, genre `7003`, depth `100`, version `1`; giữ provider/platform/country trong identity.
- Thị trường chạy: vn, us, bn, kh, id, la, my, mm, ph, sg, th. TL luôn có trong cấu hình với trạng thái nguồn chưa xác minh; không gọi TL hằng ngày.
- UTC lưu cho mọi thời điểm; web hiển thị giờ VN và chú thích múi giờ.
- Snapshot bất biến, raw evidence có hash; thiếu metadata không làm mất chart.
- Lookup tối đa 20 ID/lô, cache theo app/country 24 giờ; giãn tối thiểu 4 giây giữa các lần bắt đầu request, một request tại một thời điểm; timeout 20 giây; tối đa 3 attempts.
- Không tự fallback sang chart Games/Apps hay provider trả phí.
- Giữ lịch sử, chưa tự xóa theo retention chưa chốt; backup cục bộ, không upload.
- Không chọn lịch production trước khảo sát; không thay power settings/wake timer.
- Workspace chưa là Git repository ở lần kiểm tra gần nhất. Khi thực thi dùng using-git-worktrees để kiểm tra trạng thái thực tế; không coi lỗi git là lỗi ứng dụng. Chỉ commit khi đã có repository phù hợp, không tạo remote/push trong kế hoạch này.

## Bố cục file và phụ thuộc

Các đường dẫn dưới đây là file **sẽ tạo**, không phải file đang tồn tại. Dùng package `casual_scout`, đặt trong `src/`.

| File | Trách nhiệm |
|---|---|
| `pyproject.toml`, `requirements.lock.txt`, `.gitignore` | Packaging, dependencies khóa sau resolve, loại dữ liệu runtime/bí mật/venv khỏi Git |
| `src/casual_scout/__init__.py`, `__main__.py` | Package và điểm vào CLI |
| `config.py`, `models.py` | Thị trường/settings bất biến, DTO dùng chung |
| `providers/apple.py`, `providers/http.py` | Parse nguồn và HTTP/retry/throttle có thể thay bằng fake |
| `storage/schema.sql`, `storage/repository.py`, `storage/raw.py` | Schema, transaction, payload atomic |
| `collection/service.py`, `collection/jobs.py`, `collection/processes.py` | Điều phối, idempotency/khóa, khởi chạy collector nền |
| `web/app.py`, `web/security.py`, `web/views.py` | Routes, CSRF/Host/Origin, truy vấn cho màn hình |
| `web/templates/{base,data,runs,run,game}.html`, `web/static/app.css` | Ba luồng màn hình, trạng thái và CSS tối thiểu |
| `operations/survey.py`, `operations/backup.py`, `cli.py` | Khảo sát giờ, backup nhất quán, lệnh vận hành |
| `scripts/Register-SurveyTask.ps1`, `scripts/Start-Web.ps1` | Task Scheduler và khởi chạy web trên Windows |
| `tests/conftest.py`, `tests/test_*.py` | Fixture chung và kiểm tra hành vi theo từng task |
| `README.md`, `docs/operations/p1-runbook.md` | Cài đặt, chạy, phục hồi và hạn chế |

Tạo `__init__.py` cho các thư mục package. Bằng chứng đầu vào nằm ở `docs/core/research/evidence/2026-09-10-ios-p1/`; không sửa mẫu gốc để làm test pass. Tất cả task thực thi tuần tự 1 → 6; Task 7 là nghiệm thu cuối và pilot riêng.

## Task 1: Đọc nguồn Apple đúng chart, thứ tự và lỗi HTTP

**Files:** tạo pyproject/lock/gitignore, config/models, providers/apple.py, providers/http.py; tạo `tests/conftest.py`, `tests/test_apple.py`, `tests/test_http.py`.

**Interfaces:**

- `Settings(data_dir: Path, request_interval: float = 4.0, timeout: float = 20.0, attempts: int = 3)`; database và raw nằm dưới data_dir.
- `Chart(country: str, provider: str = "apple", platform: str = "ios", collection: str = "topfreeapplications", genre: str = "7003", depth: int = 100, version: int = 1)`.
- `Entry(app_id: str, rank: int, name: str, store_url: str, icon_url: str | None, developer: str | None, source_genres: list[dict])`.
- `ParsedChart(chart: Chart, entries: list[Entry], source_updated: str | None, quality: str, issues: list[str])`; quality là complete/partial/invalid.
- `HttpResult(url: str, started_at: datetime, elapsed_ms: int, status: int | None, body: bytes | None, headers: dict[str, str], error: str | None)`.
- `parse_chart(body: bytes, chart: Chart) -> ParsedChart`; `parse_lookup(body: bytes, requested_ids: list[str]) -> dict[str, dict]`.
- `AppleProvider.fetch_chart(chart: Chart) -> tuple[HttpResult, ParsedChart]`; `fetch_metadata(country: str, ids: list[str]) -> tuple[HttpResult, dict[str, dict]]`. HTTP client/sleep/clock được inject để test không chờ thật.

- [x] **1.1 — Thiết lập môi trường kiểm chứng.** Kiểm tra `python --version` là 3.12+, tạo venv cục bộ, pyproject với src layout và dependencies trên. Resolve trong venv, chạy `pip check`, lưu lock bằng `pip freeze`; không cài global. `.gitignore` loại `.venv/`, `data/`, `.env`, cache pytest/Ruff/Python. Ghi chính xác phiên bản đã resolve trong lock; không viết version đoán vào tài liệu.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Set-Content -Encoding UTF8 requirements.lock.txt
```

- [x] **1.2 — Viết test trước.** Conftest cung cấp `evidence_dir` là đường dẫn tuyệt đối tới thư mục evidence. Tạo test sau và các ca raw bị thiếu entry, trùng ID, sai self-link country/genre/title, invalid JSON, thêm entry vượt depth. Thay đổi bản sao trong bộ nhớ, giữ raw file gốc.

```python
from casual_scout.models import Chart
from casual_scout.providers.apple import parse_chart

def test_casual_feed_preserves_source_order(evidence_dir):
    result = parse_chart((evidence_dir / "vn-casual-100.json").read_bytes(), Chart("vn"))
    assert result.quality == "complete"
    assert len(result.entries) == 100
    assert result.entries[0].app_id == "6757412443"
    assert [e.rank for e in result.entries] == list(range(1, 101))
```

- [x] **1.3 — Chạy red.** `python -m pytest tests/test_apple.py tests/test_http.py -q` trong venv; đầu tiên phải lỗi vì package/API chưa hiện thực hoặc assertion chưa đạt, không vì đường dẫn fixture sai.
- [x] **1.4 — Hiện thực provider.** Dùng URL allowlist, `json.loads(body.decode("utf-8-sig"))`, rank từ `enumerate(entries, 1)`, join metadata bằng ID. Thiếu entry tạo partial; trùng ID/rank hoặc sai chart tạo invalid. URL store chỉ https và host apps.apple.com, country đúng. Không biến metadata thiếu thành 0. Logic retry:

```python
retryable = result.status in {429, 500, 502, 503, 504} or result.error == "timeout"
backoff_seconds = min(60.0, 2.0 ** attempt_index)
# Retry-After số giây hoặc HTTP-date được chuyển sang delay.
# Nếu delay > 300 giây: kết thúc lượt, ghi retry_after_pending; không retry sớm hơn.
# Nếu có delay <= 300: wait=max(backoff_seconds, delay), vẫn giữ khoảng request tối thiểu.
# 400/404 hoặc schema invalid: trả lỗi có body, không thử lại dồn.
```

- [x] **1.5 — Green và kiểm tra phạm vi.** Test HTTP với HTTPX MockTransport: 429 → 200, timeout hết 3 attempts, 400 chỉ 1 attempt, Retry-After dài không retry ngay. Clock fake chứng minh bắt đầu request cách ≥4 giây. Run lại hai file test và `ruff check src tests`; nếu repo có Git, commit nhóm file task này với message `feat: validate Apple Casual feeds`.

## Task 2: Lưu snapshot bất biến và metadata có phiên bản

**Files:** tạo storage/schema.sql, repository.py, raw.py; tạo `tests/test_storage.py` và `tests/test_metadata.py`.

**Consumes:** Chart/Entry/ParsedChart/HttpResult từ Task 1.

**Produces:**

- `Repository(data_dir: Path)` với `initialize() -> None`, `save_snapshot(run_id: str, result: HttpResult, parsed: ParsedChart) -> str`, `latest_complete(chart: Chart) -> dict | None`, `get_snapshot(snapshot_id: str) -> dict`, `save_metadata(country: str, values: dict[str, dict], result: HttpResult) -> dict[str, str]`, `cached_metadata(country: str, app_ids: list[str], now: datetime) -> dict[str, str]`, `bind_metadata(snapshot_id: str, versions: dict[str, str]) -> None`.
- `get_snapshot` trả id, entries (list dict gồm app_id/rank), quality, observed_at, source_updated, metadata_versions. Metadata chỉ bind trong run sở hữu snapshot; đóng run thì mapping đóng băng.
- `RawStore(root: Path).put(body: bytes) -> tuple[str, Path]`: SHA256, temp write rồi `os.replace`, không ghi đè nội dung khác dưới cùng hash.

- [x] **2.1 — Viết test snapshot complete rồi partial không đổi latest complete.** Fixture `repo` khởi tạo Repository bằng tmp_path; `complete_payload` từ Task 1. Fixture tạo run qua SQL seed chỉ trong test cho đến khi jobs API có ở Task 3.

```python
def test_partial_does_not_replace_latest_complete(repo, complete_payload, partial_payload):
    response, parsed = complete_payload
    first = repo.save_snapshot("run-1", response, parsed)
    response2, parsed2 = partial_payload
    repo.save_snapshot("run-2", response2, parsed2)
    assert repo.latest_complete(parsed.chart)["id"] == first
    assert len(repo.get_snapshot(first)["entries"]) == 100
```

- [x] **2.2 — Chạy red:** `python -m pytest tests/test_storage.py tests/test_metadata.py -q`.
- [x] **2.3 — Tạo schema.** Mỗi entity spec có bảng tương ứng: markets, charts, runs, market_runs, snapshots, entries, apps, metadata_versions, snapshot_metadata, raw_responses, request_observations. Thêm collector_lock ở Task 3. ID dùng UUID text, app ID luôn text. Khóa và transaction cốt lõi:

```sql
CREATE UNIQUE INDEX chart_identity ON charts(provider, platform, country, collection, genre, depth, version);
CREATE UNIQUE INDEX snapshot_per_market_run ON snapshots(market_run_id);
CREATE UNIQUE INDEX entry_app ON entries(snapshot_id, app_id);
CREATE UNIQUE INDEX entry_rank ON entries(snapshot_id, rank);
CREATE UNIQUE INDEX snapshot_metadata_once ON snapshot_metadata(snapshot_id, app_id);
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

Schema dùng INTEGER NOT NULL CHECK(rank>0), foreign key cho các tham chiếu; charts/runs/metadata/raw có các trường trong spec §5. Runs có request_key unique, trigger, status, start/end UTC. MarketRun có chart status/enrichment status riêng. Snapshot chỉ commit sau RawStore.put thành công. Giữ invalid raw và MarketRun lỗi mà không tạo snapshot complete. Giao dịch ghi một market ngắn, không giữ transaction khi gọi HTTP.

- [x] **2.4 — Hiện thực truy vấn và versioning.** `latest_complete` lọc đúng chart identity/quality, order observed_at và ID; bind metadata bằng app ID. Metadata quá TTL vẫn có thể hiển thị như stale nhưng không được coi cache fresh. Snapshot đã đóng run không rebind. `save_snapshot` cùng market_run trả lại snapshot đã lưu thay vì insert lại. Database không tự delete lịch sử.

```python
with connection:
    connection.execute("BEGIN IMMEDIATE")
    # Kiểm tra market_run chưa có snapshot; nếu có trả ID hiện hữu.
    # Insert snapshot + toàn bộ entries + raw reference trong cùng transaction.
    # Chỉ cập nhật trạng thái MarketRun sau khi entries hợp lệ đã được insert.
```

- [x] **2.5 — Green.** Thêm test rollback khi ghi raw lỗi, cùng ID ở VN/US giữ hai rank, retry không duplicate, metadata đảo thứ tự, metadata mới không thay bản xem lại của run cũ. Run hai file tests và Ruff; commit nếu có repo: `feat: persist immutable market snapshots`.

## Task 3: Collector, khóa tiến trình và CLI chạy độc lập

**Files:** tạo collection/service.py, jobs.py, processes.py, cli.py, __main__.py; mở rộng schema; tạo `tests/test_collection.py`, `tests/test_jobs.py`, `tests/test_cli.py`.

**Interfaces:**

- `JobService(repo).submit(trigger: str, countries: list[str], request_key: str) -> str`: trả run ID; request_key lặp trả run cũ; đang có run active trả run đó và không tạo job mới.
- `JobService.claim(run_id: str, pid: int, process_created_at: float) -> bool`, `heartbeat(run_id: str) -> None`, `finish(run_id: str, status: str) -> None`, `recover_dead_processes() -> list[str]`.
- `Collector(repo, provider, jobs).execute(run_id: str, enrich: bool = True) -> str`: trả final run status.
- `launch_collector(run_id: str, data_dir: Path) -> int`: PID của process nền hoặc báo launch error và đóng queued run failed.
- CLI: `python -m casual_scout init`, `collect --countries vn,us --data-dir PATH`, `work --run-id ID --data-dir PATH`, `serve --data-dir PATH`.

- [x] **3.1 — Red test điều phối.** FakeProvider trong conftest implement chính xác hai method Task 1, load raw fixtures, có `requested_countries` để kiểm tra TL không gọi. Fixture `collection_fixture` trả repo/provider/jobs/collector đã initialize.

```python
def test_lookup_failure_preserves_chart(collection_fixture):
    repo, provider, jobs, collector = collection_fixture
    provider.fail_lookup = True
    run_id = jobs.submit("manual", ["vn"], "request-1")
    assert collector.execute(run_id) == "partial"
    assert repo.latest_complete(provider.chart)["quality"] == "complete"
    assert "tl" not in provider.requested_countries
```

- [x] **3.2 — Chạy red:** `python -m pytest tests/test_collection.py tests/test_jobs.py tests/test_cli.py -q`.
- [x] **3.3 — Hiện thực claim/recovery.** Một hàng collector_lock có khóa singleton; `BEGIN IMMEDIATE` kiểm tra active queued/running và claim. PID kèm process create time để tránh tái sử dụng PID; psutil xác minh process trước recovery. Heartbeat lỗi/thất lạc không đủ để giết hoặc chiếm khóa process còn sống. Queued run không launch được phải failed; process chết đánh dấu interrupted, không xóa snapshot.
- [x] **3.4 — Hiện thực collector theo thứ tự:** claim → từng country fetch chart → lưu evidence/observations và snapshot → cache/Lookup các ID thiếu theo lô 20 → bind metadata → trạng thái MarketRun → finish. Nếu enrich=False thì enrichment=not_requested, không partial chỉ vì khảo sát không lấy metadata. Success yêu cầu tất cả thị trường nguồn khả dụng được yêu cầu có chart complete và metadata đạt hoặc not_requested; không có chart complete nào thì failed; còn lại partial. Mọi exception cuối run phải đóng trạng thái hoặc có thể recovery.
- [x] **3.5 — Hiện thực CLI và khởi chạy ẩn.** Dùng argparse; validate country allowlist. TL trả source_unverified không gọi mạng. Serve bind 127.0.0.1:8000. Child dùng cùng sys.executable/absolute data_dir, redirect output ra file runtime, không shell=True:

```python
subprocess.Popen(
    [sys.executable, "-m", "casual_scout", "work", "--run-id", run_id,
     "--data-dir", str(data_dir.resolve())],
    shell=False, creationflags=subprocess.CREATE_NO_WINDOW,
    stdout=log_file, stderr=subprocess.STDOUT,
)
```

- [x] **3.6 — Green:** test hai connection submit/claim đồng thời chỉ một run; request_key lặp không gọi nguồn; process chết trước/sau snapshot commit; cache fresh/expired; failed country không ngăn country khác; CLI work không chạy server. Chạy ba file test và regression Task 1–2 một lần sau thay đổi schema. Commit nếu có repo: `feat: run single-instance market collection`.

## Task 4: Web localhost với ba luồng màn hình

**Files:** tạo web/app.py, security.py, views.py, templates/base.html,data.html,runs.html,run.html,game.html,static/app.css; tạo `tests/test_web.py`, `tests/test_web_security.py`; cập nhật CLI serve.

**Interfaces:** `create_app(settings: Settings, launcher: Callable[[str, Path], int] = launch_collector) -> FastAPI`.

Routes: GET `/` (country/snapshot), GET `/runs`, GET `/runs/{id}`, GET `/games/{app_id}` (country/snapshot), GET `/runs/{id}/status`, GET `/evidence/{raw_id}`, POST `/runs`, POST `/runs/{id}/retry`. GET không gọi provider. Evidence lookup ID trong DB, không nhận đường dẫn filesystem từ request; trả download `application/octet-stream`.

- [x] **4.1 — Viết tests và chạy red.** Conftest `client` dùng FastAPI TestClient, tmp repository và launcher fake ghi lại arguments; không mở browser thật.

```python
def test_bad_origin_cannot_start_collection(client, launcher_calls):
    response = client.post("/runs", headers={"Origin": "https://example.org"},
                           data={"country": "vn", "request_key": "x"})
    assert response.status_code == 403
    assert launcher_calls == []
```

Chạy `python -m pytest tests/test_web.py tests/test_web_security.py -q`.

- [x] **4.2 — Hiện thực view models và HTML.** Trang dữ liệu mặc định VN/latest complete, có country/snapshot selector; TL hiển thị chưa xác minh. Hiển thị observed UTC chuyển Asia/Ho_Chi_Minh, source_updated riêng, cached metadata timestamp, status complete/partial/failed/stale/unknown. Trang game dùng metadata binding của snapshot, không lấy global newest. Chỉ link URL https từ nguồn đã validate; Jinja autoescape bật, không dùng safe cho mô tả.
- [x] **4.3 — Hiện thực form và run.** Session secret ngẫu nhiên lưu dưới data_dir, cookie HttpOnly/SameSite=Strict. CSRF token ký theo session; POST cần token và Origin localhost hợp lệ hoặc kiểm tra Referer khi thiếu Origin; reject khi cả hai không có. TrustedHost chỉ localhost/127.0.0.1, kiểm tra port configured. POST thành công tạo job qua JobService, gọi launcher rồi redirect 303 tới run; refresh GET không phát sinh run.

```python
run_id = jobs.submit("manual", countries, request_key)
# Chỉ launch nếu job vừa được tạo và chưa có PID; thao tác đánh dấu launch atomic.
return RedirectResponse(f"/runs/{run_id}", status_code=303)
```

- [x] **4.4 — Green:** valid token chạy được; invalid token/host/origin bị chặn; repeat POST cùng key chỉ một launch; mô tả `<script>` được escape; GET không gọi provider; màn hình thiếu/cũ/partial đúng; evidence path traversal không được mở. Poll status mỗi 2 giây chỉ lúc run active, dừng lúc terminal. Test elapsed POST bằng launcher fake xác nhận không thực thi collector trong request; không đặt ngưỡng latency tuyệt đối cho máy test. Run hai file test + Ruff; commit nếu có repo: `feat: add local collection web interface`.

## Task 5: Khảo sát giờ chạy, không backfill giả

**Files:** tạo operations/survey.py, scripts/Register-SurveyTask.ps1, scripts/Start-Web.ps1, `tests/test_survey.py`; mở rộng cli.py/schema.sql.

**Interfaces:**

- `survey_slots(start: datetime, end: datetime) -> list[datetime]`: UTC boundaries 00/06/12/18.
- `reconcile_slots(repo, now: datetime) -> datetime | None`: ghi missed cho các slot đã qua chưa quan sát; trả một slot hiện tại cần chạy, không trả hàng loạt.
- `survey_report(repo, start: datetime, end: datetime) -> dict`: theo slot trả observed/missed/request_count, error counts/status, median/p95 latency, source timestamp facts; không tự đặt lịch.
- CLI `survey --data-dir PATH` chạy JobService trigger survey và Collector enrich=False; `survey-report --days 7 --data-dir PATH` xuất JSON và Markdown cục bộ.

- [x] **5.1 — Viết tests và chạy red.** Không sử dụng đồng hồ thật hoặc sleep:

```python
from datetime import datetime, timezone
from casual_scout.operations.survey import survey_slots

def test_four_utc_slots():
    start = datetime(2026, 9, 10, tzinfo=timezone.utc)
    end = datetime(2026, 9, 11, tzinfo=timezone.utc)
    assert [t.hour for t in survey_slots(start, end)] == [0, 6, 12, 18]
```

Run `python -m pytest tests/test_survey.py -q`.
- [x] **5.2 — Hiện thực slot ledger.** Unique slot UTC; status pending/observed/missed. Restart sau nhiều slot bỏ lỡ chỉ một lần lấy hiện tại, observed_at là giờ thật; slot cũ không nhận snapshot hôm nay. Cửa sổ khảo sát đề xuất tối đa 30 phút từ boundary: quá cửa sổ thì ghi missed, lượt hiện tại là catch-up và không gán vào mẫu latency của boundary đã lỡ.
- [x] **5.3 — Hiện thực report.** RequestObservation gồm mọi attempt, timeout và rate-limit; ghi cả tỷ lệ thành công market/run để retry không che lỗi ban đầu. p95 dùng nearest-rank trên mẫu thực, nhóm có <20 mẫu nêu số mẫu nhỏ; median/p95 rỗng là null, không 0. Report thiếu 7 ngày hoặc có nhiều slot missed không kết luận khung tối ưu. Source updated không đổi không tự kết luận stale.
- [x] **5.4 — Script Scheduler có preview mặc định.** `Register-SurveyTask.ps1 -DataDir PATH [-Apply]` in XML trước; chỉ register khi Apply. Task name `ASOL-Casual-P1-Survey`; action executable venv tuyệt đối, module survey; lặp 6 giờ với StartBoundary UTC, StartWhenAvailable=true, MultipleInstances=IgnoreNew, WakeToRun=false. Chỉ dùng tài khoản hiện tại, không lưu password hoặc nâng quyền tự động. Script chạy task ẩn. Không thay power settings. Start-Web.ps1 dùng Start-Process -WindowStyle Hidden, bind localhost và thông báo URL, không mở cổng mạng.

```powershell
# XML có StartBoundary dạng 2026-09-11T00:00:00Z, Interval PT6H.
if ($Apply) {
    Register-ScheduledTask -TaskName 'ASOL-Casual-P1-Survey' -Xml $taskXml
} else {
    Write-Output $taskXml
}
```

- [x] **5.5 — Green:** fake collector chứng minh survey không enrichment; missed slot không backfill; double invocation cùng slot không hai run; timezone không phụ thuộc locale Windows. Kiểm tra XML/action/working directory/flags bằng PowerShell trước đăng ký. Commit nếu có repo: `feat: add measured scheduling survey`.

## Task 6: Backup, khôi phục và hướng dẫn Windows

**Files:** tạo operations/backup.py, README.md, docs/operations/p1-runbook.md; mở rộng CLI; tạo `tests/test_backup.py`.

**Interface:** `create_backup(repo: Repository, destination: Path) -> Path` trả manifest; CLI `backup --destination PATH --data-dir PATH`. Backup mặc định thủ công.

- [x] **6.1 — Viết red test:** backup sau một snapshot, tạo snapshot thứ hai sau khi backup bắt đầu, restore ở tmp path; database restored chỉ tham chiếu raw/metadata có trong manifest, không mất dữ liệu đã commit tại thời điểm snapshot backup.

```python
def test_backup_includes_all_referenced_raw(repo_with_snapshot, tmp_path):
    import json
    from casual_scout.operations.backup import create_backup
    manifest_path = create_backup(repo_with_snapshot, tmp_path / "backup")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["database"] == "scout.sqlite3"
    for raw in manifest["raw_files"]:
        assert (manifest_path.parent / raw["path"]).is_file()
```

Run `python -m pytest tests/test_backup.py -q`.
- [x] **6.2 — Hiện thực sqlite backup API trước, query raw references từ database backup, copy đúng các file immutable đó, kiểm tra SHA256, ghi manifest cuối cùng.** Không copy file database live bằng shutil đơn thuần; không ghi backup chồng lên data_dir; thiếu raw → backup failed và không công bố manifest complete.

```python
with sqlite3.connect(source_db) as source, sqlite3.connect(backup_db) as target:
    source.backup(target)
```

- [x] **6.3 — Viết runbook có lệnh thực tế.** Hướng dẫn tạo venv/install lock, init, serve, collect VN rồi toàn phạm vi, survey preview/apply, đọc report, backup/restore sau dừng web/collector. Ghi cách xem last error, recovery interrupted, máy sleep gây missed; no downloads; nguồn TL chưa xác minh; giờ production chưa chọn. Unregister chỉ task tên cố định; không xóa dữ liệu trong lệnh gỡ task. Ghi cách kiểm tra disk usage và giữ data_dir ngoài thư mục raw evidence khảo sát.
- [x] **6.4 — Green:** thiếu raw, hash sai và destination bên trong data_dir đều bị từ chối; restored DB foreign keys/integrity hợp lệ. Run backup test và Ruff; commit nếu có repo: `feat: add local backup and Windows runbook`.

## Task 7: Nghiệm thu P1 và bắt đầu pilot lịch riêng

**Files:** tạo `tests/test_p1_acceptance.py`, `docs/operations/p1-acceptance.md`; sửa bug đúng module nếu phép kiểm tra tìm thấy lỗi.

- [x] **7.1 — Viết integration test offline hoàn chỉnh:** fake Apple HTTP → collector → SQLite/raw → TestClient. Bao phủ VN complete, US lookup partial, TL unverified, chạy lại request_key không duplicate, GET snapshot cũ giữ metadata cũ. Các assertions so kết quả với raw fixture, không chỉ so với helper implementation.
- [x] **7.2 — Chạy bộ kiểm tra cuối một lần:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pip check
```

Expected: tests pass, lint sạch, dependencies hợp lệ. Ghi số test thực và lỗi nếu có; không đưa expected thành kết quả đã chạy.
- [x] **7.3 — Live smoke nhỏ:** init data_dir mới, collect VN một lượt, mở web localhost, kiểm tra 100 vị trí đúng feed và timestamp/raw; thiếu metadata phải hiển thị đúng. Kiểm tra không leak process/khóa. Sau smoke nhỏ đạt mới chạy 11 thị trường khả dụng một lượt, ghi observed count và lỗi thực. Không ép số 100 nếu nguồn đã đổi; chuyển sang điều tra schema theo spec.
- [x] **7.4 — Crash/recovery và backup smoke:** dừng collector thử ở môi trường test, khởi động lại, xác nhận old snapshot giữ nguyên và run interrupted; restore backup sang data_dir khác, mở web read-only để đối chiếu.
- [x] **7.5 — Ghi nghiệm thu chức năng và readiness pilot:** báo phần đã chạy, còn thiếu và version lock thực. Có thể nghiệm thu chức năng P1 khi offline/live/error/recovery/web checks đạt; chưa đánh dấu DEC-09 giờ production hoàn tất.
- [x] **7.6 — Bắt đầu khảo sát khi chức năng ổn định:** preview XML rồi cài task đúng phạm vi đã chọn, lưu lần bắt đầu và tập giờ; chạy trên máy thật ít nhất 7 ngày đủ hoạt động. Không chờ 7 ngày trong một tool call. Đánh giá report và chọn lịch production trong lần rà soát sau, chỉ khi bằng chứng đủ. Nếu máy tắt nhiều thì báo chưa đủ mẫu và đề xuất kéo dài; không bịa kết quả hoặc chuyển server trả phí.
- [x] **7.7 — Review kết quả và commit nếu có repo:** `docs: record P1 acceptance and survey readiness`. Báo rõ nếu không commit do chưa có Git; không tự tạo PR/remote.


## Ma trận phủ thiết kế và tự rà soát kế hoạch

| Spec / PRD | Task thực hiện |
|---|---|
| Nguồn Casual/depth100, TL, genre nguồn; BA-R01/02/09 | 1, 3, 4 |
| Snapshot bất biến, metadata phiên bản, raw; BA-R03 | 2, 6 |
| Một collector, retry/throttle/cache, phục hồi; BA-R04 | 1, 3 |
| Ba màn hình localhost, job nền, CSRF/Host/Origin | 4 |
| Khảo sát lịch, missed slot và không backfill; DEC-09 | 5, 7 |
| Chi phí free-first, không fallback trả phí; BA-R12 | 1, 3, 6 |
| Backup/disk/retention, kiểm chứng end-to-end | 6, 7 |
| Không P2–P4; giữ thứ tự requirement | Global Constraints, task 4/7 scope review |

Kế hoạch tự rà soát: mỗi interface được khai báo ở task sản xuất; raw fixture hiện có và không sửa; test sử dụng temporary data_dir. Các mục pilot là công việc tương lai có cách đo, không là chỗ trống trong chức năng P1. Không có code ứng dụng hoặc test nào được chạy chỉ bằng việc tạo tài liệu này.

## Bàn giao thực thi

Đề xuất thực thi tuần tự trong phiên bằng executing-plans, checkpoint sau Task 2 (nguồn/lưu trữ), Task 4 (collector/web) và Task 7 (nghiệm thu). Nếu người dùng chọn subagent-driven-development thì chia theo task và review từng phần; không giao cùng lúc các task đang phụ thuộc schema/interface chưa ổn định. Việc chọn cách thực thi không mở lại thiết kế A đã duyệt.

