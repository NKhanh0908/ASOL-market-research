# Thiết kế — Thu thập Google Play Android Top Free Casual VN

**Ngày:** 2026-09-22
**Trạng thái:** Đã duyệt thiết kế; chờ duyệt spec và lập kế hoạch triển khai

## Mục tiêu

Mở rộng Casual Scout để thu thập bảng **Top Free Casual Việt Nam** trên Google Play mỗi ngày lúc 07:00 theo `Asia/Ho_Chi_Minh`. Người dùng vận hành hoàn toàn trên Dashboard: chạy ngay bằng nút và bật/tắt lịch nội bộ của web server. Sau mỗi lần thu thập, hệ thống lưu evidence bất biến, lấy metadata game, rồi chạy phân tích hiện có cho Android.

## Phạm vi MVP

- Chỉ Android / Google Play / Việt Nam (`gl=VN`, giao diện `hl=vi`).
- Chỉ chart Top Free của category Casual (`GAME_CASUAL`).
- Nhận toàn bộ item mà trang công khai thực tế trả về; lưu số lượng nhận được và hợp lệ, không cam kết Top 100.
- Lấy metadata theo package name: title, developer, category, rating, rating count, mô tả, icon, URL store, price/currency và mọi tín hiệu hiển thị được về ads/IAP.
- Không dùng API trả phí, Google Play Developer API, Windows Task Scheduler, captcha bypass, đăng nhập, hay né giới hạn địa lý.
- Không suy diễn downloads, doanh thu, ads hay IAP từ rank hoặc từ trường thiếu.

## Nguồn và nguyên tắc thu thập

Nguồn chart là trang Google Play công khai cho Casual tại Việt Nam. Google Play Developer API không được dùng vì phục vụ publishing/quản trị ứng dụng của tài khoản sở hữu, không cung cấp chart đối thủ.

`GooglePlayProvider` dùng user-agent nhận diện Casual Scout, request tuần tự với rate limit, retry hữu hạn và metadata cache TTL. Raw HTML chart và metadata được lưu qua raw store hiện có theo content hash. Response 403, captcha, redirect đăng nhập, hay HTML không nhận diện được phải kết thúc có kiểm soát với lỗi có thể xem lại; không có cơ chế bypass.

## Kiến trúc

### Provider và collection chung

Thêm `GooglePlayProvider` cùng protocol với Apple provider:

```python
fetch_chart(chart: Chart) -> tuple[HttpResult, ParsedChart]
fetch_metadata(country: str, app_ids: list[str]) -> tuple[HttpResult, dict[str, dict]]
```

Chart Android có identity cố định:

```python
Chart(
    country="vn",
    provider="google-play",
    platform="android",
    collection="top-free-casual",
    genre="GAME_CASUAL",
)
```

Package name là `source_app_id`. Các bảng `charts`, `apps`, `snapshots` và `metadata_versions` đã phân tách bằng `provider` + `platform`, nên không cần schema mới cho identity. `Collector` được tổng quát hóa để factory chọn provider phù hợp với chart; raw store, retry, snapshot, metadata version và `AnalysisService` được tái sử dụng.

### Worker nội bộ và lịch tuần tự

Không thêm CLI Android cho người vận hành. Dashboard và scheduler gọi launcher nội bộ để mở process worker riêng cho Android; process này có entry point kỹ thuật riêng nhưng không được ghi thành lệnh vận hành công khai.

Thêm cấu hình `android_daily_schedule`, mặc định tắt, với `07:00`, `Asia/Ho_Chi_Minh`, `vn`, `top-free-casual` và ngày đã trigger gần nhất.

Vì collector lock hiện tại là global, coordinator nội bộ phải lưu một queue daily bền vững theo `platform` + `local_date`. Đúng 07:00, coordinator claim ngày cho iOS và Android, tạo hai item pending theo thứ tự iOS rồi Android. Nó chỉ dispatch item đầu khi không có run `queued`/`running`; sau khi iOS terminal (`succeeded`, `partial`, `failed`, hoặc `interrupted`), poll loop dispatch Android. Nếu iOS lỗi, Android vẫn chạy. Restart server không tạo lịch mới sau 07:00, nhưng có thể tiếp tục dispatch item pending đã được tạo trước đó. Không có hai worker collector chạy đồng thời.

