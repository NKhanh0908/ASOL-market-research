# P4 provider decision — 2026-09-25

**Integration update (2026-09-29):** CLI configuration loading, worker dispatch and manual
Dashboard/history/detail UI are connected and tested offline. See [current verification](p4-ui-verification.md).
No live call was made in this delivery. The ten-case acceptance table below remains Pending.

The owner selected Gemini by supplying a replacement key in ignored local `.env`, then
explicitly confirmed the account is Free Tier and authorized continued implementation.
The key is never included in source, reports, prompts or database history.

## Selected integration

- Provider: Gemini Developer API, Standard generateContent, `gemini-2.5-flash`.
- Account evidence: authenticated models.list returned HTTP 200 and includes this model.
- Free-tier status: owner attestation; models.list does not verify billing/quota.
- No billing activation, model/provider fallback, grounding/search, caching purchase or retry.
- Output bound: 2,000 tokens initially, finite 60-second request timeout, one active run.
- Actual cost: unknown unless explicitly reported; never manufacture a zero actual charge.
- Owner approved Free Tier guardrail in chat: maximum 5 attempted calls per local Vietnam
  calendar day, 2,000 output tokens per call, explicit manual confirmation, no automatic
  retry/fallback. This supersedes the plan's positive monetary-cap requirement only in
  explicitly selected `free_tier` mode; no positive spend allowance is approved.
- Daily attempts are reserved atomically when a runnable record is created; queued/failed
  attempts consume allowance conservatively. Blocked records do not. Restart does not reset
  allowance. The app cannot guarantee billing tier; every preflight states that limitation.
- Implement the adapter for manual testing after offline checks. Live quality acceptance
  stays unverified until ten cases are reviewed; display a pilot/review warning.
- Ten-case quality acceptance remains outstanding. Fake tests do not satisfy live acceptance.

## Official sources checked

Checked 2026-09-25:

- [Pricing](https://ai.google.dev/gemini-api/docs/pricing): 2.5 Flash Standard lists free
  input/output on Free Tier. Free-tier content can be used to improve Google products.
- [Structured output](https://ai.google.dev/gemini-api/docs/structured-output): JSON output
  still requires application validation; it does not establish factual accuracy.
- [Generate content](https://ai.google.dev/api/generate-content): generation response includes
  usage metadata; it is not a billing receipt.

Only public store evidence selected by date/market is eligible for a future model call.
Do not send private shortlist notes, filesystem paths, raw credentials or full database dumps.

## Offline pilot and live acceptance gate

`tests/fixtures/ai/pilot-cases.json` holds ten compact, explicitly synthetic review
scenarios. Its observation and candidate fields follow the P4 evidence builder's test
shapes. Snapshot IDs and raw hashes are placeholders; the fixture is for offline contract
and review preparation, not a verified source corpus or an instruction to run a model.
`tests/test_ai_pilot.py` checks scenario coverage, structure, selected-market boundaries,
and closure of candidate and derived evidence IDs.

| Case | Live run | Vietnamese clarity | Schema | Factual citations | Inferences and estimates separated | Elapsed time | Reported tokens | Actual cost / unknown | Human review |
|---|---|---|---|---|---|---|---|---|---|
| empty_scope | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| vn_no_baseline | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| vn_1d_rise | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| multi_market_rise | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| newly_crawled_market | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| partial_source | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| unknown_mechanic | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| conflicting_mechanics | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| adversarial_description | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| no_credible_recommendation | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |

BA-R10 remains unmet: all ten outputs need bounded, authorized live runs and human
quality review. A schema-valid or fake-provider result cannot close this gate. A failed
case keeps live rollout blocked until reviewed and resolved. Record token usage exactly
as reported, and leave actual cost unknown unless the provider reports a billable amount.
