# Android core storage acceptance

Updated 2026-09-29 against baseline `df63544`. Offline implementation verified.

Regression tests cover additive installs fields, migration repeatability, validated
Android identity, cross-platform analytics collision rollback, per-country complete
metadata cache with exact 48-hour expiry, snapshot binding and immutable evidence.

Core collector tests cover partial chart preservation, bodyless HTTP errors, retries,
incremental persistence, heartbeat and interruption lock cleanup. Analysis tests cover
free/grossing union, same-feed history, grossing-only apps, missing days, partial
baseline safeguards and bound metadata. Mixed Android/iOS backup/restore preserves
row fingerprints and raw SHA-256 hashes; foreign-key checks pass. No backup code
change was needed because the existing whole-database backup includes core tables.

The full offline suite passed 507 tests. All acceptance databases were temporary.
Live source completeness/performance is separate: see the
[execution report](2026-09-29-android-plan-completion.md).
