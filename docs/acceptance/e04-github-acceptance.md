# E04 GitHub Developer Collector Acceptance

Evidence date: 2026-08-11 UTC

Result: **Not yet accepted — second real UTC-day Snapshot outstanding**

The authenticated discovery Pilot, manual mapping review, baseline Snapshot, same-day idempotency,
real API output, and browser rendering have passed. Final acceptance remains deliberately open
until a normal poll produces a second persisted observation date.

## Implementation

E04 implements the following path:

```text
Curated Topic
  -> enabled explicit GitHub mapping
  -> bounded official Repository Search
  -> immutable Raw HTTP response
  -> numeric Repository identity
  -> explainable many-to-many Topic match
  -> daily ETag Repository poll
  -> immutable forward-only Snapshot
  -> read-only Developer API
  -> truthful Developer Web surface
```

The authenticated client follows official `Link` pagination, separates Search and Core budgets,
honors `Retry-After` and reset timestamps, applies bounded secondary-limit backoff, and never stores
or emits the token. Missing auth yields `not_configured`; there is no anonymous high-volume
fallback. Discovery and Snapshot orchestration remain separate and reuse shared Raw storage and
ingestion lifecycles.

## Schema

Migration `20260811_0004_github_developer_collector.py` adds:

| Table                             | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `github_repositories`             | Numeric external identity and mutable current metadata |
| `github_raw_responses`            | Safe relational pointer to immutable Raw HTTP evidence |
| `github_repository_snapshots`     | Immutable Repository state per UTC observation date    |
| `github_topic_repository_matches` | Mapping, query, rank, run, and tracking evidence       |
| `github_repository_poll_states`   | ETag and safe last-poll state                          |
| `github_discovery_states`         | Per-mapping discovery checkpoint and status            |

An independent empty PostgreSQL database ran all migrations from E00 through E04, reached
`20260811_0004`, and contained 26 public tables. The temporary database was then deleted.

## Authentication

`GITHUB_TOKEN` is read only from an environment variable or deployment secret. The local API and
Worker now report `auth_configured: true`. Startup summaries, Raw metadata, logs, APIs, CLI output,
frontend types, and this report expose only that boolean—not the secret value. `.env` remains
ignored by Git.

## Discovery Pilot and mapping quality

Status: **Passed.** The bounded six-Topic Pilot succeeded, and its identical real-network rerun
created zero new Repository or Topic-match records. The initial run persisted 60 candidate
observations across 55 unique repositories, with 51 tracked and 4 retained as candidates. It made
six Search requests with no error or pause.

Manual review covered 30 persisted rows: 23 were Direct or Ecosystem matches, 7 were Broad or
tangential, and none were forks. Broad slash-like Search queries are explicitly documented for
later curated review; observations did not silently modify Registry YAML. See the
[GitHub Pilot report](../data/github-pilot-report.md).

## Snapshot

Status: **Baseline and same-day idempotency passed; later UTC date pending.**

Run `d839564c-0b69-4eec-9759-d7dc3b79e856` polled all 51 due tracked repositories, persisted 51 Raw
HTTP 200 responses, and created 51 immutable baseline Snapshots with no error or rate pause. The
immediate rerun `cfaa8aff-5900-4617-82eb-1b48ff2c6776` found zero due repositories and made zero
requests or writes.

Automated tests additionally cover baseline 200, rename continuity, same-day idempotency,
later-day equal values, changed values, 304-to-`conditional_304`, safe poll state, isolated 404 and
other errors, and no fabricated gaps. A real second observation date is still required.

## Rate limits

The two discovery runs used 12 Search requests and left 18 of 30. The baseline used 51 Core
requests and left 4949 of 5000. Operational counters recorded zero errors, zero rate pauses, and no
secondary-limit event.

Tests cover safe parsing of limit, remaining, used, reset, resource, and `Retry-After` headers;
separate Search/Core floors; primary exhaustion; secondary 403/429 classification; and bounded
retry.

## Idempotency and rename or transfer

