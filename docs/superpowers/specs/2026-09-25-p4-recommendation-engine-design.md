# Phase 4.2 — Evidence-Based Recommendation Engine MVP

**Date:** 2026-09-25
**Status:** Design approved in chat; awaiting written-spec review.
**Parent requirement:** [Casual Game Market Research PRD](../../prd/2026-09-10-casual-game-market-research-PRD.md), P4, BA-R10–12, DEC-08.
**Prerequisite:** [P4 AI Evaluation Storage Contract](2026-09-25-p4-ai-storage-contract-design.md).
**Consumer:** [P4 Review UI](2026-09-25-p4-review-ui-design.md).

## 1. Purpose and boundary

When explicitly requested, generate up to three evidence-based casual-game opportunity recommendations from existing P2/P3 data. The engine must explain why each suggestion is worth investigating and provide bounded, assumption-labelled delivery estimates. This MVP does not add data collection sources, revenue estimates, free-form chat, user/team profiles, model training, automated daily AI runs, or autonomous development actions.

The current PRD defines the outcome but not the feasibility rubric, provider, or budget. This spec narrows the behavior without asserting that an AI-generated staffing estimate is measured fact.

## 2. Trigger and input contract

- Only a user action starts an evaluation; never run after every crawl or on a timer.
- Input scope inherits the Dashboard's selected analysis date and market selection. Persist the exact values used.
- Build a bounded context from P2/P3 analytics and their canonical snapshot references. Prefer existing explainable signals (rank movement, breadth across selected markets, taxonomy/mechanic evidence) over raw full-database dumps.
- If the selected date/markets have no usable P2/P3 candidates or evidence links, create a `blocked` evaluation with a specific explanation and do not call the provider.
- Limit the result to at most three recommendations. Return fewer when evidence does not support three; an empty recommendation result is valid if none meet the evidence floor.

## 3. Recommendation output contract

Each recommendation contains:

- a proposed casual-game opportunity/concept and subgenre/mechanic pattern (not an instruction to clone a named competitor);
- a short “why now” rationale linked to supplied market observations and evidence IDs;
- the data scope (markets/platforms/date window) and metric type for each factual observation;
- clearly separated observations, inferences, and unknowns;
- a scoped delivery assumption (e.g. prototype or MVP) selected and explained by the model;
- estimated role mix, approximate team-size range, and timeline range under that scope;
- qualitative feasibility (`high`, `medium`, `low`, or `insufficient evidence`) with a rubric-based explanation, key risks, and validation questions.

Do not emit a numeric 1–10 feasibility score in the MVP. Do not infer downloads, revenue, retention, CPI, ad/IAP mix, or causal reasons from rank alone. If evidence is absent, say unknown or lower the feasibility classification; do not fabricate citations. The model may not cite evidence IDs that were not in the input manifest.

## 4. Provider, cost, and failure behavior

- Use one explicitly configured provider/model per run behind a narrow provider adapter. Provider selection is a prerequisite decision, not part of this spec.
- Never fall back automatically to a paid provider or different model.
- Before the call, estimate cost when the provider exposes enough information; display the configured limit and the selected date/market scope. If cost is unknown, require an explicit confirmation that it is unknown. If the configured guardrail is absent or exhausted, block the call.
- Persist provider/model, prompt/output versions, reported usage, known cost/currency/method, and the complete canonical input/output using the storage contract.
- Validate JSON/schema, recommendation count, required assumptions/evidence references, and forbidden unsupported metric claims before marking the run succeeded.
- Do not auto-retry an error with an unknown billing outcome. Record provider/configuration/timeout/schema errors; the user can explicitly start a new run.
- Failure of this engine leaves Dashboard P3 and existing collection data usable.

## 5. Acceptance checks

1. A user action creates a stored evaluation for the selected date/markets; background collection does not create an AI run.
2. Missing provider configuration or insufficient evidence blocks before any external model request.
3. The engine returns no more than three recommendations and may return fewer without filling space with weak or invented ideas.
4. Every factual market claim resolves to supplied evidence; unsupported downloads/revenue/retention/CPI claims are absent.
5. Resource/time estimates identify scope, assumptions, ranges, and risks; they are labelled estimates, not actual project measurements.
6. Provider cost/usage unknown remains unknown; no automatic paid fallback or automatic retry occurs.
7. Malformed/unsupported output becomes a failed run with a recoverable explanation and does not damage P2/P3 data.

These are design acceptance checks; no provider/model evaluation or implementation tests have been performed yet.

## 6. Open decisions and required pre-implementation check

- Choose one provider/model only after testing a small representative P3 evidence pack for Vietnamese/English output quality, structured-output validity, usage reporting, and per-run cost. Do not treat a free trial as a continuing free tier.
- Define the explicit cost cap and unknown-cost confirmation policy before enabling calls. The owner is the product owner; resolution evidence is a recorded provider comparison and chosen budget.
- The `high/medium/low` feasibility rubric must be operationalized in the implementation plan using evidence strength, market breadth/momentum, differentiation hypothesis, and delivery risk. Do not convert this into a numeric score without separate approval.
