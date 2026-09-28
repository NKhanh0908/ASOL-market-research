# Casual Scout Galaxy UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the existing Casual Scout web UI with a restrained Galaxy theme and clearer laptop-first workflows while preserving every current page, route, interaction, and business rule.

**Architecture:** Keep the existing FastAPI routes, Jinja templates, and page-specific behavior. Build a shared visual foundation in `base.html` and `app.css`, then apply it page-by-page to the seven page templates; keep Android-specific behavior and JavaScript intact, and use only small local inline SVGs without adding an icon dependency.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTML, CSS, inline SVG, pytest; browser inspection for responsive and visual verification.

**Spec:** `docs/superpowers/specs/2026-09-24-galaxy-ui-ux-redesign-design.md`

## Global Constraints

- “Use a restrained Galaxy space theme: deep navy surfaces, indigo/violet accents, restrained cyan highlights, and subtle gradients/glow limited to selected accents.”
- “Do not use a starfield or decorative nebula background behind data.”
- “Keep the existing dark theme as the base rather than switching to light mode.”
- “Preserve every current route, interaction, and business rule unless this spec explicitly clarifies misleading date language.”
- “Implement simple icons as small local inline SVGs; do not require the user to supply assets or add an icon package/CDN.”
- “Optimize the primary layout for laptop screens around 1280 px and wider.”
- Keep all seven content pages and their current URLs: `/dashboard`, `/data` (and existing `/` alias), `/android`, `/shortlist`, `/runs`, `/runs/{run_id}`, `/games/{country}/{app_id}`.
- On narrow screens, do not wrap clickable navigation labels onto multiple lines; use a compact, accessible navigation treatment while keeping every destination reachable. This resolves the Hallmark audit finding without creating a phone-specific product redesign.
- Do not alter collector/provider calls, API contracts, database writes, schedule cadence/semantics, ranking thresholds, taxonomy, export formats, CSRF/security checks, or Android batch order.
- Historical date controls select stored project data; they do not request historical Apple charts. Preserve the working one-time future iOS collection schedule and label it as VN Top Free where its scope is shown.
- Preserve existing user changes, especially Android live-collection files; inspect `git status` before editing and do not revert or overwrite unrelated work.

---

## File map

- `src/casual_scout/web/templates/base.html`: shared page shell, navigation labels/active state, common banner and footer structure, shared script/style loading.
- `src/casual_scout/web/static/app.css`: Galaxy tokens, common layout/components, accessible focus states, responsive navigation and table overflow behavior.
- `src/casual_scout/web/templates/dashboard.html`: dashboard hierarchy, filters, collection summary, KPIs, radar/opportunities, charts and exports.
- `src/casual_scout/web/templates/data.html`: iOS market/snapshot toolbar, metadata, game table, immediate collection and schedule controls.
- `src/casual_scout/web/templates/android.html`, `src/casual_scout/web/static/android.css`, `src/casual_scout/web/static/android.js`: Android presentation only; preserve incremental rendering and polling contracts.
- `src/casual_scout/web/templates/shortlist.html`: shortlist filters, edits, export, and game links.
- `src/casual_scout/web/templates/runs.html`, `src/casual_scout/web/templates/run.html`: run history and run details, including partial/failed states.
- `src/casual_scout/web/templates/game.html`: game detail and existing navigation back to source pages.
- `tests/test_web.py` and `tests/test_android_web_live.py`: extend existing route/render/progressive-Android regressions where suitable.
- `tests/test_ui_contract.py`: focused rendered-markup contract checks for all content pages, common navigation, semantic controls, and preserved links; create only if those assertions do not fit the existing web tests cleanly.

## Implementation tasks

### Task 1: Lock the page and route preservation contract

**Files:**
- Create or modify: `tests/test_ui_contract.py` (or extend `tests/test_web.py` if the same fixture can cover the assertions cleanly)
- Reference only: `src/casual_scout/web/app.py`, `src/casual_scout/web/android.py`, `src/casual_scout/web/templates/*.html`

**Interfaces:**
- Consumes: existing FastAPI `create_app` test fixture and route handlers.
- Produces: regression tests asserting every existing page route returns its expected page content and shared navigation links continue pointing to existing URLs.

