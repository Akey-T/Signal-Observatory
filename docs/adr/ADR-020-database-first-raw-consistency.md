# ADR-020: Database snapshot first, immutable Raw copy second

## Status

Accepted — 2026-08-12

## Context

Collectors persist Raw before normalized database facts. Backups may run while collectors are
active, and stopping all collection is unnecessary for the current scale.

## Decision

Create an exported PostgreSQL repeatable-read snapshot, run `pg_dump` against it, close that
snapshot, then copy immutable Raw. Raw records beyond the database snapshot are allowed only as
visible warnings. A database row whose Raw record is absent is a verification failure.

## Consequences

The recovery unit never contains database facts pointing to bytes that were intentionally omitted.
It may contain harmless newer Raw records that can be normalized later. This relies on the
non-negotiable Raw-first and immutable Raw contracts.
