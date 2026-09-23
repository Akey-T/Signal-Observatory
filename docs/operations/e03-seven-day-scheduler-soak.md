# E03 seven-day scheduler soak

Status: **Original window failed; recovery window passed — 7/7**

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

### Early heartbeat at 2026-08-11 15:04 UTC

The automation fired at 01:04 Australia/Sydney, before the formal Day 1 window at
`2026-08-12T02:00:00Z` (12:00 Australia/Sydney). This was recorded as a read-only readiness check;
Day 1 remains pending rather than missing or passed.

All four Compose services were healthy. The current Worker had been up for approximately 13 hours,
and its log recorded `arxiv_daily` scheduled for `2026-08-12T02:00:00Z`. PostgreSQL contained zero
arXiv incremental runs with `trigger = scheduled` before Day 1. The latest arXiv run remained the
manual recovery run `a245d1bd-696d-4121-87b8-53ebd3825d76` (47 Raw responses, 788 records received,
576 inserted, 212 skipped, 2 persisted errors, partial); it was not counted as scheduler evidence.
No database record was modified by this check.

## Controlled recovery (not counted)

Manual run `a245d1bd-696d-4121-87b8-53ebd3825d76` preserved 47 Raw responses, received 788 entries,
created 576 Papers, reused 212 existing Papers, and created 788 Topic matches. The run was partial:
`ai-agents` received HTTP 429 and `artificial-intelligence` timed out after three attempts. It had
no parse errors or missing relations, and durable cursors remained safe. This proves recovery, not
scheduler continuity.

## Daily evidence

| Day | Scheduled UTC    | Worker schedule evidence                       | Ingestion run           | Raw / records / errors | Result                            |
| --: | ---------------- | ---------------------------------------------- | ----------------------- | ---------------------- | --------------------------------- |
|   1 | 2026-08-12 02:00 | Scheduled metadata at 02:00; log retention gap | `d386be72…` partial     | 74 / 17 / 30           | Qualified partial                 |
|   2 | 2026-08-13 02:00 | Start and completion retained in Worker log    | `f9f7cf0d...` partial   | 74 / 52 / 25           | Qualified partial                 |
|   3 | 2026-08-14 02:00 | Start and completion retained in Worker log    | `794b68f9...` partial   | 106 / 17 / 40          | Qualified partial                 |
|   4 | 2026-08-15 02:00 | Worker unavailable at due time                 | None                    | 0 / 0 / 0              | Missed                            |
|   5 | 2026-08-16 02:00 | Worker unavailable at due time                 | None                    | 0 / 0 / 0              | Missed                            |
|   6 | 2026-08-17 02:00 | Worker unavailable at due time                 | None                    | 0 / 0 / 0              | Missed                            |
|   7 | 2026-08-18 02:00 | Scheduled run completed 11 minutes late        | `65a1ecda...` succeeded | 55 / 1961 / 0          | Qualified; original window failed |

Codex heartbeat automation: `e03-7-day-scheduler-soak`. It reviews evidence once daily and appends
facts to this file; it must never turn a manual collection into a scheduled pass.

## Day 1 — 2026-08-12