Nút **Crawl Android ngay** tạo một item Android manual và dispatcher chạy item này khi lock rảnh; nếu Android đang pending/running, UI trả trạng thái hiện có thay vì tạo trùng.

## Web và API

Dashboard thêm card **Thu thập Android VN** cạnh iOS:

- Nút `Crawl Android ngay`.
- Toggle lịch 07:00, disabled mặc định.
- Trạng thái lần chạy gần nhất, số game hợp lệ, thời gian và link run detail/log.
- Cảnh báo: `Lịch chỉ chạy khi web server còn hoạt động.`

API nội bộ, đều yêu cầu local-origin và CSRF ở endpoint thay đổi trạng thái:

- `GET /api/android/schedule`: config persisted và Android run gần nhất.
- `PATCH /api/android/schedule` body đúng `{"enabled": true|false}`.
- `POST /android/runs`: tạo Android manual run từ Dashboard; không nhận provider, country hay chart type do người dùng nhập.

Data/Dashboard thêm filter `platform=ios|android|all`. Giá trị mặc định giữ `ios` để không thay đổi trải nghiệm hiện tại. Tất cả game detail, snapshot và analytics query phải giữ `provider` + `platform` trong join/filter để tránh lẫn source ID giữa App Store và Google Play.

## Chất lượng, lỗi và trạng thái

- `received_count`: số item parser tìm thấy; `valid_count`: item có package name và trường tối thiểu.
- Nếu chart hợp lệ nhưng metadata lỗi từng phần, snapshot chart vẫn lưu và run `partial`.
- Nếu chart HTML không parse được, run `failed` hoặc `partial` theo quy tắc collector; raw evidence và lỗi parser luôn còn lại.
- Trường ads/IAP không nhìn thấy được ghi `unknown`/`null`, không ghi `false`.
- Không chạy bù lịch bị lỡ khi web server tắt lúc 07:00.

## Technical contract

### Thay đổi model và provider boundary

`Chart.__post_init__()` hiện luôn chuẩn hóa collection thành Apple Top Free/Top Grossing. Migration code phải đổi quy tắc này: chỉ chuẩn hóa khi `provider == "apple"`; `GooglePlayProvider` giữ nguyên `collection="top-free-casual"` và `genre="GAME_CASUAL"`.

`Collector` phải reconstruct chart từ toàn bộ identity lưu trong `charts`, gồm `provider`, `platform`, `country`, `collection`, `genre`, `depth`, `version`; không được dùng default Apple/iOS. Thêm registry bất biến:

```python
ProviderFactory = Callable[[Settings], MarketProvider]
PROVIDERS: dict[tuple[str, str], ProviderFactory] = {
    ("apple", "ios"): AppleProvider,
    ("google-play", "android"): GooglePlayProvider,
}

def provider_for(chart: Chart, settings: Settings) -> MarketProvider: ...
```

Do Google Play metadata là nhiều page độc lập, provider contract thay `fetch_metadata()` bằng kết quả evidence theo từng app:

```python
@dataclass(frozen=True, slots=True)
class MetadataFetch:
    app_id: str
    result: HttpResult
    values: dict[str, object] | None

class MarketProvider(Protocol):
    def fetch_chart(self, chart: Chart) -> tuple[HttpResult, ParsedChart]: ...
    def fetch_metadata(self, country: str, app_ids: list[str]) -> list[MetadataFetch]: ...
```

Apple provider trả một `MetadataFetch` cho mỗi app, cùng `HttpResult` batch lookup; Google Play trả một `MetadataFetch` cho mỗi URL chi tiết. Collector lưu từng `result` có body qua `save_metadata()`, bind các metadata version nhận được, và đánh dấu enrichment `complete`/`partial`/`failed` dựa trên số `app_id` có version mới hoặc cache hợp lệ.

`JobService.submit()` nhận `charts: list[Chart]` thay cho `countries`/`chart_types` ở call site mới. Một adapter giữ syntax iOS cũ trong giai đoạn migration. Android manual tạo đúng một chart constant; backend không đọc chart/provider/country từ body HTTP.

### Source contract và parser Google Play

Request chart chuẩn:

```text
GET https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN
Accept-Language: vi-VN,vi;q=0.9
User-Agent: CasualScout/1.0 (+local-market-research)
```

