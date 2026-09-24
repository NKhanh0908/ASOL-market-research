# Casual Scout Galaxy UI/UX Redesign

**Date:** 2026-09-24
**Status:** Design approved in chat by sections; awaiting written-spec review.
**Scope:** Laptop-first visual and interaction cleanup across the existing web UI.
**Out of scope:** Changes to collectors, API contracts, analysis/scoring, database, scheduling semantics, and mobile-specific product design.

## 1. Basis and goals

The request is to make the current interface cleaner and easier to operate without changing what the product does. The user approved a shared-shell-first approach, laptop-first layout, a Galaxy/space visual direction, and inline SVG icons paired with text labels. Phone use should remain responsive, but this is not a phone-first redesign.

Repository inspection shows eight Jinja templates (`base`, `dashboard`, `data`, `android`, `shortlist`, `runs`, `run`, `game`) sharing `base.html` and `app.css`. Dashboard and Data contain substantial inline styling; Android has a separate stylesheet. The existing UI uses a dark navy palette and a horizontal navigation bar. This is code inspection, not a usability study or a claim based on observed user sessions.

### Goals

- Make navigation, page headers, controls, tables, cards, status badges, and spacing consistent.
- Reduce visual competition and make the primary task on each screen easy to find.
- Keep market data and collection state prominent; move secondary details lower or into compact disclosure areas without hiding critical failures.
- Use a restrained Galaxy-inspired palette while preserving readable data contrast.
- Preserve every current route, interaction, and business rule unless this spec explicitly clarifies misleading date language.

### Success criteria

- A user can identify the active page and its primary action at a glance.
- The market/date/chart controls are grouped in a compact toolbar and their labels distinguish stored data from scheduled collection.
- Android's in-progress batches remain visible immediately as they are processed.
- Partial, failed, stale, empty, and mock data states remain explicit and recoverable.
- Existing routes and collection/analysis results remain unchanged.

## 2. Proposed visual system

### Direction

Use a restrained Galaxy space theme: deep navy surfaces, indigo/violet accents, restrained cyan highlights, and subtle gradients/glow limited to selected accents. Do not use a starfield or decorative nebula background behind data. Keep the existing dark theme as the base rather than switching to light mode.

### Shared shell

- Keep a compact horizontal navigation sized for laptop viewports. Labels: **Tổng quan**, **iOS**, **Android**, **Shortlist**, **Lịch sử**. Map to the existing dashboard, data, Android, shortlist, and run-history routes; do not change URLs.
- Clearly distinguish the active destination using text/color and an accessible non-color cue such as an underline or filled tab.
- Standardize page title, one-line purpose, primary action placement, content width, card padding, button height, table density, and status badge treatment.
- Use shared CSS variables/classes from the shared stylesheet rather than accumulating page-specific inline styles. Android-specific layout may retain a small stylesheet but must use the same tokens and primitives.
- Keep focus indicators visible and use semantic links/buttons. SVG icons are decorative when paired with labels (`aria-hidden="true"`); icon-only controls require an accessible name and tooltip/title.
- Implement simple icons as small local inline SVGs; do not require the user to supply assets or add an icon package/CDN.

### Layout and responsiveness

- Optimize the primary layout for laptop screens around 1280 px and wider; use available width efficiently without making data tables unreadably wide.
- Retain responsive behavior below laptop width: controls may wrap, navigation may wrap or compact, and wide tables may scroll horizontally. This is baseline compatibility only, not the separately envisioned phone experience.

## 3. Page hierarchy and interactions

### Tổng quan (Dashboard)

1. Place date and market filters in one compact toolbar.
2. Show the collection status and primary crawl action in a concise operations panel.
3. Put high-value KPIs and the opportunity/radar list ahead of secondary charts.
4. Keep charts available below the primary summary; preserve current filters and export behavior.

The date control means **analysis/data date** and is populated from existing analytics dates. It selects stored project data; it must not imply that Apple can return historical chart contents on demand.

### iOS (Data)

1. Place market, Top Free/Top Grossing, and stored snapshot selection in one toolbar.
2. Keep the current snapshot timestamp, quality, evidence download, and CSV export available in a compact metadata row.
3. Keep the game table as the main content; place signal filters/counts near it and avoid duplicating actions in multiple panels.
4. Group **Crawl ngay**, the one-time future schedule, and daily schedule status/settings under a compact collection control area. Keep the immediate action visually primary.

### Android

1. Place **Crawl Android ngay**, current status, and progress at the top.
2. Keep results directly below and visible as each batch is processed; do not wait for the full crawl to finish before rendering them.
3. Keep chart type and run-history selectors close to results.
4. Reduce secondary copy and error details without hiding failures, retry guidance, processed/total counts, batch state, or last-updated time.