Checked at `2026-08-12T12:25:08Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The current Worker container was
  recreated at approximately `12:17 UTC` during the independently accepted E04.5B deployment, so
  its retained log starts with the new process and no longer contains the earlier completion line.
  It records the next `arxiv_daily` execution as `2026-08-13T02:00:00Z`.
- PostgreSQL contains exactly one arXiv incremental run tagged `trigger = scheduled` for the due
  window: `d386be72-eeb4-4261-bae5-96e368db524c`, started at
  `2026-08-12T02:00:00.128577Z`, finished at `02:30:02.278752Z`, status `partial`. The CLI does not
  assign the scheduled trigger; that tag is emitted by the Worker scheduler path. There is no
  duplicate or unfinished scheduled run.
- The run made 103 API attempts, persisted 74 immutable Raw responses, received 17 records,
  inserted 6 Papers, skipped 11 existing Papers, added 6 Topic matches, and persisted 30 errors.
  The errors were 22 HTTP 429 responses and 8 exhausted transport timeouts. There were zero parse
  errors, zero missing author/category relations, and zero stale cursors.
- Cursor state after the run was 14 `succeeded`, 17 `partial`, and 30 `failed`; all 30 failed
  cursors retained an explicit error. This is a legitimate, observable partial outcome and is
  allowed as scheduler-execution evidence; it is not presented as complete collection coverage.
- Compared with 2026-08-11, that prior UTC day had no scheduled run. Its manual recovery run
  persisted 47 Raw responses, 788 records, and 2 errors and remains excluded from the soak count.
  Current cumulative arXiv totals are 141 Raw responses and 32 persisted errors.
- The read-only soak verifier returned `pending`: 1 actual scheduled run, 1 partial, 0 missing,
  0 duplicates, 0 cursor anomalies, and 6 future windows remaining. It reported
  `modified_records = 0`.

Day 1 is recorded as a qualified real scheduled execution with a partial data outcome. The missing
historical completion log is explicitly retained as an evidence caveat caused by container
replacement; the exact scheduled timestamp, scheduler-only trigger, completed persisted run, Raw,
errors, and cursor outcomes remain available in PostgreSQL. No arXiv record was modified by this
review.

## Day 2 — 2026-08-13

Checked at `2026-08-13T12:21:33Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker had remained up for
  approximately 11 hours. Its retained log records the scheduled start at `02:00:00.065075Z`, the
  terminal collection event at `02:26:26.332506Z`, status `partial`, and the next real arXiv plan
  at `2026-08-14T02:00:00Z`.
- PostgreSQL contains exactly one scheduler execution for the Day 2 window. It transitioned from
  `scheduled` to `running` at `02:00:00.035171Z` and finished `partial` at
  `02:26:26.332660Z` with explicit `collector_partial` evidence. The corresponding incremental
  ingestion run is `f9f7cf0d-06a1-437a-92fa-2f49b7833d58`, tagged `trigger = scheduled`; there is
  no manual-run substitution.
- The run made 96 API attempts, persisted 74 immutable Raw responses, received 52 records,
  inserted 22 Papers, updated 1 persisted record, skipped 29 existing records, and persisted 25
  errors. Raw status evidence contains 17 HTTP 200 responses and 57 HTTP 429 responses. Persisted
  errors comprise 17 `ArxivHTTPError` and 8 `ArxivTransportError` records.
- Compared with Day 1, Raw count was unchanged at 74; received records increased from 17 to 52,
  inserted records increased from 6 to 22, skipped records increased from 11 to 29, and errors
  decreased from 30 to 25. HTTP 200 responses increased from 9 to 17 and HTTP 429 responses
  decreased from 65 to 57, while transport errors remained at 8. The outcome remains partial and
  is not represented as complete coverage.
- After Day 2, cumulative arXiv evidence is 215 Raw responses and 57 persisted ingestion errors.
  The read-only soak verifier returned `pending`: 2 actual scheduled runs, 2 partial, 0 failed,
  0 missing, 0 duplicates, 0 cursor anomalies, and 5 future windows remaining. It reported
  `modified_records = 0`.

Day 2 is recorded as the second qualified real scheduled execution with a partial data outcome.
No arXiv table, Research API semantic, Topic Match, or Raw observation was modified by this review.

## Day 3 — 2026-08-14

Checked retrospectively on `2026-08-17T08:49:39Z` from retained Worker, scheduler, and PostgreSQL
evidence captured after the `02:00 UTC` window.

- The retained Worker log records the scheduled start at `02:00:00.122847Z`, completion at
  `02:24:48.546477Z`, status `partial`, and the next plan at `2026-08-15T02:00:00Z`.
- PostgreSQL contains exactly one scheduler execution for this window. It started at
  `02:00:00.002084Z` and finished `partial` at `02:24:48.546722Z` with
  `error_type = collector_partial`. The corresponding scheduled incremental ingestion run is
  `794b68f9-d4dd-4c64-8171-c4326f3aa0d9`; there is no manual-run substitution.
- The run made 122 API attempts, persisted 106 immutable Raw responses, received 17 records,
  inserted 6 Papers, updated 0 records, skipped 11 existing records, and persisted 40 errors. Raw
  evidence contains 2 HTTP 200 and 104 HTTP 429 responses. Errors comprise 31 `ArxivHTTPError`
  and 9 `ArxivTransportError` records.
