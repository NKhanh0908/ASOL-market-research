# P4.1 storage verification — 2026-09-25

Implemented inline, preserving the existing dirty worktree. No commit/push, production
database initialization, model generation request, or local API-key change was performed.

## Delivered

- Packaged additive SQLite schema and frozen request/reply/evidence contracts.
- Evaluation lifecycle, idempotent request replay, one active run and immutable history.
- Evidence insertion seal committed atomically with creation, including blocked records.
- Canonical JSON/input hashes and nullable usage/cost with explicit USD provenance.
- Recursive sensitive-key and raw-provider-envelope rejection; safe fixed failure messages.
- Owner-approved Free Tier reservation: at most five attempted runs per Vietnam-local day,
  counted durably and atomically. This storage policy is not yet connected to a provider/UI.
- Backup/restore regressions preserve full run data, source references and raw hashes.

## Verification

- Full pytest on final files: **222 passed, 2 existing dependency deprecation warnings**, 27.87 seconds.
  Command: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .venv/pytest-p41-delivery-final`.
- Backup suite after fixture cleanup: **7 passed**, 0.97 seconds.
- Scoped Ruff for all AI files/tests: **All checks passed**. Tracked task diff check passed.
- Storage review fix suite: **31 passed**, 1.68 seconds.
- Independent schema, lifecycle and whole-P4.1 reviews found no remaining functional blockers.
- The reviewers identified cost-provenance inference and raw-envelope persistence; both
  were fixed and re-reviewed. Final fixture lint cleanup passed focused and full regression.

## Decisions and limits

- Work stayed inline with no worktree or commit, as requested; changes remain uncommitted.
- Owner selected Gemini Free Tier and approved 5 attempts/day, 2,000 output tokens, manual
  confirmation, no retries/fallback. The future explicit free_tier engine mode replaces the
  old positive monetary-cap prerequisite only in that mode. External billing changes cannot
  be enforced by application counters; actual unreported cost remains unknown.
- Engine, Gemini adapter/local configuration, recommendation UI and live quality pilots
  are **not implemented** in this P4.1 delivery. Their separate plans remain pending.
- No browser UI acceptance is claimed. Browser inventory currently exposes no enabled surface.
- Scratch ledgers are retained because work is uncommitted; they are not the only code copy.

Next independently reviewable plan: `docs/superpowers/plans/2026-09-25-p4-recommendation-engine.md`,
with the approved Free Tier supplement in `2026-09-25-p4-gemini-free-tier.md`.
