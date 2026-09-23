# Event and Entity Boundaries

E05 defines canonicalization boundaries; it does not run extraction, resolution, clustering, or
automatic promotion.

## Canonical Entity

A `CanonicalEntity` is a curated identity with a declared type (`PERSON`, `ORGANIZATION`,
`COMPANY`, `LOCATION`, `PRODUCT`, or `OTHER`). The contract stores canonical and normalized names,
optional description, and lifecycle status. It does not solve global identity resolution:

```text
Apple
Apple Inc.
苹果公司
```

must not be silently assumed to be one Entity. Source-local references and curated canonical
identity remain separate.

Collectors cannot create canonical Entities from observed names. A future Entity Resolution Epic
must define review, provenance, and promotion rules first.

## Canonical Event

A `CanonicalEvent` is a curated, time-bounded real-world occurrence with optional type, start/end,
and lifecycle status (`ACTIVE`, `ENDED`, `MERGED`, `DEPRECATED`). Only `CURATED` creation is
accepted by the E05 contract. A system-produced `EventCandidate` is a non-canonical review input;
there is no E05 table or promotion path for it.

Documents that describe similar occurrences do not automatically create or merge Events. Event
Detection and Event Clustering are separate future work.

## Topic boundary

Topics remain curated Registry entities. A Document title, Entity name, or Event candidate cannot
create a Topic, modify a Topic YAML file, or silently generate a Source Mapping. Aliases are not
automatically expanded into attention queries.

## LLM and text boundary

E05 performs no text classification, entity extraction, event extraction, embeddings, semantic
deduplication, or LLM review. Future LLM output cannot create canonical Events or Entities, convert
Media Attention into Public Concern, or infer a missing Observation.

## Source and geography boundary

Source-specific metadata stays in the source adapter. A source country describes an outlet/source
geography, not necessarily the event location. A document language describes the document, not the
audience nationality. A URL or source-local identifier is not automatically a canonical Entity.

## Explicit non-goals

E05 does not implement a knowledge graph, Neo4j/RDF/vector store, article-body storage, paywall
access, sentiment, political bias, fact checking, media trust, Public Attention Score, Public
Concern Score, Trend Score, or cross-source analytics.
