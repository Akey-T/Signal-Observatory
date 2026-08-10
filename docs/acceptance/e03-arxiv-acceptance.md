# E03 arXiv Research Collector Acceptance

Acceptance date: 2026-08-10 UTC
Result: **Accepted**

## Implementation

E03 activates the first real Signal Observatory observation channel from explicit curated Topic
mappings to persisted Research evidence:

```text
Curated Topic
  → enabled arXiv mapping
  → deterministic query
  → official arXiv API
  → immutable Raw response
  → Atom parse and normalization
  → Silver Paper/Author/Category
  → explainable Topic match
  → resumable backfill or incremental cursor
  → read-only Research API
  → truthful Topic Research UI
```

Implemented modules include:

- `collectors/arxiv/`: query builder, single-connection API client, rate limiter, bounded retry,
  Atom parser, persistence, backfill/incremental orchestration, status, data quality, and sampling;
- `db/`: arXiv models and Alembic migration;
- `apps/cli/`: `arxiv status`, `backfill`, `collect`, and `sample`, including JSON output;
- `apps/worker/`: validated minimal daily UTC schedule with manual CLI retained;
- `apps/api/`: source status and per-Topic Research endpoints;
- `apps/web/`: live/not-initialized/degraded/zero/error states, counts, latest papers, and homepage
  collector status.

The client uses only the official metadata API. It never scrapes HTML, bypasses controls, downloads
PDF/full text, or uses LLM/embedding classification. Every received HTTP response is persisted to
Raw before parser or status handling. A 403 is preserved and stops the current run without retry.

## Schema

Migration `20260810_0003_arxiv_research_collector.py` adds:

| Table                      | Purpose                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| `arxiv_papers`             | Canonical version-independent Paper and latest Silver metadata       |
| `arxiv_authors`            | Per-Paper display/normalized author rows without identity resolution |
| `arxiv_paper_authors`      | Ordered Paper/Author relation                                        |
| `arxiv_categories`         | Observed arXiv category code                                         |
| `arxiv_paper_categories`   | Primary/all Paper category relations                                 |
| `arxiv_topic_matches`      | Many-to-many, query-explainable Topic membership                     |
| `arxiv_collection_cursors` | Per-mapping backfill windows and incremental cursor                  |
| `arxiv_raw_responses`      | Request/HTTP/checksum index over immutable Raw                       |
| `arxiv_paper_observations` | Paper → run → exact Raw lineage                                      |

Canonical `arxiv_id` is unique and excludes `vN`; later versions update Silver without replacing
prior Raw. Indexes cover identifier, publication/update time, Topic/Paper, mapping, and Raw lookup.

An independent empty PostgreSQL database named
`signal_observatory_e03_acceptance_20260810` was created for acceptance. `alembic upgrade head`
ran all migrations from zero:

```text
20260809_0001 → 20260809_0002 → 20260810_0003
head: 20260810_0003
public tables: 20
```

## Collection

The controlled Pilot backfill used five enabled Registry mappings from 2026-07-01 through
2026-08-10 inclusive with page size 10 and one page per derived window.

Primary run: `3096b25e-408d-49ad-9010-608e331434d7`

| Measure                                      |                              Result |
| -------------------------------------------- | ----------------------------------: |
| Topics                                       |                                   5 |
| API requests / primary Raw responses         |                                  19 |
| Raw responses with HTTP 200                  |                                  19 |
| Feed entries present in Raw                  |                                 174 |
| Entries normalized after large-window probes |                                 104 |
| Unique Papers                                |                                 104 |
| Topic matches                                |                                 104 |
| Errors / parse errors                        |                               0 / 0 |
| Runtime                                      |                        54.8 seconds |
| Primary status                               | `partial` due intentional page caps |

Topic results were 80 Artificial Intelligence, 10 Model Context Protocol, 10
Retrieval-Augmented Generation, 3 Site Reliability Engineering, and 1 Data Lakehouse. Two sparse
mappings completed; three high-volume/page-capped mappings retained resumable partial cursors.

The broad Artificial Intelligence query triggered recursive date partitioning, increasing real
requests beyond the five initial dry-run windows. This was safe and bounded but establishes that
dry-run request estimates are lower bounds when remote `totalResults` causes partitioning.

A later incremental smoke run for `model-context-protocol` used one official API request over the
default 48-hour overlap. It received zero Papers, preserved one Raw response, succeeded, and made
the Topic truthfully live while retaining its 10 historical Papers. After that run the local Raw
store contained 20 payloads, 20 metadata sidecars, and `.gitkeep` (174,076 bytes total).

## Idempotency

Run `856428ae-2cc0-4cdb-8a1e-891f39965c79` repeated the identical range for the two completed
Pilot mappings. Completed cursors were skipped with:

```text
API requests: 0
Raw payloads: 0
Papers inserted/updated: 0/0
Topic matches added: 0
status: succeeded
```

Automated persistence tests also cover the same Paper on a second run, version updates, ordered
authors, categories, repeated Topic matches, and one Paper matching two Topics. The Pilot's 104
normalized entries produced 104 canonical Papers, so normalized duplicate ratio was 0%.

## Resume and safety

- Backfill cursors are per Topic/mapping/date window and retain `next_start`.
- Incremental cursors are per mapping and retain the failed/partial window for exact resume.
- A new successful incremental window resets pagination to `start=0`; a regression assertion
  verifies the first and second successful daily runs both start at zero.
- Cursor success advances only after Raw and Silver commits.
- Interrupted-run tests verify a persisted first page resumes at the next page.
- Partial failure in one mapping does not discard successful mappings.
- Retry attempts, including received transient failures and network attempts, count against the
  run request limit.
