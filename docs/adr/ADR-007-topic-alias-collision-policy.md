# ADR-007: Topic alias collision policy

- Status: Accepted
- Date: 2026-08-09

## Decision

Aliases retain punctuation and declare case sensitivity and matching mode. Cross-topic collisions fail validation unless an exact topic set and human review reason appear in `allowed_alias_collisions`.

## Consequences

The system never silently guesses which canonical topic owns an ambiguous term. Approved ambiguity remains visible in warnings, version metadata, audit history, and data-quality output. Source-specific query terms remain mappings rather than becoming canonical topics.
