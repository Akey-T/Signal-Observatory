# ADR-025: Measurement and Evidence Remain Separate

Status: Accepted

Date: 2026-09-07

## Decision

An AttentionObservation stores a measured value, unit, definition version, UTC window, collection
state, and provenance. ObservationEvidence stores role-labelled sampled Documents. Evidence list
length never substitutes for a measured value. A zero-valued successful interval is distinct from a
missing interval, and a nullable value is never silently converted to zero.

## Consequences

GDELT Timeline/raw-count responses can support measurement while ArticleList responses explain the
measurement. A failure in one evidence request can leave a valid measurement in a partial state.
