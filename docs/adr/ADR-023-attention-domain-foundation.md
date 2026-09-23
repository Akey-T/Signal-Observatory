# ADR-023: Source-neutral Attention Domain Foundation

Status: Accepted

Date: 2026-09-07

## Context

Future Media, Search, Community, and Reference collectors need shared semantics without coupling
the core model to GDELT, Wikipedia, Google Trends, or one platform's identifiers. Existing Topic,
Source, Registry Mapping, Raw, Ingestion Run, and Coverage boundaries are already authoritative.

## Decision

- Define source-neutral contracts for Topic, Entity, Event, AttentionDocument, AttentionObservation,
  Evidence, Source, Channel, metric units, and coverage semantics.
- Persist only Documents, Observations, and ObservationEvidence in E05; Entity and Event remain
  contract-only until their governance epics exist.
- Reuse existing Source, Topic, Source Mapping, Ingestion Run, RawStore, and Coverage identities.
- Keep Technology Signals (Research/Developer) separate from Attention Signals (Media/Search/
  Community/Reference).
- Require UTC windows, explicit units, definition versions, and deterministic logical identities.

## Consequences

Future source collectors can share one Observation/Evidence vocabulary while keeping GDELT,
Wikipedia, and platform-specific fields in source-specific adapters. E05 adds one migration for
the minimal persisted domain and does not make any external requests.
