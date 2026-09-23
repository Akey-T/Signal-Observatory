# Signal Observatory — E05 Attention Domain Foundation Acceptance

Evidence date: 2026-09-07

## Result

**Accepted — source-neutral domain foundation only; no external collector is enabled.**

E05 establishes the vocabulary and minimal persistence needed by future Public Attention sources.
It does not collect GDELT, Wikipedia, Google Trends, Reddit, Hacker News, or news-site data. E06
GDELT remains implementation-not-started after this acceptance.

## Dependency and scope

E05 was implemented after the E06 dependency review identified the missing Attention Domain
Foundation. The existing Technology Observatory (arXiv Research and GitHub Developer), Registry,
Raw, Ingestion, Coverage, Scheduler, Operations, and backup boundaries remain unchanged in meaning.

There were zero external source/API collector requests and zero new Raw external observations
during E05. All domain tests use synthetic records or fixtures; packaging setup is not counted as
source collection evidence.

## Domain decisions

| Concept           | E05 decision                                                                             |
| ----------------- | ---------------------------------------------------------------------------------------- |
| Topic             | Reuse curated Topic Registry; no new Topic management system                             |
| Source            | Reuse existing `sources` identity                                                        |
| Attention Channel | `MEDIA`, `SEARCH`, `COMMUNITY`, `REFERENCE`; no `PUBLIC_CONCERN`                         |
| Entity            | `CanonicalEntity` contract-only; no persistence or automatic resolution                  |
| Event             | `CanonicalEvent` and review-only `EventCandidate` contracts; no detection/clustering     |
| Document          | Persisted source-local `AttentionDocument`, no generic full-text field                   |
| Observation       | Persisted measured `AttentionObservation` over a UTC window                              |
| Evidence          | Persisted role-labelled `ObservationEvidence` relation to sampled Documents              |
| Metrics           | Explicit name, unit, description, and definition version; no Trend/Public Concern scores |
| Coverage          | Reuse shared `CoverageStrategy`; source adapter declares window semantics                |

The implementation deliberately persists only the minimum E06-ready scope:

```text
attention_documents
attention_observations
attention_observation_evidence
```

No `attention_entities`, `attention_events`, graph database, vector store, or LLM extraction path
was created.

## Persistence and invariants

- `(source_id, source_document_key)` is the source-local Document identity.
- Observation identity includes Topic, Source, Source Mapping, Channel, metric, and both UTC window
  boundaries; duplicate logical intervals are rejected.
- `window_end > window_start` and UTC-aware timestamps are enforced.
- Evidence relations are unique by Observation, Document, and role; one Observation can have zero or
  many Evidence rows, and one Document can support multiple Topics/Observations.
- A measured zero is valid and distinct from a missing Observation row; nullable is not silently
  converted to zero.
- Observation provenance reserves Source Mapping and optional Ingestion Run foreign keys. A later
  source collector must connect its Observation and Document evidence to immutable Raw through its
  own source-specific Raw index.
- Document, Observation, and Evidence persistence helpers are idempotent and update existing
  logical records instead of duplicating them.
- Persistence rejects a Document/Source name mismatch, an Observation/Source Mapping mismatch,
  cross-source Ingestion Run lineage, and cross-source Evidence links.
- An out-of-order replay can correct the earliest observed timestamp but cannot overwrite fields
  from a newer Document or Observation; non-finite numeric measurements are rejected.

## Contract boundaries

`AttentionMetricDefinition` validates units and definition versions and rejects analytical score
names outside E05. `AttentionSourceAdapter` declares Source, Channel, metric definitions, coverage,
evidence semantics, and source-local document identity without performing network or database work.
Its coverage contract includes expected-window semantics plus observed, missing, and partial UTC windows.
`CanonicalEvent`
rejects system-candidate promotion; canonical Events must be curated. Canonical Entities and Topics
cannot be created by observed text or collectors.

The full semantic boundaries are documented in:

- [`domain-model.md`](../attention/domain-model.md)
- [`observation-semantics.md`](../attention/observation-semantics.md)
- [`event-entity-boundaries.md`](../attention/event-entity-boundaries.md)
- [`ADR-023`](../adr/ADR-023-attention-domain-foundation.md) through [`ADR-026`](../adr/ADR-026-event-entity-canonicalization-deferred.md)