- [ ] **Step 1: Inspect the test app fixture and route context.** Read `tests/conftest.py`, `tests/test_web.py`, and `tests/test_android_web_live.py`; record the fixture and test-client pattern used by the plan executor.
- [ ] **Step 2: Add failing page-preservation assertions.** Parameterize GET checks for `/dashboard`, `/data`, `/android`, `/shortlist`, `/runs`, a valid `/runs/{run_id}`, and a valid `/games/{country}/{app_id}` fixture. Assert successful rendering and page-specific heading/content, not fragile CSS classes.
- [ ] **Step 3: Add failing navigation destination assertions.** For each rendered page, assert shared navigation retains links to `/dashboard`, `/data`, `/android`, `/shortlist`, and `/runs`; assert the dashboard and data aliases still work (`/dashboard`, `/`, `/data`).
- [ ] **Step 4: Run the focused tests and confirm they pass against the current UI or fail only on deliberately new assertions.** Run `python -m pytest tests/test_ui_contract.py -q` (or the modified existing test file). Resolve fixture mistakes before changing production code.
- [ ] **Step 5: Keep this test-only checkpoint reviewable.** Review `git diff --check` and commit the regression tests separately if the project workflow uses commits during execution.

### Task 2: Establish shared Galaxy shell and responsive navigation

**Files:**
- Modify: `src/casual_scout/web/templates/base.html`
- Modify: `src/casual_scout/web/static/app.css`
- Test: route/navigation contract tests from Task 1

**Interfaces:**
- Consumes: current `active_tab` values `dashboard`, `data`, `android`, `shortlist`, `runs` supplied by existing handlers.
- Produces: shared navigation with labels “Tổng quan”, “iOS”, “Android”, “Shortlist”, “Lịch sử”, existing hrefs, visible active indication, and shared CSS tokens/primitives usable by every template.

- [ ] **Step 1: Add failing shell assertions.** Assert that every rendered page has exactly the existing five primary navigation destinations, that each link has readable text, and that the active destination has a non-color cue (for example, `aria-current="page"` or an equivalent semantic state).
- [ ] **Step 2: Run the focused test and verify the new semantic active-state assertion fails.** Run `python -m pytest tests/test_ui_contract.py -q`.
- [ ] **Step 3: Refactor `base.html` navigation without changing its URLs.** Use semantic `<header>`, `<nav aria-label="Điều hướng chính">`, and anchors whose labels are “Tổng quan”, “iOS”, “Android”, “Shortlist”, “Lịch sử”; mark the matching current link semantically from `active_tab`. Keep the iOS link title/subtext clear as “Dữ liệu iOS”. Keep all visible text on navigation links single-line at compact widths.
- [ ] **Step 4: Add the Galaxy tokens and shared shell styles.** In `app.css`, define a restrained set of CSS custom properties for background/surfaces/borders/text/indigo/violet/cyan and state colors; style the shell, active nav, focus-visible outlines, buttons, inputs, cards, tables, badges, and consistent spacing. Keep effects restrained and data contrast high; do not add starfield, nebula, external font, icon CDN, or package.
- [ ] **Step 5: Add responsive rules that do not wrap clickable nav labels.** At the compact breakpoint, keep all five destinations visible using a compact horizontally arranged or deliberately scrollable nav with clear focus/active state; prevent page-level horizontal overflow. Allow only wide data tables to have their own horizontal scroll container.
- [ ] **Step 6: Run the contract tests and inspect at 1280 px, 768 px, 414 px, and 320 px.** Check that labels remain one-line, the active state is discernible, keyboard focus is visible, and there is no page-level horizontal scroll. Adjust CSS only; do not hide destinations.

### Task 3: Standardize dashboard and iOS data workflows

**Files:**
- Modify: `src/casual_scout/web/templates/dashboard.html`
- Modify: `src/casual_scout/web/templates/data.html`
- Modify: `src/casual_scout/web/static/app.css`
- Test: `tests/test_web.py`, `tests/test_one_time_schedule.py`, `tests/test_web_stats.py`, and route contract tests as needed

**Interfaces:**
- Consumes: current dashboard/data view context and existing form/API URLs unchanged.
- Produces: compact dashboard toolbar and summary-first hierarchy; iOS toolbar and table-first hierarchy; unambiguous stored-date versus future-schedule labels.

