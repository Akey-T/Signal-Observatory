# P1-C GitHub partial-outcome diagnosis — 2026-09-24 UTC

This was a read-only analysis of persisted GitHub runs, quality checks, configuration and
cross-day verification. No repository snapshots, poll state, Raw, missing dates, or scheduler
evidence were changed.

## Current facts

- Latest scheduled snapshot run `2869e62d-4c63-411e-9cf1-cbaca079b867` at
  `2026-09-24T02:30:00Z` ended `partial`: 510 repositories due, 100 requests, 100 snapshots,
  392 missing due observations in its quality check, one aggregate error, and zero persisted
  `ingestion_errors` for that run. The 392 is a run-level due gap, not permission to backfill
  historical daily snapshots.
- From `2026-09-01` through `2026-09-24`, all 18 persisted snapshot runs were `partial`. Sixteen
  reached exactly the configured `github_max_requests_per_run = 100`; the tracked/due set was
  roughly 402–510. Their one aggregate error commonly represents the service's request-cap or
  runtime stop, which increments `error_count` without inserting an `IngestionError` row.
- Two runs (`2026-09-05` and `2026-09-09`) stopped after only 3 and 1 requests, respectively,
  despite 502/506 due. They lasted roughly 92 and 172 minutes, exceeding the configured
  30-minute runtime cap. The persisted facts support runtime exhaustion; host suspension is a
  plausible but unproven explanation for the long wall-clock gaps.
- A `2026-09-15` snapshot run persisted two `GithubTransportError` rows and still reached 100
  requests. Two September weekly discovery runs were also `partial`, each with a persisted
  `GithubBudgetExhaustedError`. These are separate from the dominant daily snapshot capacity gap.
- `github verify-cross-day --json` remains passed with zero integrity mismatches. Historical
  missing observation dates remain missing, and forward-only snapshot semantics remain intact.

## Decision

The recurring 100-request cap against approximately 500 due repositories is a current bounded
capacity mismatch, not just a reporting defect. A separate, tested configuration/collector
change may be proposed after reviewing GitHub API budget, runtime and desired daily tracking
coverage; this diagnosis does not silently raise limits or create manual replacement snapshots.
Transport and discovery-budget failures should be monitored independently.
