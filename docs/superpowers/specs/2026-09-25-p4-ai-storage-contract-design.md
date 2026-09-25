# Phase 4.1 — AI Evaluation Storage Contract

**Date:** 2026-09-25
**Status:** Design approved in chat; awaiting written-spec review.
**Parent requirement:** [Casual Game Market Research PRD](../../prd/2026-09-10-casual-game-market-research-PRD.md), P4, BA-R10–12, DEC-08.
**Related specs:** [P4 Recommendation Engine](2026-09-25-p4-recommendation-engine-design.md), [P4 Review UI](2026-09-25-p4-review-ui-design.md).

## 1. Purpose and boundary

Define the smallest persistent contract needed to run and review Phase 4 AI evaluations using the existing local SQLite database. This spec does not select an AI provider, define prompt content, implement recommendation logic, add a queue service, or change collection/P2/P3 tables.

Existing evidence is held in `daily_rank_analytics` and `daily_canonical_snapshots`; source snapshots are immutable and link to raw responses. `daily_rank_analytics` rows can be recalculated/upserted. Therefore, a reference to a P3 row alone is insufficient to reproduce what an AI run saw.

## 2. Design

Add an isolated AI evaluation persistence area to the existing `casual-scout.sqlite3` database. Do not overload the collector `runs` table.

### `ai_evaluation_runs`

One immutable record per explicit evaluation request. Store at minimum:

- run ID and status (`queued`, `running`, `succeeded`, `partial`, `failed`, `blocked`);
- selected analysis date, selected market codes, and created/started/ended UTC timestamps;
- provider and model IDs as actually used, prompt version/hash, and output schema version;
- exact canonical evidence payload supplied to the model, with evidence references;
- structured result payload when available;
- provider-reported usage and cost metadata when available; cost amount/currency/method may be unknown and must be nullable/explicitly unknown, never silently zero;
- stable error category and concise safe-to-display error text for failures.

The payload records only model-visible product/evidence data, not credentials, authorization headers, or provider secrets. Preserve a versioned JSON result for the complete response; fields needed for filtering/history may be stored as small relational columns in later implementation only where a concrete UI query requires them.

### `ai_run_evidence`

Link each run to the source evidence it used: analytics row ID when present, date, market, app ID, and canonical snapshot ID when available. The serialized canonical input payload preserves the exact values sent even if P3 analytics are recalculated later. Do not duplicate raw response files or binary assets.

## 3. Transaction and lifecycle rules

- Persist a run before invoking an external provider so crashes leave an inspectable state.
- Never hold a SQLite write transaction open during network/model calls. Use short transactions for state transitions and result persistence.
- Terminal runs are immutable; a manual rerun creates a new run linked to the same or new evidence, never overwrites prior results.
- A provider timeout with unknown billing outcome is recorded as an uncertain failure; do not retry automatically. A user-triggered retry is a new run.
- Do not automatically expire evaluation history or evidence. Retention remains an operational decision.
- Existing SQLite online backup already backs up database tables. No new external storage is introduced; restore tests must include P4 rows and evidence references.

## 4. Migration and constraints

- Add tables/indexes through a non-destructive, idempotent schema migration. Existing collection, Android, and P2/P3 rows remain unchanged.
- Keep SQLite local to the application process; avoid adding concurrent writers. Any model/network call occurs outside DB transactions.
- Do not add PostgreSQL, vector search, blob storage, a message broker, or a generalized ORM/migration framework as part of this contract.
- Provider pricing is not known yet. The consuming pipeline must not make cost guarantees from absent usage/pricing; it must show unknown as unknown and obey the configured preflight/confirmation policy in the engine/UI specs.

## 5. Acceptance checks

1. Initializing an existing populated database adds P4 tables without losing or rewriting existing data; initializing again is safe.
2. A queued/running/terminal run can be persisted and read with its selected date, markets, prompt/output versions, evidence refs, result, usage/cost, and error state.
3. Stored canonical input reproduces the exact model-visible evidence even after P3 analytics for that date are recalculated.
4. Secrets are not present in persisted request/evidence/result/error records.
5. A failure after run creation remains visible and does not block unrelated collection or P2/P3 reads.
6. Backup and restore preserve P4 evaluation rows, linked evidence, and JSON payloads.

These are design acceptance checks; no implementation tests have been run for this spec.

## 6. Open decisions

- AI provider/model and its cost/usage reporting must be selected after a small cost/quality feasibility check; this spec intentionally does not choose one.
- A concrete per-run or monthly spending cap is not yet known. Enablement must remain gated on an explicitly configured limit/confirmation policy; do not infer a zero-cost allowance.
