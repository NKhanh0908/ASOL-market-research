# Android CLI and web acceptance

Updated 2026-09-29 against baseline `df63544`.

Offline acceptance covers authorized core crawl submission, real SQLite persistence,
analysis, JSON data/radar, rendered game detail and fresh ranking with cached metadata
on a second run. The provider is synthetic; this does not prove live Top100 coverage.
Existing iOS evidence fingerprints remain unchanged.

CLI/API/schedule regression tests cover platform order, feed scope, validation, CSRF,
origin, busy state, idempotency, single launch, launch failure, abandoned-launch recovery
and atomic eighteen-chart Android schedules. Archive paths retain historical pages.
No application source imports Selenium.

Rendered HTML tests cover installs, scoped navigation/export, missing metadata and
historical evidence. Browser inspection at 390/1440px remains **unverified** because no
browser is exposed in this environment. Live completeness and speed gates remain open.

See [execution report](2026-09-29-android-plan-completion.md) and
[benchmark evidence](2026-09-29-google-play-http-benchmark.json).