- Compared with Day 2, Raw increased from 74 to 106 while received records decreased from 52 to 17. Errors increased from 25 to 40, HTTP 200 responses decreased from 17 to 2, HTTP 429
  responses increased from 57 to 104, and transport errors increased from 8 to 9. Source health
  materially worsened, so this is qualified scheduler evidence with a partial data outcome only.

Day 3 is recorded as the third qualified real scheduled execution. No arXiv record was modified by
this retrospective review.

## Days 4–6 interruption — 2026-08-15 through 2026-08-17

Checked at `2026-08-17T08:49:39Z`. Docker Desktop was stopped: the Docker named pipe was absent,
`com.docker.service` was stopped, and ports 5432 and 8000 were unavailable. The environment was
safely restarted without running any collector manually. All four Compose services then returned
healthy.

- On startup at `2026-08-17T08:51:30Z`, the durable scheduler reconciled the arXiv windows for
  `2026-08-15T02:00:00Z`, `2026-08-16T02:00:00Z`, and `2026-08-17T02:00:00Z` as `missed`, each
  with `error_type = worker_unavailable_at_due_time`.
- PostgreSQL contains no scheduled ingestion run, Raw response, or ingestion error for any of
  those three windows. They were not replayed, backfilled, or relabeled as scheduler success.
- The read-only soak verifier returned `failed`: 3 actual scheduled runs, all 3 partial; 3 missing
  dates (`2026-08-15`, `2026-08-16`, `2026-08-17`); 0 duplicates; 0 cursor anomalies; and 1
  remaining window in the original period. It reported `modified_records = 0`.
- The Worker has materialized the next real arXiv plan at `2026-08-18T02:00:00Z`. This is recovery
  readiness only and does not repair the missed evidence.

The original 2026-08-12 through 2026-08-18 seven-day continuity gate has failed and cannot be
accepted. A new seven-consecutive-day qualification sequence may begin with the real
`2026-08-18T02:00:00Z` window and would require uninterrupted evidence through
`2026-08-24T02:00:00Z`. Days 1–3 do not carry forward into that new consecutive count. No arXiv
table, Research API semantic, Topic Match, or Raw observation was modified by this review.

## Recovery qualification window — 2026-08-18 through 2026-08-24

| Recovery day | Scheduled UTC    | Ingestion run           | Raw / records / errors | Result              |
| -----------: | ---------------- | ----------------------- | ---------------------- | ------------------- |
|            1 | 2026-08-18 02:00 | `65a1ecda...` succeeded | 55 / 1961 / 0          | Qualified succeeded |
|            2 | 2026-08-19 02:00 | `0c2004a8...` partial   | 103 / 1398 / 26        | Qualified partial   |
|            3 | 2026-08-20 02:00 | `0264a6bc...` partial   | 81 / 1666 / 16         | Qualified partial   |
|            4 | 2026-08-21 02:00 | `1548105a...` partial   | 48 / 1199 / 0          | Qualified partial   |
|            5 | 2026-08-22 02:00 | `afcb355c...` partial   | 44 / 615 / 0           | Qualified partial   |
|            6 | 2026-08-23 02:00 | `1114d533...` partial   | 42 / 130 / 0           | Qualified partial   |
|            7 | 2026-08-24 02:00 | `fd78146c...` partial   | 42 / 207 / 0           | Qualified partial   |

### Recovery Day 1 — 2026-08-18

