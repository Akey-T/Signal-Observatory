# ADR-009: Topic-driven arXiv API collection

## Status

Accepted — 2026-08-10.

## Context

Signal Observatory needs explainable research observations for a curated set of Topics. It does
not currently need a complete local mirror of arXiv metadata. arXiv provides a query API, OAI-PMH,
RSS, and bulk-access mechanisms, while its terms prohibit undifferentiated automated access to the
human website.

## Decision

Use the official arXiv API for selective queries generated only from explicit enabled Registry
mappings. Use one connection, a hard minimum three-second request interval, bounded retries and
safety limits, and immutable Raw persistence before parsing.

Do not scrape HTML. Do not implement API and OAI-PMH collectors simultaneously. This keeps one
ingestion identity, one cursor strategy, and one operational failure surface for E03.

## Consequences

The strategy is easy to explain per Topic and avoids collecting an unrelated corpus. It is not
efficient for very broad queries or corpus-level harvesting; large searches therefore use date
partitioning and conservative limits. API availability is an operational dependency but not a CI
dependency because normal tests use saved Atom fixtures.

Reconsider OAI-PMH when the required workload is corpus-level incremental harvesting, when a large
fraction of arXiv is needed, or when selective API pagination becomes the dominant cost. That
change requires a new ADR covering identifiers, cursor migration, Raw schema, and coexistence or
retirement of the API path.
