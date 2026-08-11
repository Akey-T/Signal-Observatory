# ADR-015: GitHub conditional request semantics

- Status: Accepted
- Date: 2026-08-11

## Decision

Repository polls retain the latest ETag and send `If-None-Match` when conditional requests are
enabled. A `200` response is preserved to Raw, normalized, and appended as that day's full
snapshot. A `304 Not Modified` response is also preserved to Raw and creates that day's immutable
snapshot by copying the prior known state with observation source `conditional_304`.

HTTP observation and daily state are therefore distinct: the 304 Raw record proves the poll, and
the lightweight normalized row makes the question “what value was observed each day?” direct.
Poll state advances only after both provenance and snapshot semantics commit successfully.

## Consequences

- A 304 does not erase the daily observation point.
- No prior snapshot means a 304 is invalid and cannot advance poll state.
- Same-date reruns remain idempotent.
- Missing polls stay missing rather than being fabricated from adjacent dates.