Checked at `2026-08-18T12:20:49Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker had remained up for
  approximately 27 hours. Its retained log records run start at `02:11:24.408704Z`, completion at
  `02:14:08.118555Z`, status `succeeded`, and the next arXiv plan at
  `2026-08-19T02:00:00Z`.
- The scheduler window remained the persisted `2026-08-18T02:00:00Z` plan and transitioned to
  `running` at `02:11:24.237379Z`, approximately 11 minutes 24 seconds late, before finishing
  `succeeded` at `02:14:08.118725Z`. The host likely did not execute wall-clock work during that
  interval; this lateness is retained rather than hidden. No manual collection was used.
- The corresponding incremental run is `65a1ecda-21e7-4e82-9379-5d16fbfa282f`, tagged
  `trigger = scheduled`. It made 55 API requests, persisted 55 immutable Raw responses, received
  1,961 records, inserted 689 Papers, updated 59 records, skipped 1,213 existing records, and
  persisted 0 errors. All 55 Raw responses were HTTP 200; there were no ingestion-error rows.
- Compared with the immediately preceding calendar window on 2026-08-17, Day 1 recovered from a
  `missed` window with no run to a complete scheduled run. Compared with the last real collection
  on 2026-08-14, Raw decreased from 106 to 55, received records increased from 17 to 1,961,
  HTTP 200 responses increased from 2 to 55, HTTP 429 responses decreased from 104 to 0, and
  errors decreased from 40 to 0.
- Cumulative arXiv evidence is now 376 Raw responses and 97 persisted ingestion errors. The prior
  errors remain immutable historical evidence; the successful run does not erase them.

Recovery Day 1 is the first qualified execution in the new sequence. It does not repair or carry
forward evidence from the failed original window. No arXiv table, Research API semantic, Topic
Match, or Raw observation was modified by this review.

### Recovery Day 2 — 2026-08-19

Checked at `2026-08-19T10:52:36Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The retained Worker log records run
  start at `03:13:47.445196Z`, completion at `03:20:59.935156Z`, status `partial`, and the next
  arXiv plan at `2026-08-20T02:00:00Z`.
- The scheduler window remained the persisted `2026-08-19T02:00:00Z` plan and transitioned to
  `running` at `03:13:47.413402Z`, approximately 1 hour 13 minutes 47 seconds late, before
  finishing `partial` at `03:20:59.935300Z` with `error_type = collector_partial`. This lateness
  is retained rather than hidden; no manual collection was used.
- The corresponding incremental run is `0c2004a8-3205-4bcc-91c4-4d0afb1b2696`, tagged
  `trigger = scheduled`. It made 103 API requests, persisted 103 immutable Raw responses,
  received 1,398 records, inserted 854 Papers, updated 4 records, skipped 540 existing records,
  and persisted 26 errors. Raw evidence contains 25 HTTP 200 and 78 HTTP 429 responses. All 26
  persisted errors are `ArxivHTTPError`; there were no transport-error rows.
- Compared with Recovery Day 1, Raw increased from 55 to 103 while records received decreased from
  1,961 to 1,398. Inserted Papers increased from 689 to 854, HTTP 200 responses decreased from 55
  to 25, HTTP 429 responses increased from 0 to 78, and errors increased from 0 to 26. The result
  is qualified scheduler continuity evidence but remains a partial data outcome.
- Cumulative arXiv evidence is now 479 Raw responses and 123 persisted ingestion errors. Prior
  observations and errors remain immutable.

Recovery Day 2 is the second qualified execution in the new sequence. No arXiv table, Research API
semantic, Topic Match, or Raw observation was modified by this review.

### Recovery Day 3 — 2026-08-20

Checked at `2026-08-20T12:22:03Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker had remained up for
  approximately 25 hours. Its retained log records run start at `02:00:00.137640Z`, completion at
  `02:14:42.011070Z`, status `partial`, and the next arXiv plan at
  `2026-08-21T02:00:00Z`.
- The persisted `2026-08-20T02:00:00Z` scheduler window transitioned to `running` at
  `02:00:00.010875Z` and finished `partial` at `02:14:42.011307Z` with
  `error_type = collector_partial`. The approximately 11-millisecond start delay is consistent with
  a live due-time claim. No manual collection or replacement run was used.
- The corresponding incremental run is `0264a6bc-23ba-4e18-8426-2fad44e4cf1f`, tagged
  `trigger = scheduled`. It made 81 persisted Raw requests, received 1,666 records, inserted 814
  Papers, updated 9 records, skipped 843 existing records, and persisted 16 errors. Raw evidence
  contains 38 HTTP 200 and 43 HTTP 429 responses. The error rows comprise 14 `ArxivHTTPError` and
  2 `ArxivTransportError` records.
- Compared with Recovery Day 2, Raw decreased from 103 to 81 while records received increased from
  1,398 to 1,666. Inserted Papers decreased from 854 to 814, HTTP 200 responses increased from 25
  to 38, HTTP 429 responses decreased from 78 to 43, and total errors decreased from 26 to 16.
  Reliability improved relative to Day 2, but the persisted outcome remains partial and is not
  relabeled as success.
- Cumulative arXiv evidence is now 560 Raw responses and 139 persisted ingestion errors. Prior Raw
  and errors remain immutable.

Recovery Day 3 is the third qualified scheduler-continuity execution in the new sequence, while its
data outcome remains partial. No arXiv table, Research API semantic, Topic Match, or Raw observation
was modified by this review.

### Recovery Day 4 — 2026-08-21

Checked at `2026-08-21T12:20:45Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker container had remained up for
  approximately two days. Its retained log records run start at `06:55:09.644235Z`, completion at
  `06:57:31.456042Z`, status `partial`, and the next arXiv plan at
  `2026-08-22T02:00:00Z`.
