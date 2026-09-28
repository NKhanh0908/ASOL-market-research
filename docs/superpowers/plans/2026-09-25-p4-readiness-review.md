# P4 — Data Readiness Review and Execution Order

Reviewed on 2026-09-25. Documentation only; no P4 code, migration, crawl, provider call,
configuration change, cleanup, or commit was performed during this review.

## Read-only evidence

Database: `data/casual-scout.sqlite3`, 8,871,936 bytes at review time. Opened with
SQLite URI `mode=ro` and `PRAGMA query_only=ON`. Production data was not initialized
through `Repository.initialize()` or the web application.

| Check | Observed result |
|---|---|
| SQLite quick_check / foreign_key_check | `ok` / no violations |
| P4 tables | None |
| Source snapshots | 10 complete Top Free; 1 invalid VN Top Grossing |
| Snapshot entries | 1,100; not 1,100 unique games |
| Canonical snapshots | 6; all complete Top Free with 100 entries each |
| Daily analytics | 600 rows, 6 date/market groups |
| Metadata versions | 521 complete; all have non-empty descriptions |
| Raw evidence | 40 referenced files; 0 missing; 0 SHA-256 mismatches |
| Raw recorded size | 9,427,177 bytes |
| Shortlist | Empty |
| Mock marker in primary data directory | Absent; this is not independent proof of source authenticity |

| Analysis day UTC | Markets | Rows | Rows with 1D / 3D delta |
|---|---|---:|---:|
| 2026-09-10 | VN, SG, US | 300 | 0 / 0 |
| 2026-09-22 | VN | 100 | 0 / 0 |
| 2026-09-24 | VN | 100 | 0 / 0 |
| 2026-09-25 | VN | 100 | 94 / 89 |

Latest VN observation: `2026-09-25T01:36:20.202958Z`. SG/US complete observations are
only on 2026-09-10. There is no recent comparable ASEAN+US sequence in this database.
Current-day multi-market claims must therefore be unavailable, not extrapolated from old SG/US data.

All 600 analytics rows say `PURE_ADS`; this is the legacy inference/default, not verified
advertising evidence. On the latest day, 55/100 mechanics are `Other`. Metadata availability
does not mean taxonomy confidence or monetization knowledge is complete.

Android has three succeeded jobs (two on 24/9 and one on 25/9); its stored entries include
81 rows classified `casual`, 164 older rows with null casual classification (82 complete,
82 cached). These are job-entry counts, not unique games. Android evidence is not yet in
the iOS analytics/canonical contract; P4 MVP excludes it explicitly.

## Decisions reflected in these plans

- Use `stats/noteworthy.py` and complete same-day observations, not retired opportunity scores.
- Restrict P4 evidence to the markets the user selected. The ordinary dashboard's global
  cross-market annotations are not permission to silently include other markets in AI input.
- Preserve exact model-visible input and reference IDs before the provider call; analytics
  can be recalculated and cannot be the only reproducibility mechanism.
- Treat downloads, revenue amount, ad/IAP mix, retention and CPI as unknown in the MVP.
  Do not pass the legacy `PURE_ADS` field as measured evidence.
- Do not use the current dashboard 7-day aggregate as evidence: its query currently uses
  a row limit rather than an exact seven-day window. Build P4's bounded date window directly.
- Keep the user-approved charcoal/iris/jade/amber palette. The older P4 UI spec's dark-navy
  wording is superseded by the later explicit palette approval; preserve the five-tab shell.
- Existing specs say provider/model and budget are not selected. These plans deliver a
  provider-neutral, offline-testable pipeline and review UI. Live adapter implementation and
  live acceptance stay behind the decision gate below; no provider is selected by implication.

## Three independently reviewable implementation plans

1. [P4.1 Storage](2026-09-25-p4-ai-storage.md): additive SQLite contract, immutable history,
   short transactions, migrations and backup/restore. Can start without an AI provider.
2. [P4.2 Engine](2026-09-25-p4-recommendation-engine.md): bounded evidence, qualitative
   rubric, strict output, preflight/cost policy and single-call orchestration using injected
   fake adapters. Depends on P4.1; no live provider until the gate is resolved.
3. [P4.3 Review UI](2026-09-25-p4-review-ui.md): manual Dashboard action, confirmation,
   persisted history, result/evidence review and accessible states. Depends on P4.1/4.2.

Every plan has its own file map, interfaces, test/code steps and acceptance checks.
Do not execute all three as one unreviewed change. Stage only task-owned changes: the
worktree already contains unrelated uncommitted Android, UI and noteworthy work.
The user's prior inline/no-worktree preference remains in force unless changed.

## Live enablement gate (not a blocker for writing plans or offline implementation)

The product owner must choose a provider/model and cost policy after a small feasibility
study, preferring free sources as previously requested. Record the decision in
`docs/superpowers/reviews/p4-provider-decision.md` during that separate decision step:

```json
{
  "status": "not_selected",
  "provider_id": null,
  "model_id": null,
  "endpoint_documentation": null,
  "pricing_checked_at": null,
  "continuing_free_allowance": null,
  "max_cost_per_run_usd": null,
  "max_output_tokens": null,
  "unknown_cost_policy": "require_explicit_confirmation",
  "live_calls_enabled": false
}
```

The record above is an explicit disabled configuration, not invented pricing. Once chosen,
verify the provider's current official API/pricing, write a provider-specific adapter plan
against the P4.2 `Provider` protocol, and test a representative evidence pack for Vietnamese
output, schema validity, source fidelity and usage reporting. Do not promise cost is zero
because a trial, quota, local model, or absent usage field exists. No network pilot is
authorized by this documentation-only review.

The previous discussion about changing iOS Crawl ngay to all configured ASEAN+US markets
has not resolved whether daily/one-time schedules should change too. P4 plans do not change
those buttons/schedules. Wider collection improves input coverage but is not a prerequisite
for storage or a VN-scoped pilot.

## Initial free-source documentation survey

User explicitly confirmed free-source research first, with no provider selection. Official
documentation checked during this review; account-specific quota and real output quality
have not been tested. No signup, API key use, billable request or model installation occurred.

| Candidate | Evidence from official documentation | Pilot must establish |
|---|---|---|
| Gemini Developer API | A free tier exists for selected models; the pricing page distinguishes free/paid data-use policies. [Pricing](https://ai.google.dev/gemini-api/docs/pricing). Structured JSON output is documented. [Structured output](https://ai.google.dev/gemini-api/docs/structured-output) | Account/model eligibility, actual quota, Vietnamese recommendations, schema subset, usage reporting, acceptable data-use policy |
| Groq | Free-plan rate limits are documented. [Rate limits](https://console.groq.com/docs/rate-limits). Structured-output support depends on the model/mode; JSON mode is not a schema guarantee. [Structured outputs](https://console.groq.com/docs/structured-outputs) | Eligible model, usable input/output token limits for our 30 KB pack, Vietnamese quality, strict schema support, actual account restrictions |

These are candidates for comparison, not a recommendation to enable both. Do not hard-code
model names or published quota numbers before the pilot; free availability and model support
can change. Neither service's advertised free tier establishes zero total cost for this project.

## Self-review

Mapped all three P4 specs to separate plans. Reconciled retired scores, observed presence,
unreliable monetization defaults, partial coverage, UTC date semantics and latest palette.
Provider and budget are explicit external enablement gates, not hidden implementation assumptions.
The review validates database integrity and referenced raw hashes, not commercial usefulness
of recommendations or browser layout. No P4 implementation tests have been run yet.
