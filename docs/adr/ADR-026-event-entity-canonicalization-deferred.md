# ADR-026: Event and Entity Canonicalization Deferred

Status: Accepted

Date: 2026-09-07

## Decision

E05 defines curated CanonicalEvent, CanonicalEntity, and review-only EventCandidate contracts but
does not persist or automatically promote them. Collectors, LLMs, and observed document text cannot
create canonical Events, Entities, or Topics. Event detection, clustering, entity extraction, and
global resolution require later governance and acceptance.

## Consequences

E06 can retain document and observation evidence without inventing event or entity facts. The
absence of a canonical Event or Entity is observable as an unimplemented governance boundary, not
silently inferred data.