- The persisted `2026-08-21T02:00:00Z` scheduler window transitioned to `running` at
  `06:55:09.579660Z`, approximately 4 hours 55 minutes 10 seconds late, and finished `partial` at
  `06:57:31.456297Z` with `error_type = collector_partial`. The retained container uptime together
  with the delayed arXiv and other scheduled work is consistent with the host not executing during
  the due-time interval. The lateness is preserved; no manual collection or replacement run was
  used.
- The corresponding incremental run is `1548105a-f18e-48e2-a962-b8624d752cfa`, tagged
  `trigger = scheduled`. It persisted 48 immutable Raw responses, received 1,199 records, inserted
  374 Papers, updated 13 records, skipped 812 existing records, and persisted 0 ingestion errors.
  All 48 Raw responses were HTTP 200; there were no HTTP 429 or ingestion-error rows.
- Zero ingestion errors did not make the run complete. Persisted quality evidence records two stale
  cursors and two failed mappings, and the checkpoints identify `large_incremental_query` partials
  for Artificial Intelligence and Machine Learning. The collector and scheduler therefore
  correctly retained `partial` rather than inventing success.
- Compared with Recovery Day 3, Raw decreased from 81 to 48, records received decreased from 1,666
  to 1,199, and inserted Papers decreased from 814 to 374. HTTP 200 responses increased from 38 to
  48, HTTP 429 responses decreased from 43 to 0, and errors decreased from 16 to 0. The HTTP path
  improved, while the two cursor/mapping gaps kept the data outcome partial.
- Cumulative arXiv evidence is now 608 Raw responses and 139 persisted ingestion errors. The error
  total did not increase, and all earlier evidence remains immutable.

Recovery Day 4 is the fourth qualified scheduler-continuity execution in the new sequence, while
its delayed start and partial data outcome remain explicit. GitHub activity was not used in this
decision. No arXiv table, Research API semantic, Topic Match, or Raw observation was modified by
this review.

### Recovery Day 5 — 2026-08-22

Checked at `2026-08-22T12:21:39Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker container had remained up for
  approximately three days. Its retained log records run start at `09:39:39.006771Z`, completion at
  `09:42:02.942152Z`, status `partial`, and the next arXiv plan at
  `2026-08-23T02:00:00Z`.
- The persisted `2026-08-22T02:00:00Z` scheduler window transitioned to `running` at
  `09:39:38.840753Z`, approximately 7 hours 39 minutes 39 seconds late, and finished `partial` at
  `09:42:02.942309Z` with `error_type = collector_partial`. Retained container uptime and delayed
  scheduled work remain consistent with the host not executing during the due-time interval. The
  delay is not hidden, and no manual collection or replacement run was used.
- The corresponding incremental run is `afcb355c-e6f2-49e9-80e9-8ff639d615d3`, tagged
  `trigger = scheduled`. It persisted 44 immutable Raw responses, received 615 records, inserted 51
  Papers, updated 0 records, skipped 564 existing records, and persisted 0 ingestion errors. All 44
  Raw responses were HTTP 200; there were no HTTP 429 or ingestion-error rows.
- Persisted quality evidence again records two stale cursors and two failed mappings. The
  non-succeeded checkpoints identify the same `large_incremental_query` partials for Artificial
  Intelligence and Machine Learning. The zero-error HTTP result therefore remains distinct from
  complete data coverage, and both collector and scheduler correctly retained `partial`.
- Compared with Recovery Day 4, Raw decreased from 48 to 44, records received decreased from 1,199
  to 615, inserted Papers decreased from 374 to 51, and updated records decreased from 13 to 0.
  HTTP 200 responses decreased from 48 to 44, while HTTP 429 responses and persisted errors both
  remained at 0. The network path stayed clean, but the two cursor/mapping gaps remained.
- Cumulative arXiv evidence is now 652 Raw responses and 139 persisted ingestion errors. The error
  total again did not increase, and all earlier evidence remains immutable.

Recovery Day 5 is the fifth qualified scheduler-continuity execution in the new sequence, while
its delayed start and partial data outcome remain explicit. GitHub activity was not used in this
decision. No arXiv table, Research API semantic, Topic Match, or Raw observation was modified by
this review.

### Recovery Day 6 — 2026-08-23

Checked at `2026-08-23T12:21:42Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker container had remained up for
  approximately four days. Its retained log records run start at `06:07:38.810852Z`, completion at
  `06:09:43.197732Z`, status `partial`, and the next arXiv plan at
  `2026-08-24T02:00:00Z`.
