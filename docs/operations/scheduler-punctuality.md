# Scheduler punctuality

## Purpose

Scheduler continuity and scheduler punctuality answer different questions. Continuity proves that
each expected UTC window has one durable execution record. Punctuality proves that the Worker
claimed the window close to its configured due time. Neither claim proves complete source data.

For `arxiv_daily`, the default schedule is `02:00 UTC` (`0 2 * * *`). Timing is derived only from
persisted `scheduler_executions` fields:

```text
dispatch_delay_seconds = max(0, started_at - scheduled_at)
```

| Timing state  | Deterministic rule                                        |
| ------------- | --------------------------------------------------------- |
| `on_time`     | `started_at` exists and delay is at most 300 seconds      |
| `late`        | `started_at` exists and delay is greater than 300 seconds |
| `missed`      | the due window was never claimed                          |
| `interrupted` | a claimed running window was abandoned across restart     |
| `pending`     | a future planned window has not become due                |

Collector outcome is displayed independently as `succeeded`, `partial`, or `failed`. An on-time
partial collection is on time but still partial. A late successful collection is late. No state
is promoted or hidden.

## Post-deployment qualification

E04.6 requires three real terminal windows under `scheduler-punctuality-v1`. The Worker writes this
marker only to a future scheduled plan after the hardened build is deployed. Historical evidence
is retained but cannot qualify the new implementation. The gate is:

- `PENDING` before three due terminal windows exist;
- `FAILED` immediately for any late, missed, interrupted, missing, or duplicate qualification
  window;
- `PASSED` only when all three real windows are terminal and on time.

Manual `arxiv collect` runs create ingestion evidence but no `scheduler_executions` row, so they
cannot satisfy or repair this gate. A restart never backfills a missed qualification as success.

## Read-only operator commands

```powershell
signal-observatory scheduler status --json
signal-observatory scheduler verify-punctuality --json
```

`status` always reports current evidence. `verify-punctuality` exits `0` for passed, `1` for
pending, and `2` for failed. Both return `modified_records = 0` and never trigger a collector.

The Operations API and `/operations` page show continuity, qualification progress, latest planned
time, actual start, delay, timing state, collector outcome, and next expected qualification
window. This is operational evidence, not a popularity, coverage percentage, or Trend Score.

## Host availability

The project does not change the Windows power plan. Docker Desktop, its Linux VM, the computer,
and the Worker must be running at due time for an on-time result. If host sleep prevents execution,
the persisted delay or missed state is the correct result; operators may change their own host
policy outside the application after reviewing security and energy implications.
