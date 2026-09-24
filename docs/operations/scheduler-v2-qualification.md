# Scheduler punctuality v2 — daily qualification evidence

The `scheduler-punctuality-v1` result is historically failed and immutable. This ledger starts a
new versioned evaluation; it must never relabel an old execution or a manual collection as a v2
scheduled success. The persisted 2026-09-25 02:00 UTC future plan is v1. The first eligible v2
window is 2026-09-26 02:00 UTC, if the Worker actually plans and executes it under the v2 marker.

## Gates

- Punctuality: three consecutive real v2-tagged `arxiv_daily` scheduled windows, each with
  `dispatch_delay_seconds <= 300`. A missing, duplicate, missed, interrupted, or late window
  fails that sequence.
- Continuity: seven consecutive real natural daily windows with no missing, duplicate, missed,
  or interrupted scheduler record. This is independent of the three-window timing gate.
- Collector outcome, Raw count, and error count are recorded separately. A timely but partial
  collection is not complete source coverage; an untimely successful collection is still late.

Read-only daily checks should include Docker Worker health and logs, `scheduler status --json`,
`scheduler verify-punctuality --json`, the persisted scheduler execution for the UTC due window,
and Raw/error counts compared with the previous day. Each entry must name the actual UTC window
and observation time. If evidence is unavailable, say so; do not backfill or hand-run collection
to repair a qualification day.

## Status before first eligible v2 window

On 2026-09-24 after the v2 deployment, the read-only verifier reported `PENDING`, 0/3; no v2
scheduled run had occurred. Rolling seven-day continuity was `FAILED` because the then-current
seven-day evidence contained one missed/interrupted window. This is deployment baseline only,
not Day 1. See `docs/operations/scheduler-v2-readiness-2026-09-24.md` for tests and host state.

Daily checks are scheduled in this Codex task after the 02:00 UTC due time. A scheduled Codex
check does not keep the Windows host or Docker Desktop running; it only inspects and records the
evidence that actually exists. Notifications are reserved for failure, completion, or required
owner action.

## Daily evidence

No eligible v2 natural-day evidence has been observed yet.
