# Android HTTP implementation and acceptance — 2026-09-29

Baseline: `df63544`. Working branch: `feat/android-http-plan-completion`.
This report separates delivered behavior from the original specs' release gates.

## Delivered behavior

- HTTP POST chart RPC and GET detail pages; shared limit of ten requests, 15-second timeout, bounded retries. No Selenium import remains in application source.
- Nine markets, both feeds, validated package identity and installs. Short charts remain `partial`; malformed chart rows are rejected rather than renumbered.
- Core SQLite snapshots, raw HTTP attempts, incremental metadata bindings, per-country complete metadata cache under 48 hours, interruption cleanup and heartbeat.
- Separate feed canonicals, free/grossing union including grossing-only apps, same-feed deltas, partial baseline safeguards, Android monetization and platform isolation.
- CLI platform flags and sequential iOS/Android collection; shared worker dispatch, secured/idempotent crawl API, atomic Android schedules and dead-worker recovery.
- Platform data/dashboard, radar v1.5, installs badges, package detail, 14-day dual history, scoped snapshot navigation and CSV exports. Historical metadata and analysis stay anchored to observations.
- Legacy Android pages remain available by job ID; new crawl and schedule entry points use the HTTP core. Shortlist and AI remain iOS-only.

## Verification

Commands use the local `.venv\Scripts\python.exe`.

| Check | Result |
|---|---|
| `-m pytest -q --tb=short` | 507 passed, 3 dependency deprecation warnings |
| Google mock tests under coverage | 61 passed |
| Google provider/transport/parser statement and branch coverage | 100% each; 293 statements, 112 branches |
| Real SQLite API → collection → analysis → data/radar/game offline acceptance | Passed; synthetic fixture provider, not live source acceptance |
| Second offline run | Fresh chart snapshots, zero additional detail requests |
| Mixed-platform backup and immutable evidence checks | Passed; iOS rows and raw hashes preserved |
| Independent code review | Important findings fixed and covered by regression tests |
| Browser visual QA at 390/1440px | Not performed: computer-use inventory had no browser; in-app browser unavailable |

Default AI web wiring was missing in the baseline and caused existing tests to fail.
It was restored with explicit signed preflight/confirmation, no calls on GET and no
Android AI expansion. Tests use a fake provider; no Gemini request was made.

## Live acceptance remains open

See [benchmark JSON](2026-09-29-google-play-http-benchmark.json). The benchmark uses
an independent temporary database and immediately repeats it as a warm run.
Raw evidence paths and logs remain in those temporary directories; no production DB
was crawled or migrated by acceptance checks.

First measured pair: cold 384.81s / warm 106.82s; eighteen charts in each run, zero
browser processes, zero missing display/numeric installs. Source Grossing charts
returned fewer than 100 in several markets. Two completed measurements are recorded
in the JSON. The additional pairs were stopped after the user accepted these operational
limits; the original six-run release gate remains unfulfilled.

These results do **not** meet the original full Top100 and <60-second gates.
The implementation uses POST chart RPC already present in the baseline, whereas
SPEC-AND-01 originally required public GET. The original spec has not been silently
rewritten. Short responses do not prove that all available games have been returned.
Release acceptance remains open for a source/spec decision, performance target and
browser visual QA. Passing offline tests is not a claim that all three specs are fully met.

The user accepted the current partial-source and measured timing behavior on 2026-09-29.
This allows delivery of this implementation; it does not establish that unmeasured strict
release criteria have passed. Changed Python files pass Ruff; `git diff --check` passes.

## Plan tracking

The three plans contain an execution status section linking this evidence. Existing
RED/commit recipes are retained as planned instructions; they are not retroactively
claimed as individual historical executions. Changes are consolidated on the working
branch. Storage/analysis implementation is verified; HTTP and web release gates remain open.
