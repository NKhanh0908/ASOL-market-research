# P4 offline review workflow — 2026-09-29

Baseline: `8d57309`; delivery branch: `feat/p4-review-completion`.
This report covers the connected P4 offline implementation, not live model quality acceptance.

## Delivered behavior

- CLI `serve` explicitly loads server-only AI settings/provider. Direct `create_app` stays
  disabled by default; test-injected providers bypass local configuration.
- The web lifespan recovers orphaned evaluations and closes its single worker at shutdown.
  Confirmed POST returns 202 without waiting for model completion; persisted status remains readable.
- Session-bound, five-minute signed preflight freezes selected iOS date/markets, evidence,
  provider/model and policy. CSRF/origin checks remain required. Replaying a request key
  finds its original run even after it falls outside the latest 50 history records.
- iOS Dashboard exposes **Tạo gợi ý AI**, a native dialog and an explicit consent checkbox.
  Opening preflight or cancelling does not dispatch a model call. Duplicate submit is guarded;
  ambiguous network failure consumes the quote and directs the user to inspect history.
- `/recommendations` shows the latest 50 runs. Detail separates frozen observations,
  AI inference, assumed scope/team/timeline, rubric, risks and validation questions.
  Rationale-only citations and derived-source references also resolve against frozen evidence.
  Raw links require a valid hash; game links carry snapshot, country and platform.
- Detail polling uses GET every two seconds only while queued/running, stops on terminal
  state/unload, and reloads once on completion. Failure offers explicit manual refresh.
- Free Tier remains owner-attested, five attempted calls per Vietnam-local day, maximum
  2,000 output tokens and no automatic retry/fallback. Unknown actual cost stays unknown.
  No AI is triggered by startup, GET, crawl or schedule.

## Verification evidence

- Final `.venv\Scripts\python.exe -m pytest -q`: **543 passed**, three existing dependency
  deprecation warnings, 162.49 seconds. This includes the final citation and real-engine tests.

- Runtime/worker/security tests: 26 passed during implementation.
- Dashboard rendered contracts: 5 passed during implementation.
- Result/review/polling tests: 23 passed after the citation review fix, including a real
  engine-generated manifest and byte-identical routed result after analytics recalculation.
- `node --test tests/js/test_ai_clients.cjs`: 6 passed after the final client guard fix.
  These execute the actual Dashboard JavaScript with a VM/event DOM fixture, covering
  inert load, scoped preflight, consent, cancel/Escape, double-click, ambiguous failure,
  exhausted/unattested Free Tier and metered policy compatibility. They are not browser tests.
- Ruff on all changed Python source/tests passes. A broader existing AI test lint run found
  pre-existing import/fixture lint issues in `test_ai_evidence.py`, `test_ai_pilot.py` and
  `test_ai_web_security.py`; this report does not claim the whole repository is lint-clean.
- Both client scripts pass `node --check`. Tracked `git diff --check` and new-file
  `git diff --no-index --check` report no whitespace errors (only Git LF/CRLF notices).
- Independent review found missing rationale-only citation rendering; it was fixed with
  RED/GREEN coverage. Fresh final review found no remaining critical/important code issues
  and independently ran 58 focused Python tests and six Node client tests successfully.
  The report link was absent during that review and has now been created.

All model calls in these tests use offline fakes or MockTransport. No live Gemini request,
production data change, `.env` edit, commit, merge or push was performed in this delivery.

## Remaining acceptance gates

- Browser surfaces inventory returned `apps: []`, `browsers: []`. No screenshot or native
  keyboard/layout pass is claimed. Inspect 1280/1440, 768/414/320 px, dialog focus/Escape,
  checkbox confirmation, evidence readability and local table scrolling when available.
- Ten authorized pilot outputs still require Vietnamese clarity, citation correctness,
  inference/estimate separation, timing/token/cost recording and human quality review.
  The [provider decision](p4-provider-decision.md) retains every case as Pending.
  Fake or schema-valid results do not establish quality. Preserve five attempts/day and
  explicit confirmation for each actual call; do not bypass empty-evidence blocking.

Historical 2026-09-25 readiness/storage reports remain historical evidence. Current task
summaries at the top of the four implementation plans track delivered code and these gates;
their original step recipes are retained for reference, not a second unfinished backlog.
