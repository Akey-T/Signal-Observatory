# ADR-021: Restore only into explicit empty targets

## Status

Accepted — 2026-08-12

## Context

In-place restore can silently combine incompatible database, Raw, Registry, and provenance state.
An overwrite switch would make operator error destructive.

## Decision

Restore requires an explicit PostgreSQL URL and Raw directory. The database must contain no tables,
the Raw target must be empty, and both must differ from active storage and the source backup. No
force or overwrite mode exists. Disaster-recovery acceptance uses a uniquely named isolated
database and Raw directory and cleans them after evidence is persisted.

## Consequences

Operators must provision an empty target, but drills and migrations cannot damage active data.
Cutover, if later required, is a separate deployment decision after the restored unit passes all
checks.
