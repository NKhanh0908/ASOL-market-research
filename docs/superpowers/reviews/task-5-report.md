# P4.2 Task 5 offline pilot report — 2026-09-25

Created ten compact synthetic pilot cases in `tests/fixtures/ai/pilot-cases.json` and
focused coverage/ID-closure checks in `tests/test_ai_pilot.py`. The cases cover empty
scope, VN without baseline, VN 1D rise, multi-market rise, newly crawled market, partial
source, unknown mechanic, conflicting mechanics, adversarial description, and no credible
recommendation. Fields mirror P4 test-generated evidence shapes; synthetic IDs and dummy
hashes are not verified store records.

The selected integration remains Gemini Developer API `gemini-2.5-flash` under the
owner-approved Free Tier guardrail recorded in `p4-provider-decision.md`. This task made
no provider call, account check, billing change, or production data read. All ten live
acceptance rows remain pending human review; BA-R10 is not met by these offline fixtures.

Focused verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_ai_pilot.py
```

Final result: 12 passed in 0.11s. The test was first observed failing because the fixture file
was absent, then passed after adding the fixture and correcting the description-only
adversarial text assertion.