- [ ] **Step 1: Add failing rendered-content regressions for dashboard and iOS page semantics.** Assert that dashboard date is described as analysis/data date; iOS snapshot selection uses stored-snapshot language; collection scheduling says “Lên lịch crawl” and “Thời điểm chạy”; existing export, crawl, and schedule form targets remain unchanged.
- [ ] **Step 2: Run focused tests to establish current behavior and identify exact legacy wording.** Run `python -m pytest tests/test_web.py tests/test_web_stats.py tests/test_one_time_schedule.py -q` and capture current form action/name expectations before template edits.
- [ ] **Step 3: Refactor dashboard visual hierarchy.** Group existing date/market filters in one toolbar; show collection status/action concisely; prioritize KPIs and opportunity/radar content; keep charts lower on page and keep current filter/export behaviors and data bindings intact.
- [ ] **Step 4: Refactor the iOS Data hierarchy.** Group market, Top Free/Top Grossing, and stored snapshot selectors; retain timestamp, quality, evidence, CSV, signal filters/counts, and the game table; group Crawl ngay and existing schedule controls without introducing duplicate actions.
- [ ] **Step 5: Clarify date/schedule copy without changing semantics.** Use “Ngày dữ liệu” / “Bản chụp đã lưu” for records already stored, and “Lên lịch crawl” / “Thời điểm chạy” for the future schedule. Make clear that the one-time schedule collects VN Top Free; do not imply a live historical Apple API call. Retain existing daily schedule behavior.
- [ ] **Step 6: Run the focused regressions.** Run `python -m pytest tests/test_web.py tests/test_web_stats.py tests/test_one_time_schedule.py tests/test_ui_contract.py -q`; verify route URLs, form names/actions, exports, and schedule persistence remain unchanged.
- [ ] **Step 7: Inspect dashboard and data pages in the browser at 1280 px and narrow widths.** Confirm no key failures or collection controls are hidden, the table remains the main content on `/data`, and any horizontal scrolling is confined to the table.

### Task 4: Apply shared visual language to Android without changing live batches

**Files:**
- Modify: `src/casual_scout/web/templates/android.html`
- Modify: `src/casual_scout/web/static/android.css`
- Modify: `src/casual_scout/web/static/app.css` only if a shared primitive is genuinely missing
- Tests: `tests/test_android_web_live.py`, `tests/test_android_batches.py`

**Interfaces:**
- Consumes: current Android run/status API, polling, batch rendering, and existing Android-specific styles.
- Produces: Galaxy-consistent Android status/progress/results presentation; no change to JavaScript polling or incremental batch contracts.

- [ ] **Step 1: Add or strengthen failing presentation contract assertions.** Verify the rendered Android page contains its primary crawl action, status/progress regions, chart/history selectors, and accessible labels for dynamically updated status where applicable.
- [ ] **Step 2: Run `python -m pytest tests/test_android_web_live.py tests/test_android_batches.py -q` and record the baseline.** Confirm the tests cover batch results appearing before crawl completion and avoid modifying any user changes unrelated to this spec.
- [ ] **Step 3: Update Android template classes and hierarchy.** Keep crawl action/status/progress at the top, batch results immediately below, chart/run selectors beside results, and concise but visible failure/retry/processed-count/batch/last-updated detail. Keep all IDs/data attributes consumed by `android.js` intact.
- [ ] **Step 4: Align `android.css` to shared tokens.** Remove conflicting colors/spacing in favor of shared CSS variables and reusable primitives; keep only Android-specific layout rules in this stylesheet.
- [ ] **Step 5: Run the focused Android regression tests and inspect an in-progress/partial state.** Confirm updates remain progressive without page reload, long labels fit, and error states remain visible.

### Task 5: Standardize Shortlist, run history, run details, and game details

**Files:**
- Modify: `src/casual_scout/web/templates/shortlist.html`
- Modify: `src/casual_scout/web/templates/runs.html`
- Modify: `src/casual_scout/web/templates/run.html`
- Modify: `src/casual_scout/web/templates/game.html`
- Modify: `src/casual_scout/web/static/app.css`
- Tests: `tests/test_web.py`, `tests/test_web_security.py`, `tests/test_shortlist_storage.py`, plus Task 1 route assertions

**Interfaces:**
- Consumes: current page view data, form endpoints, filters, edit/export links, detail links, status values, CSRF fields.
- Produces: consistent page headers/toolbars/tables/forms/statuses with every existing secondary action and route preserved.