Không dùng CSS class minified. Parser xác định section Top Free bằng heading locale-independent được fixture hóa từ URL thực tế, sau đó chỉ nhận anchor có dạng `/store/apps/details?id=<package>` trong section đó. `package` phải khớp `^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$`; package duplicate giữ lần xuất hiện đầu. Rank là index 1-based của item hợp lệ trong thứ tự section. Title lấy text/accessibility label của item; developer, icon và category chỉ lấy khi gắn với cùng card. `source_updated=None` vì Play page không công bố timestamp chart.

Parser tạo:

```python
ParsedChart(
    chart=android_chart,
    entries=entries,
    source_updated=None,
    quality="complete" if entries else "invalid",
    issues=[] if entries else ["top_free_casual_section_missing"],
)
```

Nếu section tìm thấy nhưng có package bị loại, quality là `partial` và `issues` chứa `invalid_package:<ordinal>`; snapshot vẫn lưu raw HTML. Metadata request là `https://play.google.com/store/apps/details?id=<package>&hl=vi&gl=VN`. Parser metadata chỉ điền trường mà markup công khai thể hiện. `values_json` luôn có `{"ads_observed": true|false|null, "iap_observed": true|false|null}`; `has_in_app_purchases` chỉ là `1` khi evidence có IAP, còn không thấy là `0` nhưng `iap_observed=null` phải được view/analysis ưu tiên thay vì diễn dịch 0 là không IAP.

### Migration SQLite chi tiết

Hai bảng analytics hiện có khóa theo `(date, country)` và `(date, country, app_id)`, không đủ để chứa iOS + Android VN cùng ngày. `Repository.initialize()` phải thực hiện migration transaction-safe, idempotent:

1. `CREATE TABLE daily_canonical_snapshots_v2` với `provider TEXT NOT NULL`, `platform TEXT NOT NULL`, `collection TEXT NOT NULL` và primary key `(date, country, provider, platform, collection)`.
2. Copy row cũ với `provider='apple'`, `platform='ios'`, `collection='topfreeapplications'`; drop bảng cũ, rename `_v2`, rồi tạo index date/country/platform.
3. `CREATE TABLE daily_rank_analytics_v2` với `provider TEXT NOT NULL`, `platform TEXT NOT NULL`, thêm hai field đó vào uniqueness `(date, country, provider, platform, app_id)` và index `(date, country, platform)`.
4. Copy toàn bộ field cũ với `provider='apple'`, `platform='ios'`; swap table và khôi phục index signal/app theo provider/platform.
5. Tạo `android_daily_schedule` one-row table với schema tương đương `daily_schedule`, nhưng constant `country='vn'`, `chart_type='top-free-casual'`, `platform='android'` và `provider='google-play'`.
6. Tạo `daily_dispatch_queue`:

```sql
CREATE TABLE daily_dispatch_queue (
    id TEXT PRIMARY KEY,
    local_date TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
    provider TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'dispatched', 'terminal')),
    trigger TEXT NOT NULL CHECK (trigger IN ('daily', 'manual')),
    run_id TEXT REFERENCES runs(id),
    request_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    dispatched_at TEXT,
    terminal_at TEXT,
    UNIQUE(local_date, platform, trigger)
);
```

Daily entries use `trigger='daily'`; manual Android entries use `local_date` equal to the local creation date and a random request key, so they remain independently idempotent. All migrations run before inserting default schedule rows. Existing data remains read-only except copying into the replacement analytics tables; raw snapshots/entries are never rewritten.

### Coordinator state machine

`DailyCollectionCoordinator(repo, launch_ios, launch_android, now)` replaces the single-platform `DailyScheduler` as the FastAPI lifespan service.

```python
def check_once(self) -> list[str]: ...
def enqueue_daily_pair(self, local_date: str) -> list[str]: ...
def enqueue_android_manual(self, request_key: str) -> str: ...
def dispatch_next(self) -> str | None: ...
```

At exactly 07:00 local, it atomically claims each enabled schedule and inserts its daily queue row. `dispatch_next()` selects the oldest `pending` row under `BEGIN IMMEDIATE`, but only if no `runs.status IN ('queued', 'running')`. It creates one run, sets queue state `dispatched`, stores `run_id`, then calls the platform launcher after the transaction commits. On each 30-second poll, it converts `dispatched` to `terminal` when the linked run is terminal and dispatches the next row. Launcher failure sets the run `failed` and queue `terminal` with a launch error in run summary. Restart keeps queue rows and resumes dispatch only; it never creates a new daily row when now is later than 07:00.

