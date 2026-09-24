# Android Live Batches Implementation Plan

> Execute inline against the approved live-batch requirement; request independent
> code review before completion. Preserve existing uncommitted user changes.

**Goal:** Android chart collection with progressive, durable batch analysis on web.
**Architecture:** Additive Android SQLite store, shared collector lock, Selenium
worker process, existing scheduler extended by coordinator, 2s polling cards.
**Tech Stack:** Python, SQLite, FastAPI/Jinja, Selenium, pytest.
**Spec:** docs/superpowers/specs/2026-09-24-android-live-batches-design.md

## Global constraints

VN / GAME_CASUAL / Top Free + Top Grossing; batch size 5; no revenue amounts;
48h metadata cache; 15m run budget; Android daily disabled initially.

### 1. Durable storage and live analysis
- [x] Create android/storage.py and schema.sql: enqueue, atomic dispatch, chart
  persistence, per-batch updates, exact previous-day rank lookup, API view.
- [x] Tests: duplicate request, repeated manual runs, active iOS prevents dispatch,
  partial chart visibility, committed batch visibility, restart/read-only history.
- [x] Run focused pytest and inspect actual failure before implementation.

### 2. Browser provider and worker
- [x] Create android/provider.py using validated probe selectors and numeric ranks.
  Reject empty ranks and stale chart tab; preserve HTML/PNG for each chart.
- [x] Create android/worker.py: shared lock, each chart committed, metadata batches,
  cache reuse, per-app errors, final partial/failed/succeeded, browser cleanup.
- [x] Integration test using only a fake external provider: stop inside the second
  batch and observe first batch through the real DB; then fail one metadata item.

### 3. Coordinator and API
- [x] Create android/coordinator.py: persistent queue, internal launch, recovery,
  daily 07:00 after iOS check, no missed-slot backfill.
- [x] Create web/android.py, include router in create_app; API CSRF and run IDs.
- [x] Tests for state validation, multiple manual runs/day, queue serialization,
  recovery, existing one-time iOS schedule regressions.

### 4. Responsive progressive UI
- [x] Create templates/android.html and static/android.js / android.css.
- [x] Links from /data, dashboard and navigation. Poll at 2s, persistent run
  selection, display batch progress and data without reload, safe text rendering.
- [x] Run full regression, independent code review, actual headless collection;
  measure first chart / first batch / final timings and inspect mobile layout.
- [x] Record findings and limitations in docs/operations; launch page for user.

Verified: 161 tests passed; scoped Ruff clean; two live headless runs succeeded.
See docs/operations/2026-09-24-android-live-batches-acceptance.md for measurements.