- Result limits apply across all windows for a Topic, and runtime is checked between pages and
  retries.
- 403 handling stops the run after one preserved response and does not retry.

## Data quality

The primary run had 19/19 HTTP 200 responses, no parse errors, no ingestion errors, and no Paper
missing required author/category relations. Large-query parent responses remain in Raw even though
their entries are not normalized before narrower windows are processed.

Twenty matched Papers were manually reviewed with title, abstract preview, matched query, Topic,
mapping ID, ingestion run, and Raw checksum. No clear false positive was found. One Artificial
Intelligence paper was marked borderline because the mapping is intentionally broad; SRE samples
were relevant but included adjacent incident-diagnosis work. MCP and RAG appeared precise, and
Data Lakehouse was sparse and precise. No Registry mapping was changed automatically.

Full findings and the exact 20-paper list are in
[the Pilot report](../data/arxiv-pilot-report.md).

## API

New endpoints:

- `GET /api/sources/arxiv/status`
- `GET /api/topics/{slug}/research?limit=5`

The Research endpoint reads Silver data only and distinguishes `not_configured`,
`not_initialized`, `live`, and `degraded`. It exposes total/7-day/30-day Paper counts,
30-day unique normalized display-author names, last observation time, latest Papers, official arXiv
links, and mapping/run/Raw provenance. Publication windows use UTC `published_at`; the author count
is not human identity resolution.

Live API smoke result:

```text
health: healthy
collector: healthy / last run succeeded
papers observed: 104
site-reliability-engineering: live
topic papers: 3 total / 1 in 30 days / 3 latest returned
Topic Registry: 101 topics
```

Unknown Topic, no mapping, never collected, live zero, live with Papers, degraded history, and
full API → Paper → match → mapping → run → Raw lineage are covered by tests.

## Web

Topic Detail now treats only Research/arXiv as an implemented observation channel:

- explicit mapping without a successful cursor: Not collecting / not initialized;
- successful cursor, including zero results: Live;
- failed latest cursor with history: Degraded with history retained;
- Research API failure: only the Research surface becomes Unavailable;
- GitHub, Hacker News, and Wikipedia remain Not collecting when configured;
- latest Papers show title, ordered authors, publication date, primary category, abstract preview,
  and official arXiv link.

Homepage Research becomes Live only when source status has a healthy successful run. Featured
Topics still use editorial priority and category diversity, never Paper counts. Registry health and
collector state are displayed separately. A browser-found stale E02 footer/status claim was removed
and covered by a regression test.

Browser acceptance:

| Route                            | Verified                                                                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/`                              | Research/arXiv Live; other three configured/ready; Registry and collector state separated; no stale contradictory claim                                |
| `/topics`                        | 101 Topics, filters, first 24 results, pagination, and original Explorer behavior                                                                      |
| `/topics/model-context-protocol` | Research Live; 0/1 Paper counts for 7d/30d; 3 display authors in 30d; 10 total persisted Papers; latest 5 links; exactly three Not collecting channels |

All three routes produced zero browser Console warnings or errors. The desktop visual layout was
inspected for the Topic header, mappings, identity/registry panels, four observation cards, metrics,
and latest-paper list.

## Tests

Final automated results:

```text
Python:   98 passed, 1 skipped (standard run only; PostgreSQL URL unset)
Postgres: 4 passed (explicit connection + key arXiv persistence/lineage integration)
Frontend: 22 passed
```

The fixture suite includes single/multiple/empty/paginated/updated/missing-optional/malformed/API
error Atom feeds. Network access is not required in CI.

## Quality gate

| Gate                                      | Result                                                           |
| ----------------------------------------- | ---------------------------------------------------------------- |
| `ruff check .`                            | passed                                                           |
| `ruff format --check .`                   | passed                                                           |
| `mypy apps packages config db collectors` | passed                                                           |
| `pytest`                                  | passed                                                           |
| `npm run lint`                            | passed                                                           |
| `npm run format:check`                    | passed                                                           |
| `npm run typecheck`                       | passed                                                           |
| `npm run test`                            | passed                                                           |
| `npm run build`                           | passed                                                           |
| `docker compose config --quiet`           | passed                                                           |
| Docker image rebuild                      | passed                                                           |
| Docker Compose health                     | db/api/worker/web healthy                                        |
| Empty PostgreSQL migration                | passed at `20260810_0003`                                        |
| API smoke                                 | passed                                                           |
| Browser smoke and Console                 | passed                                                           |
| Core TODO/stub audit                      | no E03 stub; only intentional worker signal/timeout control flow |

## Known limitations

- Only Research/arXiv is live. GitHub, Hacker News, and Wikipedia are not collecting.
- No Trend Score, Research Score, momentum, acceleration, z-score, percentile, forecast, breakout
  detection, or predictive analytics exists.
- Counts are observation summaries, not popularity or trend strength.
- Broad API phrase mappings can require recursive date windows and continued human review.
- Dry-run cannot know remote `totalResults`, so partition-related request estimates are lower
  bounds.
- The Pilot intentionally left three historical backfills partial at safe checkpoints.
- No OAI-PMH mirror, PDF/full text, citation graph, full-text index, author identity resolution,
  institution analysis, semantic matching, embeddings, LLM classification, or Topic discovery is
  implemented.
- Local filesystem Raw storage and the minimal in-process daily scheduler are appropriate for the
  current single-host scope; no cloud or distributed infrastructure was added.

## Next recommended Epic

**E04 — GitHub Developer Collector.**

E04 should activate the existing explicit GitHub mappings with the same Raw-first, idempotent,
cursor-safe, explainable approach. It should not alter E03 Research evidence or introduce trend
scores prematurely.