The iOS queue row precedes Android by `created_at` plus a deterministic platform order. The Android row is dispatched after iOS terminal even when iOS failed. Manual Android rows are appended behind already-running work; a second manual request with an active Android queue/run returns that run ID.

### Analysis and query contract

`AnalysisService.analyze_date()` gains required keyword-only context:

```python
def analyze_date(
    self,
    date_str: str,
    countries: list[str] | None = None,
    *,
    provider: str = "apple",
    platform: str = "ios",
    collection: str = "topfreeapplications",
) -> dict[str, object]: ...
```

Canonical lookup, current/past snapshots, grossing pairing, cross-market presence, and writes all filter by this context. Android analysis uses `provider="google-play"`, `platform="android"`, `collection="top-free-casual"`; it does not query or manufacture a grossing rank. UI repository queries that currently literal-filter Apple/iOS must accept the same context. Default remains Apple/iOS for backward compatibility.

### HTTP/API/UI contract

```http
GET /api/android/schedule
200 {"enabled": false, "time": "07:00", "timezone": "Asia/Ho_Chi_Minh",
     "country": "vn", "chart_type": "top-free-casual", "last_triggered_local_date": null,
     "last_run": null, "queue_state": null}

PATCH /api/android/schedule
X-CSRF-Token: <token>
{"enabled": true}
200 <persisted schedule object>
422 {"detail": "enabled must be a boolean"}

POST /android/runs
Origin: http://127.0.0.1:8000
csrf_token=<token>
303 Location: /runs/<run_id>
```

`/dashboard` renders an Android card with loading/queued/running/succeeded/partial/failed state and disabled crawl button only while an Android item is pending or active. The platform selector is query parameter `platform=ios|android|all`; invalid input returns HTTP 400. `all` displays platform-tagged separate rows and never combines rank deltas or cross-market counts across platforms.

### Exact test matrix

| Layer | Fixture / setup | Assertions |
|---|---|---|
| Provider chart | saved VN HTML with section and three packages | ranks 1–3, `google-play/android`, package IDs, complete quality |
| Provider malformed | no target heading; one bad package; duplicated package | invalid/no snapshot candidate; partial issues; first duplicate only |
| Metadata | app page with/without ads/IAP labels | raw response persisted per app; observed flags are true/false/null, no invented IAP |
| Storage migration | populated iOS canonical/analytics DB then initialize | legacy rows visible as Apple/iOS; Android same app ID/date inserts without uniqueness error |
| Collector | Android fake provider with one metadata failure | chart persists; evidence exists; enrichment/run is partial |
| Coordinator | frozen 07:00; iOS and Android schedules enabled | two queue rows, iOS launches first, Android launches only after iOS terminal, failed iOS still unlocks Android |
| Recovery | pending Android row and frozen 07:01 after restart | dispatches pending row; does not insert a new daily row |
| Web | TestClient plus fake coordinator/launchers | CSRF enforcement, fixed Android chart, toggle persistence, Android card and platform filters |

## Kiểm thử nghiệm thu

- Fixture parser bao phủ chart đúng, package name thiếu, HTML đổi cấu trúc, metadata thiếu ads/IAP.
- Android và iOS có cùng numeric/source ID không tạo cùng `app_ref`.
- Collector lưu raw evidence Android, giữ chart khi metadata partial, và chạy analysis Android sau terminal success/partial.
- Coordinator tại 07:00 tạo iOS rồi Android tuần tự; không duplicate, Android vẫn dispatch sau iOS failed, restart chỉ tiếp tục pending item.
- API toggle yêu cầu CSRF; nút Dashboard tạo đúng chart Android cố định.
- Filter Android/iOS/all cho data và dashboard; regression iOS hiện có giữ nguyên.

## Giới hạn vận hành

Scheduler chỉ hoạt động khi `serve` đang chạy và máy có kết nối mạng. Google Play có thể thay đổi markup/giới hạn truy cập; khi đó MVP phải báo lỗi evidence-backed, không có cam kết uptime hoặc độ sâu danh sách cố định.
