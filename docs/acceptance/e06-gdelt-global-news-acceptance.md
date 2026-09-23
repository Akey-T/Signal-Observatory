# Signal Observatory — E06 GDELT Global News Collector

## Dependency gate result

**DEPENDENCY SATISFIED — E05 Attention Domain Foundation is accepted; E06 implementation not started.**

This is a dependency update, not an E06 implementation acceptance. The E06 specification requires
an accepted, source-neutral foundation for `Topic`, `Event`, `Entity`, `Article / Document`, and
`Observation` before production GDELT schema or collection work begins.

## Evidence checked

- `docs/acceptance/e05-attention-domain-foundation-acceptance.md` records E05 acceptance.
- The repository now provides accepted source-neutral Attention Domain contracts and minimal
  persisted Document, Observation, and Evidence models for future collectors.
- Entity and Event remain contract-only; their governance is not silently treated as implemented.
- The existing `event_stream` coverage enum remains an infrastructure value; E05 reuses and extends
  the shared Coverage strategy rather than creating a parallel coverage system.
- Existing arXiv, GitHub, Registry, Raw, Coverage, Scheduler, Operations, and backup boundaries
  remain source-specific and must not be reinterpreted as E05.

## Work intentionally not started

E06 remains deliberately unimplemented after the prerequisite update:

- no GDELT endpoint probe or production request;
- no database tables or Alembic migration;
- no `GdeltClient`, Query Builder, parser, collector, cursor, or scheduler;
- no GDELT Registry mappings or Topic changes;
- no Coverage, Operations API, UI, or production Docker changes;
- no GDELT Raw, Article, Media Attention, Event, or trend data;
- no claim that GDELT is configured, live, healthy, or accepted.

No database, Raw records, Registry YAML, arXiv evidence, GitHub evidence, or Scheduler history was
modified by this dependency review.

## Satisfied prerequisite and next implementation gate

**E05 — Attention Domain Foundation is now separately accepted.** Its source-neutral contracts,
ownership boundaries, and minimal Document/Observation/Evidence persistence are the only foundation
available to E06. E06 must reuse them instead of introducing competing `gdelt_article`,
`news_article`, or `attention_article` concepts.

When implementation is authorized, resume E06 in this order:

1. perform a small official GDELT DOC API capability probe and persist a fixture;
2. implement bounded, Raw-first timeline and ArticleList collection against explicit mappings;
3. prove interval, article identity, provenance, coverage, catch-up, and idempotency semantics;
4. run the bounded real pilot and 50-row human evidence review;
5. integrate Operations/API/UI and produce a new evidence-backed E06 acceptance decision.

GDELT Media Attention must remain distinct from Public Attention, Public Concern, Event Importance,
and Trend Score. No automatic Event clustering, Topic discovery, article-body crawling, sentiment,
or cross-source scoring is authorized by this gate.

## Current project boundary

E05 is the latest implemented Epic, but it is a domain foundation only: no Attention source is live.
E04.6 scheduler punctuality remains `FAILED 0/3` in the latest read-only qualification, arXiv
cursor coverage remains separate, and the E04.7 off-host recovery obligation is still independent.
This dependency record does not alter those historical or operational facts.
