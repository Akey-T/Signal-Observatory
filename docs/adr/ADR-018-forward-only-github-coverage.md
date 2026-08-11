# ADR-018: GitHub coverage is forward-only

- Status: Accepted
- Date: 2026-08-11

## Decision

GitHub Repository Snapshot coverage begins on the first persisted real UTC observation date and is
classified as `forward_only`. The status remains forward-only after additional observation dates;
it is not called partial merely because pre-observation daily history is unavailable.

Expected daily dates between the first and latest observations are compared with persisted
Snapshot dates. Gaps are exposed as missing and are never interpolated. A 304 conditional response
can create a real unchanged daily observation because its Raw poll evidence is persisted; a missed
poll cannot.

## Consequences

- GitHub collector health can be healthy while historical coverage is forward-only.
- A second UTC date validates cross-day behavior but does not convert coverage to complete.
- Metric consumers can distinguish real daily history from unavailable pre-observation history.
- The read-only cross-day verifier cannot create or repair observations.
