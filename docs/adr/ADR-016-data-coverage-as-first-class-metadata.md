# ADR-016: Data coverage as first-class metadata

- Status: Accepted
- Date: 2026-08-11

## Decision

Persist a deterministic, rebuildable Topic × Source coverage projection derived from source
mappings, cursors, ingestion runs and normalized observations. The projection records target and
observed windows, counts, missing dates, partial reasons and a derivation version. It uses explicit
`complete`, `partial`, `forward_only`, `empty` and `unknown` states.

Coverage is evidence metadata that future metrics must consume. A successful latest run, lack of
errors, or an administrator assertion is insufficient to label history complete. The derivation
does not use an LLM.

## Consequences

- Coverage differences remain queryable beside future analytics.
- Logic changes can be introduced through a new derivation version and projection rebuild.
- Partial and missing history remains visible and explainable.
- API requests query persisted projections instead of rescanning the Raw lake.
