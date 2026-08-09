# ADR-005: Idempotent ingestion

- Status: Accepted
- Date: 2026-08-09

## Context

Long-running collection will retry after timeouts, restarts, and partial failures. Retries must not duplicate observations or normalized entities.

## Decision

Make idempotency an end-to-end invariant. Bronze identity is deterministic from source, UTC request timestamp, and payload checksum. Silver topics use a normalized unique identity, aliases use scoped unique constraints, and each attempt has an explicit ingestion run with checkpoint-before/checkpoint-after values.

## Consequences

Safe retry behavior is testable from the first release. Future collectors must define stable source record keys and use transactional upserts constrained by the database; logging a run alone is not sufficient idempotency.