## Migration evidence

Previous Alembic head: `20260813_0007`

New E05 migration: `20260907_0008`

New tables: `attention_documents`, `attention_observations`, `attention_observation_evidence`

The fresh migration chain reaches the new head without using `create_all()` as a migration
substitute. Existing historical migrations were not modified. The final quality gate records both
fresh-chain migration results and the deployed PostgreSQL head.

## Boundary and persistence tests

The test suite covers:

- distinct Topic/Entity/Event/Document/Observation concepts;
- four Attention Channels and rejection of Public Concern/Trend analytical metrics;
- metric units, definition versions, UTC normalization, and invalid windows;
- curated-only canonical Event creation;
- existing CoverageStrategy reuse;
- zero versus missing semantics;
- same-window idempotent Document and Observation upserts;
- stale replay protection and finite numeric values;
- Source, Source Mapping, Ingestion Run, and Evidence lineage consistency;
- many-to-many Observation–Document evidence links and duplicate relation prevention;
- ingestion-run provenance fields and no Event/Entity tables;
- fresh Alembic migration chain and downgrade.

No test creates or promotes an Event, Entity, or Topic from a Document. No test performs a network
call.

## E04.6 operational dependency evidence

E04.6 punctuality does not block E05 domain implementation. It does block future E06 production
scheduling. On 2026-09-07, the following read-only commands were run at handoff time; E05 did not
modify scheduler history:

```powershell
signal-observatory scheduler status --json
signal-observatory scheduler verify-punctuality --json
```

Observed result: `FAIL` (both commands). Continuity remains `passed` at 7/7 with no missing or
duplicate windows, while the separate punctuality qualification is `completed=3`,
`on_time=0`, `late=3`, `missed=0`; therefore its timing contract is not satisfied. The latest
execution is still a future `scheduled`/`pending` record for 2026-09-08 02:00 UTC. Manual
collection cannot satisfy this gate, and E06 production scheduling remains blocked until a new
qualification window passes.

Docker health was not claimable in this handoff: the local Docker Engine returned a named-pipe
permission error, and the required escalated Compose verification was unavailable under the
current execution quota. This does not change the domain acceptance. Alembic did connect to the
project PostgreSQL and applied `20260813_0007 -> 20260907_0008`; `alembic current` now reports
`20260907_0008 (head)`, and the three E05 tables are present. The fresh-chain migration test uses
an isolated fixture and passed; a fresh isolated PostgreSQL container run is **PENDING** until
Docker access is restored.

The E05 change has no frontend route or UI data-path changes. Required browser smoke routes (`/`,
`/topics`, `/topics/model-context-protocol`, `/operations`) were not re-run in this handoff because
the local browser surface was blocked by the current execution quota; the prior E04.6 `/operations`
smoke remains historical evidence only.

## E06 dependency update

E05 now satisfies the source-neutral domain dependency, but E06 itself is not implemented or live.
The E06 dependency record has been updated to:

```text
DEPENDENCY SATISFIED
IMPLEMENTATION NOT STARTED
```

Before E06 code begins, the next Epic must perform a small official GDELT DOC API capability probe,
save the real response fixture, and then implement bounded Raw-first Timeline and ArticleList
semantics. ArticleList length must never substitute for a timeline/raw-count measurement.

## Known limitations and explicit non-goals

- No GDELT, Wikipedia, Google Trends, Reddit, or Hacker News Attention collector is implemented.
- No external API was probed or called by E05.
- Event detection, Event clustering, Entity extraction/resolution, automatic Topic discovery, LLM
  classification, embeddings, and knowledge graphs are deferred.
- No article-body crawling, full-text storage, paywall access, sentiment, political-bias, fact-check,
  media-trust, Public Attention, Public Concern, Trend, Momentum, or cross-source score exists.
- E04.6 punctuality and the E04.7 off-host backup obligation remain independent operational work.

## Acceptance conclusion

E05 is accepted as a **domain foundation**, not as a data-collection Epic. Future Public Attention
collectors must reuse these contracts and minimal tables, preserve explicit Source/Channel and
Measurement/Evidence distinctions, and retain the existing Registry, Raw, provenance, Coverage, and
UTC rules. E06 may now be planned as a separate implementation Epic, but it must not be labeled LIVE
until it has real bounded collection evidence and its own acceptance.
