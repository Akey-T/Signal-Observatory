# ADR-019: PostgreSQL, Raw, Registry, and provenance are one recovery unit

## Status

Accepted — 2026-08-12

## Context

Normalized entities and metrics depend on immutable source responses, curated Topic identity,
ingestion runs, source mappings, and exact provenance pointers. Recovering only one layer can
produce apparently healthy but irreproducible data.

## Decision

A valid full backup always contains the PostgreSQL custom-format dump, immutable Raw tree and
sidecars, Registry YAML snapshot, strict manifest, Raw manifest, and verification report. Partial
backup types are outside E04.5B.

## Consequences

Backup storage is larger than a database-only dump, but restored observations remain traceable and
metrics remain reproducible. Verification must fail when any required member is missing or
inconsistent.
