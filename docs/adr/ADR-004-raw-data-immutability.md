# ADR-004: Raw data immutability

- Status: Accepted
- Date: 2026-08-09

## Context

Reproducible research requires the exact bytes returned by a source. In-place corrections destroy evidence and make later results impossible to explain.

## Decision

Treat every Bronze record as immutable. `LocalRawStore` stores gzip payload bytes and a checksum manifest in a deterministic directory, publishes the directory atomically, and has no update or delete operation. Duplicate writes verify and return the existing record.

## Consequences

Corrections must be new observations or downstream normalization changes. Storage grows monotonically and needs an explicit future retention policy. External tampering is detected on read through SHA-256 and length verification.
