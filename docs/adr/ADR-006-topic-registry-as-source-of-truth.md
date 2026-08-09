# ADR-006: Topic Registry as source of truth

- Status: Accepted
- Date: 2026-08-09

## Decision

Human-reviewed YAML under `config/topics/` is the administrative source of truth for canonical topics, categories, aliases, and source mappings. PostgreSQL is an audited runtime projection produced by a deterministic loader and transactional synchronizer.

## Consequences

Registry changes are reviewable in version control and can be reproduced from a checksum. Runtime database edits cannot silently redefine the registry. Automatic topic discovery must use a separate proposal workflow and cannot write curated YAML or canonical Topic rows.
