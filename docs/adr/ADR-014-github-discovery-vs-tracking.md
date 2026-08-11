# ADR-014: GitHub discovery and tracking are separate

- Status: Accepted
- Date: 2026-08-11

## Decision

Weekly discovery executes only explicit, enabled `github` Registry mappings through the official
Repository Search endpoint. It never derives queries from Topic aliases. Search results are
candidate evidence, not a claim of verified relevance. Each match records the exact query,
mapping, rank, run, and Raw response.

Tracking uses a deterministic cap, API rank, public/non-fork policy, and numeric-ID deduplication.
Forks, archived, and disabled repositories remain identifiable but are not newly prioritized by
default. Daily snapshotting operates independently over already tracked repositories.

## Consequences

- Search and Core rate budgets can fail independently.
- Discovery failure cannot invalidate existing snapshots or stop Core-budget polling.
- One Repository can match several Topics.
- Mapping quality remains reviewable and does not use LLM or embedding classification.
