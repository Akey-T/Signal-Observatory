# ADR-017: Collector health and data coverage are separate

- Status: Accepted
- Date: 2026-08-11

## Decision

Represent collector health, data freshness and historical coverage as separate deterministic
concepts. Collector health is based on persisted configuration and recent runs; freshness is based
on last successful observation time and source thresholds; coverage is based on the source's
historical collection semantics.

Overall Observatory state may be degraded by partial historical coverage even while a collector is
currently healthy. Conversely, old persisted data remains available when a recent run fails.
Registry validity remains a fourth independent signal.

## Consequences

- Operators can distinguish a current incident from a known historical limitation.
- No opaque health score or fabricated percentage is required.
- Community and Public can be reported as not started without presenting them as failures.
- State transitions remain testable and reproducible from persistence.
