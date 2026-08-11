# E03 seven-day scheduler soak

Status: **In progress — no seven-day pass claimed**

Formal window: 2026-08-12 through 2026-08-18, scheduled daily at 02:00 UTC
(12:00 Australia/Sydney). Review heartbeat: 12:20 Australia/Sydney.

## Acceptance rule

Seven consecutive real scheduled arXiv executions must be evidenced by the Worker log and the
persisted ingestion run, Raw responses, cursor outcome, and errors. Manual runs do not count as a
scheduler success. A sleeping/stopped host or stopped Docker Desktop produces a missing/failed day;
it is never backfilled or relabeled as scheduled evidence.

## Preflight on 2026-08-11

Docker services were healthy and the Worker had been up for approximately 18 hours, but the
2026-08-11 02:00 UTC execution was absent. Worker logs contained only startup/scheduling evidence.
The likely mechanism was Windows host sleep while the old scheduler waited on one long monotonic
timer. This is recorded as a preflight failure, not Day 1.

The scheduler now checks wall-clock time at short intervals. On wake, an already-due job executes;
independent source failures are contained and collectors are serialized with a shared lock.

The corrected Worker image was deployed at `2026-08-11T06:30:53Z`. Its startup log records the
next arXiv execution as `2026-08-12T02:00:00Z`; all four Compose services were healthy and the
database was at migration head `20260811_0004`. This is readiness evidence, not a Day 1 pass.

## Controlled recovery (not counted)

Manual run `a245d1bd-696d-4121-87b8-53ebd3825d76` preserved 47 Raw responses, received 788 entries,
created 576 Papers, reused 212 existing Papers, and created 788 Topic matches. The run was partial:
`ai-agents` received HTTP 429 and `artificial-intelligence` timed out after three attempts. It had
no parse errors or missing relations, and durable cursors remained safe. This proves recovery, not
scheduler continuity.

## Daily evidence

| Day | Scheduled UTC    | Worker schedule evidence | Ingestion run | Raw / records / errors | Result  |
| --: | ---------------- | ------------------------ | ------------- | ---------------------- | ------- |
|   1 | 2026-08-12 02:00 | Pending                  | Pending       | Pending                | Pending |
|   2 | 2026-08-13 02:00 | Pending                  | Pending       | Pending                | Pending |
|   3 | 2026-08-14 02:00 | Pending                  | Pending       | Pending                | Pending |
|   4 | 2026-08-15 02:00 | Pending                  | Pending       | Pending                | Pending |
|   5 | 2026-08-16 02:00 | Pending                  | Pending       | Pending                | Pending |
|   6 | 2026-08-17 02:00 | Pending                  | Pending       | Pending                | Pending |
|   7 | 2026-08-18 02:00 | Pending                  | Pending       | Pending                | Pending |

Codex heartbeat automation: `e03-7-day-scheduler-soak`. It reviews evidence once daily and appends
facts to this file; it must never turn a manual collection into a scheduled pass.
