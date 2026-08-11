# Topic source coverage ledger

## Purpose

The Coverage Ledger records what Signal Observatory can honestly claim for every curated
Topic × implemented Source. It is a rebuildable projection derived from persisted source facts,
not an administrative completeness flag. Future analytics must consume coverage metadata together
with metric values and confidence.

The projection is stored in `topic_source_coverage` and is uniquely keyed by Topic and Source. It
includes the target and observed windows, first and last successful observations, observation and
missing counts, a partial reason, source-specific metadata, and `derivation_version = coverage-v1`.

## Status meanings

| Status         | Meaning                                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------------------- |
| `complete`     | Every expected unit in the explicitly declared historical target window completed without an unresolved cursor gap. |
| `partial`      | Some expected historical work is unresolved or failed; `partial_reason` explains why.                               |
| `forward_only` | History begins at the Observatory's first real observation and accumulates forward by design.                       |
| `empty`        | The configured source completed the relevant work and found zero observations. This is not a failure.               |
| `unknown`      | Persisted facts are insufficient to make a reliable coverage claim.                                                 |

Community and Public additionally return `collection_state = not_started` at the API layer. No fake
database projections are created for unimplemented collectors.

## arXiv derivation

arXiv coverage is derived from the enabled Source Mapping, declared Backfill Cursor windows,
Ingestion Runs and persisted Topic Matches. `complete` requires a persisted target window, all of
its windows to have succeeded, no unresolved cursor gaps, and at least one observation. A completed
zero-result target is `empty`. Any unresolved, failed, partial or missing expected window is
`partial`. Without a reliable declared target it remains `unknown`, even if the latest incremental
run succeeded.

## GitHub derivation

GitHub daily Repository Snapshots cannot be reconstructed before the Observatory first observed a
Repository. The first real Snapshot date is therefore `coverage_start`; the latest is
`coverage_end`; the status is `forward_only` for both one-day and multi-day histories.

The missing-date detector compares every UTC date between the first and latest actual Snapshot
dates with persisted observation dates. Missing dates remain visible and are never filled,
interpolated, or treated as historical backfill. Before the first Snapshot the state is `unknown`,
unless a completed discovery established an honestly empty tracked set.

## Rebuild and query

```powershell
signal-observatory coverage rebuild --json
signal-observatory coverage list --source arxiv --status partial
signal-observatory coverage list --stale
signal-observatory coverage show --topic model-context-protocol --json
```

Rebuild is deterministic and idempotent: unchanged facts retain the prior projection and its
`derived_at` timestamp. Worker and real collector CLI paths rebuild the projection after durable
collection; dry runs do not. APIs query the projection and do not launch derivation or scan Raw:

- `GET /api/coverage`
- `GET /api/topics/{slug}/coverage`
- `GET /api/operations`

The `/operations` Coverage Matrix supports Topic search and Source/Status filtering. Topic Detail
shows a compact per-channel summary and links to Operations. Neither surface displays an invented
completeness percentage.
