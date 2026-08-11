# ADR-013: GitHub Repository identity

- Status: Accepted
- Date: 2026-08-11

## Decision

The persistent external identity is GitHub's numeric Repository `id`. `owner_login`, `name`, and
`full_name` are mutable attributes. Discovery and polling upsert the current entity by numeric ID;
a rename or ownership transfer updates that current row without splitting its history.

Snapshots retain `full_name` at observation time. Topic relations point to the internal Repository
UUID, and the external numeric ID has a unique constraint.

## Consequences

- Rename/transfer continuity is deterministic and testable.
- URLs and names are display metadata, not keys.
- A Repository may relate to multiple Topics without duplication.
- Deleted or unavailable Repository identities remain in history; a 404 is an observable poll
  outcome, not authorization to delete evidence.
