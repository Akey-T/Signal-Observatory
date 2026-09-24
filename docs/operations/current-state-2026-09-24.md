# Current runtime evidence — 2026-09-24 UTC

Evidence captured at approximately `2026-09-24T02:15Z` for plan P0-A. This is a current-state
snapshot, not a revision of historical acceptance. All commands below were read-only; no collector
was run and no database, Registry, Raw, or scheduler record was modified.

## Code, schema, and services

| Check                                | Result                                                                |
| ------------------------------------ | --------------------------------------------------------------------- |
| Branch / HEAD / `origin/main`        | `main` / `9f77a4d3d23860e5edb9f23820465f249f424267` / same            |
| Worktree                             | Only owner-provided, untracked `CODEX_PLAN.md` at start of inspection |
| Tracked runtime paths                | Only `data/raw/.gitkeep`; no tracked `.env` or `data/backups/` path   |
| `git diff --check`                   | Passed                                                                |
| Alembic current / sole head          | `20260913_0009` / `20260913_0009`                                     |
| `alembic check`                      | No new upgrade operations detected                                    |
| `docker compose config --quiet`      | Passed                                                                |
| Compose `db`, `api`, `worker`, `web` | All healthy                                                           |

## Data and verification

| Check                    | Current result                                                                                             |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Operations               | `degraded`; Research healthy, Developer degraded                                                           |
| Raw integrity            | Sample 100/100 pass; 5,266 persisted responses available; 0 failures; 0 modified                           |
| arXiv                    | Latest scheduled 2026-09-24 run succeeded; 42 mappings, 17,983 papers, 56 Raw responses, 0 last-run errors |
| arXiv cursors            | 42/42 parent cursors succeeded; 12 partition children; 4 unexplained historical child-root anomalies       |
| arXiv durability checks  | 0 without durable run, 0 without intact Raw, 0 advanced past failure                                       |
| GitHub                   | Latest 2026-09-23 run partial with 1 error; 510 tracked repositories, 2,753 snapshots, 33 dates            |
| GitHub cross-day         | Passed; 0 Raw, fabricated-date, delta, or poll-state mismatches; 0 modified                                |
| Scheduler continuity     | Failed: 7/7 rows present, 0 missing/duplicates, 1 missed or interrupted                                    |
| Scheduler punctuality v1 | Failed: 3 terminal qualification windows, 0 on time, 3 late                                                |
| Latest backup            | `20260819T110243Z-97d468`, verified; migration head `20260813_0007`                                        |

The four arXiv anomalies remain the two child cursors under each of mapping IDs
`7c2e1c1c-c965-4e19-b763-4abc7c0749e0` and
`88573826-56a1-4d80-8a0d-97f2bc30a936`. Their cursor IDs are
`d765b270-b193-497b-b4a8-6e825f3f88b3`,
`9afc03bf-e10b-4b10-85ac-1fcd71ea1e1d`,
`5394a23b-91a2-41c4-89ca-9af9fcc9f360`, and
`6d7a216f-8d83-43d1-a41b-ff924dab5e44`. The current verifier reports
`unexplained_cursor_state = 4` and `modified_records = 0`.

The earlier phase report recorded 41 succeeded and 1 failed parent cursor. The current 42/42
succeeded state is newer operational evidence; it does not remove the four historical child
lineage anomalies. The latest backup remains behind the current schema and is not a current
recovery point.
