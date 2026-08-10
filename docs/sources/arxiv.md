# arXiv Research source

## Why arXiv

arXiv is a durable public source of research metadata across computing and adjacent scientific
domains. Signal Observatory uses it as the first real Research observation source because Topic
Registry mappings can be translated into narrow, explainable metadata queries without collecting
PDFs or scraping human-facing pages.

The current implementation follows the official [arXiv API user manual](https://info.arxiv.org/help/api/user-manual.html)
and [API terms of use](https://info.arxiv.org/help/api/tou.html). It uses only
`https://export.arxiv.org/api/query` and Atom XML metadata.

## API now; OAI-PMH later if the strategy changes

E03 is selective and topic-driven: only active Topics with an explicit, enabled `arxiv` source
mapping are queried. The API is a good fit for that bounded discovery workload. The collector does
not implement a second OAI-PMH path in parallel.

The official [OAI-PMH documentation](https://info.arxiv.org/help/oa/index.html) describes the
bulk metadata harvesting interface. Reconsider OAI-PMH if the project moves from selective Topic
tracking to maintaining a substantial local arXiv metadata corpus. That would be a distinct
architecture decision and migration, not an automatic fallback inside this collector.

HTML search pages, abstract pages, PDF pages, and site listings are never scraped. E03 does not
download PDFs, TeX source, images, or full text.

## Request policy

- One arXiv connection is active at a time.
- The hard minimum interval is 3 seconds between request starts; configuration cannot lower it.
- Default page size is 100 and is configurable.
- Timeouts and retries are bounded.
- Only 429, 500, 502, 503, 504 and transient network failures are retried.
- Retry backoff still passes through the rate limiter and includes jitter.
- A 403 is persisted to Raw, stops the current run immediately, is not retried, and is exposed to
  operators.
- Per-run request, per-Topic result, page, and runtime limits stop gracefully with a durable
  checkpoint.

Configuration is centralized through `ARXIV_API_BASE_URL`,
`ARXIV_MIN_REQUEST_INTERVAL_SECONDS`, `ARXIV_REQUEST_TIMEOUT_SECONDS`, `ARXIV_PAGE_SIZE`,
`ARXIV_MAX_REQUESTS_PER_RUN`, `ARXIV_MAX_RESULTS_PER_TOPIC`,
`ARXIV_INCREMENTAL_OVERLAP_HOURS`, and `ARXIV_SCHEDULE`. The User-Agent identifies Signal
Observatory and its collector version; it does not imitate a browser.

## Topic mapping and match semantics

Registry YAML is the administrative source of truth. The collector uses only mappings where the
Topic is active, `source = arxiv`, and `enabled = true`. It never creates queries from aliases and
never rewrites a configured query based on observations.

`ArxivQueryBuilder` deterministically converts the explicit mapping into the API `search_query`.
A Topic match means only:

> the paper appeared in the result set for this exact Registry-configured arXiv API query.

The method is `ARXIV_API_QUERY`. Every match stores the matched query, Topic, source mapping,
first/last ingestion run, and timestamps. Paper-to-Topic is many-to-many; no semantic, embedding,
fuzzy, or LLM match is implied.

## Raw storage and provenance

Every HTTP response is written to `RawStore` before parsing or normalization, including empty,
error, and retry responses. The immutable payload is accompanied by requested-at time, request
parameters, query, pagination, sort, safe response headers, HTTP status, collector/schema versions,
and SHA-256 checksum. Parse failure records the error without removing Raw.

The relational `arxiv_raw_responses` index and `arxiv_paper_observations` lineage table connect a
Silver Paper back to the exact Raw response and ingestion run. Silver may represent the latest
known metadata, but its prior Raw observations remain immutable.

## Paper identity and normalization

Canonical arXiv identifiers are stored without a version suffix: `2401.12345` and
`2401.12345v2` are the same Paper. The latest observed version and current normalized metadata are
updated idempotently. Titles and abstracts receive whitespace normalization only; scientific text
is not lowercased, stemmed, or rewritten.

Authors are position-preserving relations, not a single text field. `normalized_name` supports
display-count consistency only and is not author identity resolution. Same-name people may be
different people. Primary and all arXiv category codes are preserved without recreating the arXiv
taxonomy.

## Backfill

`signal-observatory arxiv backfill` supports selected Topics or all active mappings, UTC date
ranges, dry-run, page size, and maximum pages. Default historical scope is bounded rather than
starting at arXiv's origin. Large result sets are recursively divided by submitted-date windows.
Each Topic/mapping/window has a resumable cursor with `next_start`.

Pagination follows `totalResults`, `startIndex`, and `itemsPerPage`; it does not infer completion
only from a short page. A completed cursor is skipped on an identical rerun. A partial cursor
resumes at its durable next page.

## Daily incremental collection

`signal-observatory arxiv collect` maintains a separate cursor for every mapping. A first run uses
the configured overlap relative to the current UTC time. Later runs query from the last successful
observation with the same configurable overlap so metadata updates, late changes, and boundary
conditions are re-observed safely. Silver idempotency absorbs overlap.

Cursor advancement occurs only after Raw and Silver persistence commit successfully. A failed
mapping keeps its safe checkpoint and does not prevent independent mappings from completing. The
minimal worker scheduler runs once daily by default; the manual CLI remains available.

## Read surfaces

- `signal-observatory arxiv status [--json]`
- `signal-observatory arxiv sample --topic SLUG --limit 20 [--json]`
- `GET /api/sources/arxiv/status`
- `GET /api/topics/{slug}/research`

The Topic Research endpoint reads Silver tables only. Counts are observation summaries, not trend
metrics. Publication windows are based on `published_at` in UTC. `unique_authors_30d` counts unique
normalized display names and must not be interpreted as resolved human identities.

## Data quality and known limitations

Runs record Raw/parsed counts, unique Papers, Topic matches, duplicate Paper observations, missing
author/category counts, parse errors, failed mappings, stale cursors, and active Topics without an
arXiv mapping. Operators review deterministic samples manually; the collector never changes the
Registry.

Known limitations:

- API phrase mappings can be broad or sparse and require human review.
- Recursive date-window planning cannot know final request count from dry-run alone because
  `totalResults` is available only after real responses.
- Current Paper rows represent the latest normalized state; Raw carries observation history.
- No author identity resolution, institutions, citations, full-text search, topic discovery, or
  semantic classification is implemented.
- No Research Score, Trend Score, momentum, acceleration, percentile, forecast, or predictive
  analytics exists in E03.
