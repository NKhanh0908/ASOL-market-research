# Android VN — live batches

Approved source: user requested implementation of the evaluated Android MVP and
batch processing with immediate results, plus a skill-assisted assessment.

## Scope

Google Play Casual VN Top Free and Top Grossing. Headless Selenium worker,
standalone process, no paid API. Persist ranks as soon as each chart is validated.
Enrich the union of packages sequentially in batches of 5; commit metadata and
analysis together per batch, including per-package errors. Poll UI every 2s,
show progress and preserve finished batches on failure/reload. Responsive cards.
Developer is the listed publisher; revenue amounts remain unknown.

## Architecture decision

Existing evidence: 45 rows/chart, 82 unique packages, three successful metadata
samples; previous plan assumed static HTML and excluded Android grossing.
Options: migrate all iOS storage now, or add a bounded Android storage module.
Decision: additive Android tables in existing SQLite, sharing core runs and
collector lock. Avoid changing legacy iOS analytics identity while delivering a
reviewable Android slice. Separate /android page linked from /data and dashboard.
This supersedes the old plan for this implementation; unified cross-platform
dashboard/shortlist remains a future integration, not a claim of this slice.

Rows contain package, free/grossing ranks, metadata status, cached-at/evidence,
taxonomy, per-chart one-day delta where exact previous local date has evidence.
Missing baseline stays unknown; never infer new/removed chart membership from
varying observed depth. Local day is Asia/Ho_Chi_Minh.

Persistent Android queue is separate from actual core runs: a pending request
does not block iOS. Atomic dispatch creates a core run only with no open core run.
Worker must claim shared collector lock. Manual duplicate while active returns
existing Android request; after completion manual requests can run again.
Daily schedule default off; at 07:00 enqueue at most one Android request/date,
after checking existing iOS scheduler. Pending requests survive restart, but
missed daily slots are not created later. One-time iOS schedule remains supported.
Failure/dead worker marks terminal, preserving committed rows; explicit next run
can reuse successful metadata for 48h. Browser closed in finally, 15m run budget.

UI: run selector, chart filter, progress counters, latest batch timestamp, row
status, error details, developer/rating/category/model/deltas. Two-second polling
does not overlap requests; stale response must not overwrite newer selected run.
No full reload or HTML insertion of scraped strings. Same CSRF policy as iOS.

Acceptance: prove batch 1 visible while batch 2 blocked; errors do not erase data;
duplicate/serialization, day/timezone, missing baseline, API validation/CSRF,
headless live crawl and desktop/mobile checks; record observed timings separately
from targets. Keep daily schedule off until evidence supports unattended operation.
