# GitHub Developer source

## Scope and official interface

E04 observes public Repository metadata through the official GitHub REST API only. Discovery uses
Repository Search; polling uses Repository endpoints. It never scrapes human-facing HTML, clones
repositories, queries code search, or collects users, individual Stargazers, contributors, commit
history, pull requests, or issue analytics.

The client sends `Accept: application/vnd.github+json`, `Authorization: Bearer ...`, a configured
`X-GitHub-Api-Version`, and the Signal Observatory User-Agent. GitHub documents REST API
[versioning](https://docs.github.com/en/rest/about-the-rest-api/api-versions),
[Link-header pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api),
[conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api),
and [rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

## Authentication

Set `GITHUB_TOKEN` in the local `.env` file or deployment secret store. The token only needs read
access to public Repository metadata; no write permission is required. The value is excluded from
Raw metadata, structured logs, startup summaries, API responses, CLI output, and the Web bundle.
An empty or missing value yields `collector_state = not_configured`. High-volume anonymous
fallback is disabled by default.

```powershell
Copy-Item .env.example .env
# Edit .env and set GITHUB_TOKEN without committing it.
docker compose up -d --build
docker compose exec api signal-observatory github status --json
```

`.env` is ignored by Git. Use a fine-grained personal access token without repository write
permissions, or an equivalent deployment secret. Revoke and replace any token that is ever pasted
into a terminal transcript, issue, log, or tracked file.

## Discovery

Only active Topics with an explicit enabled GitHub mapping are eligible. The deterministic query
builder reads `configuration.search_queries`; it does not inspect aliases or invent terms. Results
are ordered by the official API's star sort and bounded by per-mapping results, per-run request,
rate-budget, and runtime limits. Pagination follows the returned `Link` header.

```powershell
docker compose exec api signal-observatory github discover --topic model-context-protocol --dry-run --json
docker compose exec api signal-observatory github discover --topic model-context-protocol --max-results 10 --max-requests 5 --json
docker compose exec api signal-observatory github sample --topic model-context-protocol --limit 20 --json
```

A match means only that a Repository appeared for the configured query. Evidence records the
Topic, source mapping, exact query, API rank, discovery run, and Raw checksum. Numeric Repository
ID deduplicates renamed/transferred entities and supports Topic-to-Repository many-to-many.

## Daily snapshots

Discovery and snapshotting are independent. The first successful poll is the baseline; later
polls append one immutable row per UTC date. ETag/`If-None-Match` is enabled by default. A 304
creates a daily `conditional_304` point from the prior state, while a missed poll remains absent.

```powershell
docker compose exec api signal-observatory github snapshot --topic model-context-protocol --dry-run --json
docker compose exec api signal-observatory github snapshot --topic model-context-protocol --json
```

The Worker schedules snapshots daily at `02:30 UTC` and discovery weekly at `03:00 UTC` Sunday by
default. It serializes collectors with a shared lock and checks wall time frequently so host sleep
does not strand a long monotonic timer. Manual CLI runs remain available.

## Raw, rate limits, and failure safety

Every received response, including 304, 403, 404, 429, and retry responses, reaches immutable Raw
before parsing/status handling. The relational Raw index stores only safe request metadata,
response headers, checksum, and filesystem pointer—never Authorization.

Actual response headers drive separate Search/Core budgets. `Retry-After` is honored; zero
remaining waits for reset; suspected secondary limits use bounded backoff and stop rapid retries.
The default request concurrency is one. A mapping or Repository failure is recorded independently
and cannot modify arXiv evidence.

## Read surfaces and limitations

- `signal-observatory github status --json`
- `signal-observatory github sample --topic SLUG --limit 20 --json`
- `GET /api/sources/github/status`
- `GET /api/topics/{slug}/development`

Developer counts and deltas are direct summaries of persisted snapshots, not scores. There is no
history before the Observatory's first observation, no inferred missing day, no Trend Score, and
no user/contributor analytics. Mapping quality requires human review and Registry changes remain a
separate curated process.
