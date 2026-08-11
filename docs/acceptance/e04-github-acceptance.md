# E04 GitHub Developer Collector Acceptance

Acceptance date: Pending
Result: **Not yet accepted — authenticated Pilot and forward-time evidence outstanding**

## Implementation

E04 implements the code path:

```text
Curated Topic
  → enabled explicit GitHub mapping
  → bounded official Repository Search
  → immutable Raw HTTP response
  → numeric Repository identity
  → explainable many-to-many Topic match
  → daily ETag Repository poll
  → immutable forward-only Snapshot
  → read-only Developer API
  → truthful Developer Web surface
```

The client is authenticated by default, follows redirects and official Link pagination, separates
Search/Core budgets, honors Retry-After/reset, applies bounded secondary-limit backoff, and never
stores or emits the token. Missing auth yields `not_configured`; no anonymous high-volume fallback
occurs. Discovery and Snapshot orchestration are separate and reuse the shared RawStore and
ingestion lifecycle.

## Schema

Migration `20260811_0004_github_developer_collector.py` adds:

| Table                             | Purpose                                                  |
| --------------------------------- | -------------------------------------------------------- |
| `github_repositories`             | Numeric external identity and mutable current metadata   |
| `github_raw_responses`            | Safe relational pointer to immutable Raw HTTP evidence   |
| `github_repository_snapshots`     | Immutable Repository state per UTC observation date      |
| `github_topic_repository_matches` | Mapping/query/rank/run explainability and tracking state |
| `github_repository_poll_states`   | ETag and safe last-poll state                            |
| `github_discovery_states`         | Per-mapping discovery checkpoint/status                  |

An independent empty PostgreSQL database ran every migration from E00 through E04 and reached
`20260811_0004` with 26 public tables. The exact temporary database was then deleted.

## Authentication

`GITHUB_TOKEN` is read only from environment or a deployment secret. The API/Worker Compose
services receive it at runtime; blank interpolation normalizes to missing auth. Startup summaries,
Raw metadata, logs, APIs, CLI output, and frontend types expose only `auth_configured: boolean`.
The local acceptance environment currently reports `false`, so no real request is claimed.

## Discovery Pilot and mapping quality

Status: **Pending.** See [GitHub Pilot report](../data/github-pilot-report.md). The final acceptance
requires 5–10 Topics, bounded discovery, an idempotent rerun, and manual review of at least 30 real
persisted candidates. Fixture responses are test evidence, not a real-network Pilot.

## Snapshot

Automated tests prove baseline 200, rename continuity, same-day idempotency, later-day equal-value
snapshots, changed values, 304-to-`conditional_304`, safe poll state, 404/error isolation, and no
fabricated gap. Operational baseline and a second real UTC-day Snapshot remain pending.

## Rate limits

Fixture tests prove safe parsing of limit, remaining, used, reset, resource and Retry-After headers;
separate Search/Core floors; primary exhaustion handling; secondary 403/429 classification; and
bounded retry. Real Pilot budgets, pauses, and secondary-limit event counts remain pending.

## Idempotency and rename/transfer

- Numeric GitHub Repository ID is unique; `full_name` is mutable.
- A rename/transfer updates current identity and preserves prior snapshot names.
- Repeated discovery updates one match instead of duplicating Repository identity.
- Same Repository/date yields one snapshot; the same values on a later date remain a new point.
- Poll state advances only after Raw and Snapshot persistence succeed.

## Provenance

Every received response is written to unified immutable Raw before parse/status handling. The DB
index records endpoint, safe URL hash/parameters, Repository ID where applicable, status, ETag,
Last-Modified, actual rate headers, Retry-After, collector/schema versions, checksum, and Raw path.
Topic match evidence records mapping, exact query, rank, run, and Raw checksum. A real end-to-end
lineage example will be inserted after the Pilot.

## API and Web

- `GET /api/sources/github/status`
- `GET /api/topics/{slug}/development`
- Homepage Research/Developer stages use independent persisted collector truth.
- Topic Developer has not-configured, not-initialized, live, degraded, zero-data, and localized
  API-error states.
- Live history shows Repository/star/fork/pushed-30d summaries, snapshot deltas, 5 Repository links,
  and match evidence.
- Research behavior is unchanged; Hacker News and Wikipedia remain Not collecting.

Current browser preflight passed `/`, `/topics`, and `/topics/model-context-protocol`, with 24
Explorer cards, live persisted Topic Research, GitHub truthfully Not collecting, and zero console
warnings/errors. Developer Live and real Repository rendering remain pending authenticated data.

## Tests and quality gate

| Gate                                      | Result                                                         |
| ----------------------------------------- | -------------------------------------------------------------- |
| `ruff check .`                            | Passed                                                         |
| `ruff format --check .`                   | Passed                                                         |
| `mypy apps packages config db collectors` | Passed                                                         |
| `pytest`                                  | 128 passed, 1 skipped (PostgreSQL URL not set in standard run) |
| frontend lint                             | Passed                                                         |
| frontend format                           | Passed                                                         |
| frontend typecheck                        | Passed                                                         |
| frontend tests                            | 29 passed                                                      |
| frontend build                            | Passed                                                         |
| empty PostgreSQL migration                | Passed at `20260811_0004`, 26 tables                           |
| Docker Compose config/build/health        | Passed; db/api/worker/web healthy                              |
| API/CLI no-auth smoke                     | Passed; `not_configured`, dry-run zero writes                  |
| Browser preflight                         | Passed; operational Developer-live check pending               |
| Core TODO/stub audit                      | No E04 stub; only expected Windows signal fallback             |

## Outstanding acceptance gates

1. Operator configures a protected `GITHUB_TOKEN`.
2. Run the bounded 6-Topic discovery Pilot and its identical idempotency rerun.
3. Manually review and document at least 30 persisted Repository candidates.
4. Record the baseline and a second real Snapshot on a later UTC date.
5. Capture real Search/Core budgets, DQ records, and one full lineage example.
6. Re-run API and browser acceptance with Developer truthfully Live.
7. Replace this pending result with Accepted only if every E04 definition-of-done item passes.

## Known limitations

- No GitHub history exists before Signal Observatory first observes a Repository.
- Missing daily Snapshots remain missing; no interpolation or backfill is fabricated.
- Only Research can currently be called live in this environment; Developer waits for the
  authenticated Pilot. Community and Public are not collecting.
- No Trend Score, Developer Score, momentum, acceleration, forecast, or cross-source analysis.
- No individual Stargazer history, user profiling, contributor graph, detailed commit/PR/issue
  analytics, code search, cloning, or source-code analysis.

## Next recommended Epic

After—and only after—this report becomes **Accepted**, the next recommendation is **E05 — Hacker
News Community Collector**. No E05 code is implemented here.
