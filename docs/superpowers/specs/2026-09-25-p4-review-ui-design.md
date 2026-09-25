# Phase 4.3 — AI Recommendation Review UI MVP

**Date:** 2026-09-25
**Status:** Design approved in chat; awaiting written-spec review.
**Parent requirement:** [Casual Game Market Research PRD](../../prd/2026-09-10-casual-game-market-research-PRD.md), P4, BA-R10–12, DEC-08.
**Prerequisites:** [P4 AI Evaluation Storage Contract](2026-09-25-p4-ai-storage-contract-design.md), [P4 Recommendation Engine](2026-09-25-p4-recommendation-engine-design.md).
**Related visual direction:** [Galaxy UI/UX Redesign](2026-09-24-galaxy-ui-ux-redesign-design.md).

## 1. Purpose and boundary

Provide a compact laptop-first way to explicitly request, inspect, and revisit P4 recommendations. Reuse the application shell and approved restrained Galaxy visual direction where available. This spec does not redesign P1–P3 pages, add chat, free-form prompt editing, numeric ratings, training feedback, or mobile-specific interaction design.

## 2. Entry point and flow

1. On Dashboard, show **Tạo gợi ý AI** beside the selected analysis date/market scope.
2. Before an external call, show the exact scope, configured provider/model, configured cost limit, and estimated cost when known. If cost is unknown, explicitly say so and require an additional user confirmation. Disable submission if provider/guardrail is missing, exhausted, or the evidence preflight blocks.
3. After confirmation, create a run and show a stable link to its status/detail view. The user can continue using P3 while it runs.
4. A dedicated recommendations view shows the latest run and run history; opening an older run shows the immutable result and the scope used at the time, not a regenerated result.

The exact URL and placement of the history view can be chosen during implementation as long as there is a stable route, the current dashboard context is passed correctly, and existing navigation is not disrupted.

## 3. Result presentation

Present at most three recommendation cards. Each card shows, in scan order:

1. opportunity/concept, subgenre/mechanic, and qualitative feasibility label;
2. concise “why now” evidence with date, market/platform, source metric type, and links to available source detail;
3. clearly labelled assumptions and estimate ranges for scope, roles/team size, and timeline;
4. key risks, unknowns, and validation questions.

Use separate visual treatments for observed data, model inference, and estimate. Do not display AI-produced downloads/revenue as facts, and do not hide a missing-evidence warning behind a tooltip.

## 4. Required states and recovery

- **Not configured / cost guardrail missing:** explain what must be configured; no call is sent.
- **Insufficient evidence:** explain the missing P2/P3 coverage; do not bill the provider.
- **Awaiting confirmation:** show market/date scope and cost-known vs. cost-unknown state.
- **Running:** display persisted run status; allow navigation away and return by run ID.
- **Succeeded/partial:** show recommendations and linked evidence; mark partial coverage visibly.
- **Failed/uncertain billing:** show safe error text and distinguish definite failure from unknown provider outcome; do not offer silent automatic retry. A new explicit run is a new billable attempt.
- **No qualifying suggestions:** state that evidence did not support a recommendation; do not manufacture three cards.
- **History empty:** explain how to create the first run.

P3 charts/tables remain available and unchanged in every P4 state.

## 5. Accessibility and visual constraints

- Laptop-first layout matching the shared Galaxy tokens: dark navy surface, restrained indigo/violet/cyan accent, high-contrast text, no decorative starfield behind evidence.
- Buttons and links have text labels; icons are local inline SVGs and decorative when paired with labels. Keyboard focus remains visible.
- Status changes are announced through semantic status/alert regions. Do not use color as the only distinction among feasibility, evidence, or run states.
- Baseline responsive behavior is retained; this is not the separate phone-first design.

## 6. Acceptance checks

1. The Dashboard action carries the selected date/market scope and never runs automatically.
2. Missing configuration, insufficient evidence, and blocked budget states cause no model call.
3. User can distinguish cost estimate, known actual usage/cost, and unknown values before/after the run.
4. Result cards expose evidence, assumptions, estimate ranges, risks, and unknowns without implying estimates are measured facts.
5. Prior run detail remains stable and is clearly tied to its original scope; failure does not impair P3.
6. Keyboard-only use can start a run, confirm cost, navigate status/history, and open evidence links; state updates have accessible labels.
7. Existing shared UI and Android live batch behavior are not regressed.

These are design acceptance checks; no implementation or browser accessibility tests have been run.
