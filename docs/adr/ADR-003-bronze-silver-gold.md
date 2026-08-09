# ADR-003: Bronze, Silver, and Gold layers

- Status: Accepted
- Date: 2026-08-09

## Context

Raw evidence, normalized entities, and analytical metrics have different mutation and reproducibility requirements. Combining them would make corrections difficult to audit.

## Decision

Separate data into immutable Bronze observations, normalized Silver relational entities, and versioned Gold metric outputs. Transformations flow forward; downstream output never mutates upstream evidence.

## Consequences

Normalization and aggregation can be replayed when definitions change. Storage is duplicated intentionally across semantic layers. Gold implementations wait until source inputs and metric definitions are stable.
