# ADR-011: Preserve every arXiv response before normalization

## Status

Accepted — 2026-08-10.

## Context

Silver arXiv metadata can change when Papers are revised or normalization evolves. Debugging,
reprocessing, and audit require the exact response that produced a normalized observation.

## Decision

Write every received API response to immutable `RawStore` before status handling, parsing, or
normalization. Index the Raw path, checksum, request, response metadata, Topic, mapping, and run in
`arxiv_raw_responses`. Connect each normalized observation through
`arxiv_paper_observations`.

Retry responses, empty feeds, 403s, other HTTP errors, and malformed XML are Raw records too. A
transport failure without a received response has no payload to persist but remains an ingestion
error and counts against the run request limit.

## Consequences

Any Research API Paper can be traced through Silver Paper, Topic match, source mapping, ingestion
run, observation, and Raw checksum. Storage grows with observations rather than unique Papers, but
payloads are compressed and immutable. Raw is never edited to repair Silver; corrected parsers
must reprocess evidence into a new normalized state.
