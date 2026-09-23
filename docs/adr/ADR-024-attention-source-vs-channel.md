# ADR-024: Attention Source and Channel Are Separate

Status: Accepted

Date: 2026-09-07

## Decision

Source identifies the provider (`gdelt`, `wikipedia`, or a future platform); Channel identifies
what kind of attention signal it measures (`MEDIA`, `SEARCH`, `COMMUNITY`, or `REFERENCE`). A
Source never substitutes for a Channel, and `PUBLIC_CONCERN` is not a channel.

## Consequences

Operations and future APIs can compare channel semantics without claiming that all sources measure
the same quantity. Source-specific query, geography, language, and identity fields remain outside
the generic Attention tables.