- The persisted `2026-08-23T02:00:00Z` scheduler window transitioned to `running` at
  `06:07:38.785772Z`, approximately 4 hours 7 minutes 39 seconds late, and finished `partial` at
  `06:09:43.198169Z` with `error_type = collector_partial`. Retained container uptime and delayed
  scheduled work remain consistent with the host not executing during the due-time interval. The
  delay remains visible, and no manual collection or replacement run was used.
- The corresponding incremental run is `1114d533-da6f-44b2-a8fe-8ba48a1ed038`, tagged
  `trigger = scheduled`. It persisted 42 immutable Raw responses, received 130 records, inserted 0
  Papers, updated 0 records, skipped 130 existing records, and persisted 0 ingestion errors. All 42
  Raw responses were HTTP 200; there were no HTTP 429 or ingestion-error rows. Zero insertions are
  retained as a legitimate observed outcome rather than treated as missing collection.
- Persisted quality evidence continues to record two stale cursors and two failed mappings. The
  only non-succeeded checkpoints remain the `large_incremental_query` partials for Artificial
  Intelligence and Machine Learning. Clean HTTP execution and zero new Papers therefore do not
  imply complete data coverage, and both collector and scheduler correctly retained `partial`.
- Compared with Recovery Day 5, Raw decreased from 44 to 42, records received decreased from 615 to
  130, inserted Papers decreased from 51 to 0, and skipped records decreased from 564 to 130.
  Updated records, HTTP 429 responses, and persisted errors all remained at 0; HTTP 200 responses
  decreased from 44 to 42. The network path stayed clean, while the two cursor/mapping gaps
  remained.
- Cumulative arXiv evidence is now 694 Raw responses and 139 persisted ingestion errors. The error
  total again did not increase, and all earlier evidence remains immutable.

Recovery Day 6 is the sixth qualified scheduler-continuity execution in the new sequence, while
its delayed start and partial data outcome remain explicit. GitHub activity was not used in this
decision. No arXiv table, Research API semantic, Topic Match, or Raw observation was modified by
this review.

### Recovery Day 7 — 2026-08-24

Checked at `2026-08-24T12:22:01Z`, after the `02:00 UTC` scheduled window.

- Docker `db`, `api`, `web`, and `worker` were all healthy. The Worker container had remained up for
  approximately five days. Its retained log records the arXiv run start at
  `08:08:25.887789Z`, completion at `08:10:30.303335Z`, status `partial`, and the next arXiv plan at
  `2026-08-25T02:00:00Z`.
- The persisted `2026-08-24T02:00:00Z` scheduler window transitioned to `running` at
  `08:08:25.816291Z`, approximately 6 hours 8 minutes 26 seconds late, and finished `partial` at
  `08:10:30.303741Z` with `error_type = collector_partial`. Retained container uptime and delayed
  scheduled work remain consistent with the host not executing during the due-time interval. The
  delay remains visible, and no manual collection or replacement run was used.
- The corresponding incremental run is `fd78146c-c46e-42e6-83c7-230d77484925`, tagged
  `trigger = scheduled`. It persisted 42 immutable Raw responses, received 207 records, inserted
  164 Papers, updated 0 records, skipped 43 existing records, and persisted 0 ingestion errors. All
  42 Raw responses were HTTP 200, with 407 parsed entries and no parse errors; there were no HTTP
  429 or ingestion-error rows.