- Numeric GitHub Repository ID is unique; `full_name` is mutable.
- A rename or transfer updates current identity and preserves prior Snapshot names.
- Repeated discovery updates one match instead of duplicating Repository identity.
- The same Repository and UTC date yields one Snapshot; equal values on a later date remain a new
  observation.
- Poll state advances only after Raw and Snapshot persistence succeed.

## Provenance

Every received response is written to immutable Raw storage before parsing or status handling. The
DB index records endpoint, safe URL hash and parameters, Repository ID where applicable, status,
ETag, Last-Modified, actual rate headers, Retry-After, collector and schema versions, checksum, and
Raw path. Topic-match evidence records mapping, exact query, rank, run, and Raw checksum.

Verified lineage for Repository ID `960665821`, `microsoft/mcp-for-beginners`, connects its
discovery match and Search Raw checksum to the Repository, the 2026-08-11 `full_200` Snapshot, Raw
checksum, and baseline run. Across the Pilot, 63 immutable Raw responses were persisted: 12 Search
and 51 Repository responses.

## API and Web

- `GET /api/sources/github/status` reports healthy authenticated collection, 51 tracked
  repositories, and 51 snapshots.
- `GET /api/topics/{slug}/development` returns persisted metrics, repositories, and match evidence.
- Model Context Protocol renders 9 tracked repositories, 80,511 stars, 14,015 forks, and 7 pushed
  in 30 days. Baseline-only deltas are correctly absent.
- Homepage Research and Developer stages use independent persisted collector truth.
- Topic Developer supports not-configured, not-initialized, live, degraded, zero-data, and localized
  API-error states.
- Browser acceptance passed `/`, `/topics`, and `/topics/model-context-protocol`, including five
  real Repository links and evidence sections, with zero console warnings or errors.
- Hacker News Community and Wikipedia Public remain Not collecting.

The homepage currently shows the global arXiv Research collector as Degraded because its latest
operational run was partial; the Topic Research panel still renders persisted live data. This is
truthful E03 operational state, not an E04 regression.

## Tests and quality gate

| Gate                                 | Result                                           |
| ------------------------------------ | ------------------------------------------------ |
| `python -m ruff check .`             | Passed                                           |
| `python -m ruff format --check .`    | Passed                                           |
| `python -m mypy apps packages db`    | Passed                                           |
| `python -m pytest`                   | 128 passed, 1 skipped                            |
| `npm run lint`                       | Passed                                           |
| `npm run typecheck`                  | Passed                                           |
| `npm run test`                       | 29 passed                                        |
| `npm run build`                      | Passed                                           |
| Empty PostgreSQL migration           | Passed at `20260811_0004`, 26 tables             |
| Docker Compose config/build/health   | Passed; db, api, worker, and web healthy         |
| Authenticated dry-run                | Passed; configured auth, zero network and writes |
| Real discovery and identical rerun   | Passed                                           |
| Baseline and same-day Snapshot rerun | Passed                                           |
| Browser Developer-live acceptance    | Passed                                           |
| Second real UTC-day Snapshot         | **Pending**                                      |

## Outstanding acceptance gate

1. After the normal due interval and on a later UTC date, run the Snapshot collector.
2. Confirm a second immutable point, changed and unchanged handling, Core budget, and error or pause
   counters from persisted evidence.
3. Re-run the required quality gates if code changes occur, update the Pilot report, and change this
   result to **Accepted** only if every E04 definition-of-done item passes.

No clock manipulation, manual database insertion, interpolation, or fabricated backfill may satisfy
this gate.

## Known limitations

- GitHub history begins when Signal Observatory first observes a Repository.
- Missing daily Snapshots remain missing; no interpolation or backfill is fabricated.
- Research and Developer have persisted data. Research's global operational health is currently
  degraded while the E03 seven-day scheduler soak remains in progress.
- Community and Public are not collecting.
- There is no Trend Score, Developer Score, momentum, acceleration, forecast, or cross-source
  analysis yet.
- There is no individual Stargazer history, user profiling, contributor graph, detailed
  commit/PR/issue analytics, code search, cloning, or source-code analysis.

## Next recommended Epic

After—and only after—this report becomes **Accepted**, the next recommendation is **E05 — Hacker
News Community Collector**. No E05 code is implemented here.