### Shortlist, Lịch sử, and game detail

- Reuse shared page headers, toolbars, cards, tables, button hierarchy, form controls, and status treatments.
- Keep existing edit/export/detail links and collection-run status behavior intact.
- Do not remove secondary features solely to reduce visual density; reorganize or compact them.

## 4. Date and collection semantics (confirmed from code)

Three different concepts must remain distinct:

1. **Apple current-chart collection:** `AppleProvider.fetch_chart(chart)` calls `_chart_url(chart)`, which uses country, feed, depth, and genre; it has no historical-date parameter. The current Apple RSS provider therefore cannot request a past chart snapshot for an arbitrary date.
2. **Historical project-data selection:** Dashboard analysis date and Data snapshot selector choose records already stored in SQLite. The `/api/charts/grossing` route looks up a complete snapshot for a requested date; it does not call Apple.
3. **One-time future collection schedule:** `/api/one-time-schedule` accepts a future local date/time, stores the schedule, and the scheduler creates an iOS VN Top Free collection run when due. This is a real supported feature and must be retained. `tests/test_one_time_schedule.py` verifies due-time launch/idempotence; `tests/test_web.py` verifies schedule submission/persistence.

UI wording must say **Ngày dữ liệu** / **Bản chụp đã lưu** for historical selection and **Lên lịch crawl** / **Thời điểm chạy** for the future schedule. Do not advertise “crawl API theo ngày lịch sử.” If any legacy control suggests that capability, remove or relabel only that misleading control, not the functioning future schedule or stored-date filters.

## 5. State, errors, and recovery

- **Empty:** explain what action creates data and keep that action visible.
- **Loading:** use a compact status/skeleton while preserving the page frame; Android must continue showing incoming batch results.
- **Running:** show status, progress/processed count, and updated time; prevent duplicate action only as current backend rules require.
- **Partial/failed/interrupted:** label the state clearly, retain any valid data, show a concise actionable explanation, and link to run details where available. Never style partial as complete.
- **Stale:** show observation/last-success time so old data is not mistaken for current.
- **Mock:** preserve the prominent warning that demo values are simulated and not historical Apple data.
- **Validation/network error:** retain user-entered schedule values when possible, show an inline message, and keep keyboard focus/semantic status behavior usable.

## 6. Existing behavior and implementation boundaries

Known routes include `/dashboard`, `/data`, `/android`, `/shortlist`, `/runs`, `/runs/{run_id}`, and `/games/{country}/{app_id}`. The redesign should be presentation-only. It must not change provider calls, scheduling cadence/semantics, database writes, ranking thresholds, taxonomy, export format, CSRF/security checks, or Android batch order.

Relevant current sources: `src/casual_scout/web/templates/*.html`, `src/casual_scout/web/static/app.css`, `src/casual_scout/web/static/android.css`, `src/casual_scout/web/static/android.js`, `src/casual_scout/web/app.py`, and `src/casual_scout/web/views.py`. Existing Android-related files have uncommitted user work; implementation must preserve and work around those changes.

## 7. Verification contract

Planned checks (not yet executed for this design):

- Render every route and verify the shared navigation, active state, title, and no template errors.
- Check laptop viewport layout for all major pages, especially table/toolbars and long Vietnamese labels.
- Check a narrower viewport for wrapping/overflow and horizontal table scroll without claiming a phone-optimized redesign.
- Verify keyboard focus visibility, semantic button/link roles, icon labels, and status announcements.
- Verify filters, snapshot/date selection, exports, shortlist edits, and navigation still use their existing URLs and behavior.
- Verify future iOS schedule controls retain labels and flow; verify historical date controls never imply a live historical API request.
- Verify Android batch results remain visible incrementally and error/partial states remain explicit.
- Run focused web tests and the full test suite before claiming implementation complete.

No external user study has been conducted. A useful optional follow-up would be a short task-based walkthrough with the project owner after implementation; the decision it should inform is whether the three core tasks—inspect opportunities, review store data, and start/schedule collection—are faster to locate. Do not contact participants or collect user data without separate approval.

## 8. Open implementation details

- Exact spacing, radius, and color tokens should be derived from current styles and checked in a rendered browser; no external design-system package is approved.
- Whether to collapse secondary Dashboard charts behind a disclosure is not settled; default to keeping them visible lower on the page unless page length proves materially distracting.
- The nav label **iOS** should be paired with clarifying subtext/title such as “Dữ liệu iOS” where needed; keep the user-facing label short.
