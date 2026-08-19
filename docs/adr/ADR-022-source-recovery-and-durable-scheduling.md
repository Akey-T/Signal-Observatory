# ADR-022: Fail-closed source recovery and durable schedule evidence

Status: Accepted

Date: 2026-08-13

## Context

Hacker News and Wikipedia are present in the curated Registry, but the implemented recovery and
coverage paths originally named only arXiv and GitHub. Adding a collector under that design could
leave new Raw evidence outside a published backup or let an existing coverage rebuild delete rows
owned by another source. The in-process scheduler also kept future plans only in memory, so a
container restart could silently skip a due window.

## Decision

- Backup, Raw integrity, source manifests, and restore lineage use one explicit recovery-adapter
  catalog. An unknown persisted Raw source fails backup creation and an unsupported manifest source
  fails verification.
- Manifest source names remain safely extensible; adding a collector requires registering its Raw
  pointer model, database count surfaces, and lineage sampler in the same change.
- Coverage deletion is restricted to sources handled by the active derivation implementation.
- Scheduler windows are persisted before they are due. Restart reconciliation materializes every
  elapsed window after the last plan, records unclaimed windows as `missed`, and records abandoned
  running plans as `interrupted`; it does not manufacture a successful run.
- Scheduler terminal evidence preserves `succeeded`, `partial`, and `failed` collector outcomes.
  Window claims are atomic, PostgreSQL permits one advisory-lock leader, and a scheduler coroutine
  failure removes Worker readiness and terminates the process.
- Locks are per source. Jobs sharing a source budget remain serialized, while independent sources
  do not block each other.
- Shared Wikipedia page mappings produce a Registry warning and must retain shared provenance in a
  future Public collector. Warning metadata changes are versioned even when curated Registry
  content and its checksum are unchanged.

## Consequences

New collectors require a narrow recovery and coverage adapter as part of their acceptance scope.
This is deliberate duplication at the source boundary, not source-specific logic in generic Topic
models. Scheduler evidence adds one Alembic-managed operational table and is included automatically
in exact-count backup/restore verification. Existing arXiv ingestion, GitHub ingestion, Raw bytes,
and Topic matching semantics are unchanged.
