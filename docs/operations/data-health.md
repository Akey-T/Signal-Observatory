# Data health and operational state

## Purpose

Data Health answers whether Signal Observatory is operating correctly now. It does not claim that
the historical dataset is complete. The `/operations` page and `GET /api/operations` keep these
concepts separate:

- **Collector health**: whether recent configured collection runs are succeeding.
- **Freshness**: how long ago persisted source evidence was last observed.
- **Coverage**: what historical interval exists and whether its declared target was completed.
- **Registry health**: whether the curated Topic Registry is internally valid.
- **Scheduler continuity**: whether every expected UTC window was durably claimed and terminated.
- **Scheduler punctuality**: whether dispatch began within the explicit delay threshold.

No composite health percentage is calculated.

## Deterministic states

Collector states are `healthy`, `degraded`, `failed`, `not_initialized`, `not_configured`, and
`paused`. Freshness is `fresh`, `stale`, `very_stale`, or `unknown`. Thresholds are configured per
implemented source; the very-stale threshold must be greater than the fresh threshold.

Overall Observatory state is derived as follows:

1. `failed` when an active collector has a critical failed state.
2. `degraded` when an active collector is not healthy, historical coverage is partial or unknown,
   an active source is stale, or an expected observation date is missing.
3. `healthy` when all active collectors are operationally healthy and no degrading condition is
   present. GitHub `forward_only` coverage is expected and does not itself degrade health.
4. `not_started` when no collector is active.

Community/Hacker News and Public/Wikipedia are currently reported as not collecting, not as
errors. Their absence does not create fabricated coverage rows.

Coverage rebuilds are source-scoped. An arXiv/GitHub rebuild may create, update, or delete only
the projections owned by those implemented derivation handlers; it preserves rows owned by future
Hacker News, Wikipedia, or other handlers.

## Data-quality counters

Operations exposes persisted counts for ingestion errors in the last 24 hours, unresolved partial
arXiv mappings, stale cursors, missing GitHub snapshot dates, and Registry warnings. Raw checksum
failures are not reported as zero unless a verification was performed; the live API reports them
as not verified because a page request must never scan the Raw lake.

Use the bounded, read-only verifier instead:

```powershell
signal-observatory ops verify-raw --sample 100 --json
signal-observatory ops verify-raw --source github --sample 100 --json
signal-observatory ops verify-raw --full --json
```

It checks the database pointer, filesystem object, payload checksum, and metadata sidecar. It does
not repair or modify any record. Full scans should be scheduled deliberately rather than run on
every page request.

## Operational checks

```powershell
signal-observatory ops check
signal-observatory ops check --json
signal-observatory github verify-cross-day --json
signal-observatory arxiv verify-soak --days 7 --json
```

`ops check` combines Registry, migration, source health, coverage and a bounded Raw sample. Exit
codes are `0` healthy/acceptable, `1` degraded, `2` failed/action required, and `3`
configuration/database failure.

The cross-day and soak commands are read-only acceptance gates. A GitHub dataset with only one
real UTC observation date returns `PENDING`; it does not generate another snapshot. The arXiv soak
counts only persisted scheduler-tagged runs and allows legitimate partial runs as evidence when
their errors and cursor outcomes are recorded. Manual runs never become scheduled evidence.

Expected windows are persisted in `scheduler_executions` before they become due. A run transitions
`scheduled → running → succeeded|partial|failed` using the collector's persisted terminal outcome;
a returned partial or failed collection is never promoted to scheduler success. On Worker restart,
every elapsed window after the last materialized plan is created and recorded as `missed`, while a
previously running plan is recorded as `interrupted`. Neither state triggers a hidden manual replay.
Window claims are atomic and one PostgreSQL advisory leader owns scheduling. arXiv and GitHub have
independent execution locks; GitHub snapshot and discovery remain serialized with each other
because they share one source budget. Missed, interrupted, late, partial, and failed counts are exposed
separately in the Operations API and UI. Registry warnings and each scheduler anomaly both degrade
the overall Operations state and are named in its explanation.

`scheduled_at → started_at` is the only dispatch-delay calculation. `≤300` seconds is `on_time`;
greater delay is `late`. Missing and interrupted windows retain their own states. Collector
`succeeded`, `partial`, or `failed` is shown beside timing and cannot overwrite it. The E04.6
qualification starts only at a future plan carrying `scheduler-punctuality-v1` and requires three
real terminal windows. Manual ingestion runs have no scheduler row and cannot satisfy it. See
[`scheduler-punctuality.md`](scheduler-punctuality.md).

## Backup scope

E04.5B backup/restore automation treats PostgreSQL, immutable Raw, Registry configuration, and
provenance as one recovery unit. Source recovery adapters fail closed so that a future collector
cannot be enabled while its Raw or lineage is silently excluded from verification. Database-only
or Raw-only copies are not sufficient.
