# ADR-008: Topic deprecation instead of deletion

- Status: Accepted
- Date: 2026-08-09

## Decision

Topics with historical identity are retired by explicit `deprecated` status. Sync never deletes database records merely because YAML entries disappear; it reports orphan warnings. Registry changes, audit rows, and quality checks are committed atomically, and identical content is a no-op.

## Consequences

Historical observations keep valid foreign keys and partial registry versions cannot become visible. Operators can attribute each applied semantic change, while accidental file deletion cannot silently destroy Topic identity.
