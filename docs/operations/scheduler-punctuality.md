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

## Historical v1 post-deployment qualification

E04.6 requires three real terminal windows under `scheduler-punctuality-v1`. The Worker writes this
marker only to a future scheduled plan after the hardened build is deployed. Historical evidence
is retained but cannot qualify the new implementation. The gate is:

- `PENDING` before three due terminal windows exist;
- `FAILED` immediately for any late, missed, interrupted, missing, or duplicate qualification
  window;
- `PASSED` only when all three real windows are terminal and on time.

Manual `arxiv collect` runs create ingestion evidence but no `scheduler_executions` row, so they
cannot satisfy or repair this gate. A restart never backfills a missed qualification as success.

The v1 qualification failed and remains historical evidence. It must not be reclassified as a v2
success or repaired by manual collection.

## Current v2 qualification

The deployed Worker now marks newly planned `arxiv_daily` windows with
`scheduler-punctuality-v2`. The verifier isolates v2-tagged scheduled windows and does not retag
or count earlier v1 rows. The previously persisted 2026-09-25 02:00 UTC future plan is still v1;
the first eligible v2 due window is 2026-09-26 02:00 UTC if the Worker plans it. Deployment on
2026-09-24 yielded `PENDING`, 0/3; it did not prove a successful scheduler run.

The v2 punctuality gate requires three consecutive real v2 scheduled dispatches no more than 300
seconds late. The separate rolling continuity gate requires seven consecutive real natural daily
windows with no missing, duplicate, missed, or interrupted row. Do not infer either result from
container health alone. A manual run cannot satisfy either gate, and the collector outcome is
reported separately from timing. Evidence for the initial deployment and host policy is in
`docs/operations/scheduler-v2-readiness-2026-09-24.md`.

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

The application does not change the Windows power plan at runtime. On 2026-09-24 the owner approved
an operator-level AC-only setting change: automatic host sleep is disabled while plugged in, but
the display still turns off after 60 minutes of inactivity. Battery sleep remains 30 minutes.
Docker Desktop, its Linux VM, the computer, and the Worker still must be running at due time for
an on-time result. Reboot recovery, lid-close behavior, power loss, and Docker startup are not
proven by the AC sleep setting. If host unavailability prevents execution, the persisted delay or
missed state is the correct result.
