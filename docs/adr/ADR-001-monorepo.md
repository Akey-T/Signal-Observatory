# ADR-001: Monorepo

- Status: Accepted
- Date: 2026-08-09

## Context

API, worker, collector contracts, relational models, migrations, and the web UI evolve around shared data invariants. Splitting them now would make cross-layer changes harder to validate atomically.

## Decision

Use one monorepo with deployable processes in `apps/`, reusable Python code in `packages/`, shared settings in `config/`, and persistence code in `db/`. Root-level Python and npm configuration provides one quality-check entry point.

## Consequences

Cross-layer migrations and contract changes can land with their tests and documentation. Package boundaries must still be respected; source-specific logic does not belong in the API or collector core.