- [ ] **Step 1: Add failing route/action-preservation assertions for the four page types.** Check shortlist edit/export controls and game links; run-history detail links; run-detail links/status rendering; game-detail return/navigation links. Assert current `href`, `action`, and CSRF inputs rather than CSS class names.
- [ ] **Step 2: Run focused tests before refactoring.** Run `python -m pytest tests/test_web.py tests/test_web_security.py tests/test_shortlist_storage.py -q` and note expected route/form behavior.
- [ ] **Step 3: Update shortlist page structure.** Use a shared title/description, compact filter toolbar, consistent table/status/actions; preserve edit/export/detail targets and security fields.
- [ ] **Step 4: Update runs and run-detail structure.** Keep run status, timestamps, partial/failure context, and detail navigation explicit; use consistent table density and badges without changing status interpretation.
- [ ] **Step 5: Update game-detail structure.** Use shared page heading, metadata/table primitives, and existing back/detail links; retain all game fields and evidence/download targets.
- [ ] **Step 6: Run focused regressions and verify every route.** Run `python -m pytest tests/test_web.py tests/test_web_security.py tests/test_shortlist_storage.py tests/test_ui_contract.py -q`; verify all route and CSRF/action assertions pass.

### Task 6: Cross-page accessibility, visual, and full regression verification

**Files:**
- Modify only defects found in: all seven page templates and `app.css` / `android.css`
- Tests: all relevant web tests and full test suite

**Interfaces:**
- Consumes: completed shared shell and page-level presentation from Tasks 2–5.
- Produces: verified existing page/routes parity, keyboard/accessibility basics, desktop-first layout, compact-width compatibility, and passing regressions.

- [ ] **Step 1: Render and inspect every content page.** Open `/dashboard`, `/data`, `/android`, `/shortlist`, `/runs`, a run detail, and a game detail at 1280 px; verify shared nav, active state, heading, no template errors, and expected page-specific controls.
- [ ] **Step 2: Check narrow widths at 768 px, 414 px, and 320 px.** Confirm nav labels do not wrap to two lines, every page remains reachable, controls wrap without overlap, tables scroll inside their container, and the document itself does not scroll horizontally.
- [ ] **Step 3: Check keyboard and semantics.** Tab through navigation/forms/actions; verify visible focus, actual buttons for actions, links for navigation, accessible names for icon-only controls, decorative SVGs hidden from assistive technology, and status updates announced without focus theft.
- [ ] **Step 4: Check the required state treatments.** Inspect empty, loading, running, partial, failed/interrupted, stale, mock, and validation/network-error examples where fixtures/data permit; ensure partial is never styled as complete and mock data remains clearly marked.
- [ ] **Step 5: Run all focused UI/workflow regressions.** Run `python -m pytest tests/test_ui_contract.py tests/test_web.py tests/test_web_security.py tests/test_web_stats.py tests/test_one_time_schedule.py tests/test_android_web_live.py tests/test_android_batches.py -q` (omit the new test path if assertions were placed in existing tests).
- [ ] **Step 6: Run the full suite and lint.** Run `python -m pytest -q` and `ruff check src/casual_scout/web tests`; resolve only regressions introduced by this redesign and document pre-existing failures distinctly.
- [ ] **Step 7: Review the final diff for scope control.** Confirm no route, provider, storage, scheduler, analysis, or Android batch behavior changed; run `git diff --check`; summarize tests and any visual checks not possible in the environment.

## Self-review

- **Spec coverage:** Shared Galaxy palette, shell, SVG handling, focus semantics, and responsive navigation are covered in Task 2; Dashboard and iOS semantics/hierarchy are covered in Task 3; incremental Android behavior in Task 4; Shortlist/history/run/game pages in Task 5; every state, viewport, route, interaction, and regression gate in Task 6.
- **Page preservation:** Task 1 locks routes and shared destinations before changes. All seven page templates are in scope, with `/` retained as the existing data-page alias. Detail pages remain reachable through existing parent-page links.
- **Scope boundary:** No backend/API/database/provider/scheduler logic is planned. The one-time schedule is preserved and its existing VN Top Free scope is made visible in UI copy.
- **Responsive audit finding:** Task 2 and Task 6 explicitly prohibit two-line clickable navigation labels and verify all destinations at 320/414/768 px as well as laptop width.
- **No placeholders:** Every task names files, test commands, expected behavior, and concrete implementation boundaries; no deferred TODO/TBD steps are included.
- **Type/interface consistency:** The page active-state identifiers and route map match current route handlers; Android dynamic element IDs/data attributes must remain unchanged because `android.js` consumes them.
