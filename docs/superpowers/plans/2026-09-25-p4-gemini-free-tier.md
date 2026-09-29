# P4 Gemini Free Tier Adapter Implementation Plan

**Current progress (2026-09-29):** Adapter, durable reservations, CLI startup configuration
and manual UI guardrails are connected. See [P4 offline acceptance](../reviews/p4-ui-verification.md).
Unchecked step recipes below preserve the original instructions; this summary tracks actual work.

- [x] Task 1: Atomic, restart-safe five-attempt daily reservation.
- [x] Task 2: Gemini adapter and explicit local configuration loading at CLI startup.
- [x] Task 3: Manual consent, unknown billing, limits, history and failure states.
- [ ] Task 3 live acceptance: Ten pilot outputs still require authorized calls and human review.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable manually confirmed Gemini pilot calls within the owner's approved Free Tier usage guardrail.

**Architecture:** Reuse P4 storage/engine/UI. A narrow HTTPX adapter reads a server-only key and calls one fixed Gemini model. Daily attempted calls are limited by atomic SQLite reservation, not process memory. No billing administration or automatic retry.

**Tech Stack:** Existing HTTPX, SQLite, FastAPI, pytest MockTransport; no Gemini SDK needed.

**Spec:** `docs/superpowers/reviews/p4-provider-decision.md`, owner approval in chat 2026-09-25, and the three P4 specifications.

## Global Constraints

- `gemini-2.5-flash`; one `generateContent` request, no fallback, no tools or grounding.
- At most 5 attempted calls per Asia/Ho_Chi_Minh calendar day, at most 2000 output tokens.
- Unknown actual cost stays null. Free Tier is owner-attested, not API-verified.
- Explicit manual confirmation before each call. No model calls at startup, GET, crawl or cron.
- Secrets stay in ignored `.env` or environment and never enter browser, database or errors.
- Existing positive monetary-cap policy applies outside explicit free_tier mode.

## Task 1: Atomic Free Tier reservations

**Files:** Modify `ai/storage.py`, `ai/settings.py`, `ai/service.py`; tests `test_ai_storage.py`, `test_ai_engine.py`.

**Interfaces:** Extend AISettings with `cost_mode: str = 'metered'`,
`free_tier_confirmed: bool = False`, `max_runs_per_day: int = 5`.
Frozen run policy includes mode, daily limit and local reservation day.

- [ ] Write failing tests: five sequential runnable attempts (including failures) exhaust day;
  sixth becomes blocked `daily_limit_reached`; restart/new store does not reset count;
  blocked runs do not count; replay same key does not reserve twice.
- [ ] Add count and insertion in the same `_write_connection()` transaction. Count rows
  with `status != 'blocked'` and matching reservation day across all free-tier models.
  When limit reached, insert a blocked row rather than dispatch. Recheck policy at run time.
- [ ] Test disabled/missing attestation and unconfirmed unknown cost cause zero network calls.
- [ ] Verify scoped pytest and lint. No production DB writes or commits.

## Task 2: Gemini adapter and local configuration

**Files:** Create `ai/gemini.py`, `tests/test_ai_gemini.py`; extend `ai/settings.py`,
web application wiring and README. Local `.env` edits must preserve existing key without printing it.

**Interfaces:** `GeminiProvider(api_key: str, *, timeout_seconds: int = 60,
transport: httpx.BaseTransport | None = None)` implements the P4 Provider protocol.
Fixed provider/model IDs; `estimate_cost` returns None (not an invoice).

- [ ] Write failing MockTransport tests for exact URL/header (dummy key), one request,
  timeout, 429, auth/server errors, invalid JSON, no candidate, truncation and valid output/usage.
- [ ] Implement POST to
  `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
  using `x-goog-api-key` header, redirects disabled and finite timeout.
  Send exact persisted system prompt and JSON evidence. Generation config uses JSON output
  schema, `candidateCount: 1`, `maxOutputTokens` from frozen input <=2000; no tool declarations.
- [ ] Extract non-thought text from the single candidate, require STOP finish, parse JSON.
  Preserve whitelisted integer token usage even for malformed/truncated output; no raw error
  envelope, output or exception is persisted on failure. Map 429 to ProviderQuota, timeout
  to ProviderTimeout and other failures to fixed safe errors. No retry.
- [ ] Add explicit local config loading only for server startup. Environment overrides `.env`.
  Missing/invalid config disables calls safely. Do not overwrite os.environ or load secrets
  into generic Settings repr. Tests injecting fake provider/settings bypass local config.
- [ ] Verify tests with no real key. README documents 5/day local calendar, restart-safe limit,
  unknown billing limitation, public-data transmission and pilot quality warning.

## Task 3: UI guardrails and acceptance record

**Files:** Extend recommendations router/templates/JS and tests; provider decision report.

- [ ] Show Free Tier (owner-confirmed), attempts remaining, model, 2000-token limit and
  actual-cost unknown. Require explicit confirmation. Never show guaranteed-zero billing.
- [ ] Test sixth call blocked, double click replay, cancelled dialog no attempt, and no
  secret in HTML/status/history. Show quota failure as terminal with manual new-run flow.
- [ ] Run full offline regression. Live pilot only within approved bounded calls; each
  report distinguishes schema success from human-reviewed quality. Ten-case acceptance
  cannot be claimed from one smoke call. Preserve data and all prior routes.

## Review

Uses existing Provider/store interfaces and no new infrastructure. Covers current owner
approval without inventing a paid budget. Application cannot prevent billing if account
settings are changed externally; user confirmation and clear UI make this boundary explicit.