- Persisted quality evidence records two stale cursors and two failed mappings. The only
  non-succeeded incremental cursors remain the `large_incremental_query` partials for Artificial
  Intelligence and Machine Learning; the other 40 incremental cursors are `succeeded`. The
  separate Registry-coverage warning for 59 enabled Topics without an arXiv mapping also remains
  visible. Clean HTTP execution therefore does not imply complete source coverage.
- Compared with Recovery Day 6, Raw and HTTP 200 counts remained at 42, while records received
  increased from 130 to 207 and inserted Papers increased from 0 to 164. Skipped records decreased
  from 130 to 43; updated records, HTTP 429 responses, and persisted errors all remained at 0. The
  network path stayed clean, while the two cursor/mapping gaps remained.
- Cumulative arXiv evidence is now 736 Raw responses and 139 persisted ingestion errors. The error
  total again did not increase, and all earlier evidence remains immutable.

Recovery Day 7 is the seventh qualified scheduler-continuity execution in the new sequence, while
its delayed start and partial data outcome remain explicit. GitHub activity was not used in this
decision. No arXiv table, Research API semantic, Topic Match, or Raw observation was modified by
this review.

## Final recovery conclusion — 2026-08-24

The recovery scheduler-continuity gate **passed** for the real `2026-08-18T02:00:00Z` through
`2026-08-24T02:00:00Z` windows:

- PostgreSQL contains exactly seven consecutive scheduler windows and exactly one completed arXiv
  incremental ingestion run tagged `trigger = scheduled` for each UTC date.
- The seven persisted outcomes are one `succeeded` and six `partial`, with zero missing, duplicate,
  failed, or unfinished executions and no manual-run substitution.
- Each run has persisted Raw evidence and a terminal Worker outcome. Collector failures and quality
  gaps remain visible rather than being relabeled as scheduler success.

This pass is deliberately limited to scheduler continuity. It does **not** establish 02:00 UTC
punctuality: six recovery executions started late, including Day 7 by approximately 6 hours 8
minutes. It also does **not** establish complete arXiv coverage: six runs were partial, and the
Artificial Intelligence and Machine Learning `large_incremental_query` cursor gaps still require
separate operational remediation. The original `2026-08-12` through `2026-08-18` window remains
failed and is not repaired or superseded by this recovery result.

## E04.6 punctuality qualification — deployed 2026-08-25 UTC

E04.6 adds a separate, persisted-evidence punctuality contract without changing either soak
conclusion above. The original E03 window remains **failed**, and the recovery continuity window
remains **passed 7/7** with one succeeded and six partial collector outcomes. Six of those seven
recovery executions started more than five minutes late, so they are historical continuity
evidence, not post-deployment punctuality evidence.

The updated Worker became healthy at `2026-08-25T14:18:05.959095Z`. Its first complete
post-deployment contract window is therefore `2026-08-26T02:00:00Z`. Qualification requires three
consecutive real `arxiv_daily` scheduler windows, each starting no more than 300 seconds after its
persisted scheduled time, with no missing, duplicate, interrupted, or manual-substitution window.
At deployment the read-only verifier reported:

| Evidence                          | Result                 |
| --------------------------------- | ---------------------- |
| Recovery continuity               | `PASSED`, 7/7          |
| Punctuality qualification         | `PENDING`, 0/3         |
| Qualification threshold           | 300 seconds            |
| First / next qualification window | `2026-08-26T02:00:00Z` |
| On-time / late / missed           | 0 / 0 / 0              |
| Duplicate / interrupted           | 0 / 0                  |
| Records modified by verification  | 0                      |

The manual targeted arXiv validation runs `21237850-843c-4607-8158-cc463aee8bcc` and
`335f9ab1-7f46-4d97-b169-30c88ea2123d` are ingestion evidence only. They cannot satisfy, repair,
or replace a scheduler window. The project did not change the Windows power plan; host wake and
availability remain an operator/deployment responsibility. Future qualification evidence must be
appended from the actual scheduled windows and must remain `PENDING` or become `FAILED` unless all
three persisted windows genuinely meet the contract.
