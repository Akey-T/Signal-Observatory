# P2-A GDELT DOC capability probe — 2026-09-24 UTC

## Decision: NO-GO for implementation at this access point

This is a bounded, non-production probe, not E06 implementation or acceptance. Two direct requests
to the official DOC 2.0 API for a two-hour UTC window both returned HTTP 429. They were separated
by more than the response's requested five-second pacing interval. The second response body is
preserved in [`gdelt-doc-429-2026-09-24.txt`](fixtures/gdelt-doc-429-2026-09-24.txt). No
successful Timeline or ArticleList JSON was received, so schema, zero-result behavior,
deduplication, stable document identity, language behavior, pagination, and reproducible window
behavior remain **unverified**. No further retry was attempted, no rate limit was bypassed, and no
production GDELT Raw, database row, Registry mapping, scheduler job, or UI LIVE state was created.

## Method and exact request

Endpoint:

```text
GET https://api.gdeltproject.org/api/v2/doc/doc?query=%22climate%20change%22&mode=timelinevolraw&format=json&startdatetime=20260923000000&enddatetime=20260923020000
User-Agent: Signal-Observatory-Capability-Probe/0.1
```

The query is an ordinary phrase, the window is two hours, and the request contained no token or
credential. Both responses were HTTP 429 with a plain-text instruction to limit requests to one
every five seconds and guidance to consider the Web NGrams dataset for high-volume users. This
may reflect a shared network/IP limit; the probe cannot determine that cause. It does demonstrate
that a reliable daily collection claim cannot be made from the current access path.

## Documented semantics versus observed semantics

The [official DOC 2.0 reference](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
documents `STARTDATETIME`/`ENDDATETIME`, JSON output, `TimelineVolRaw` as distinct matching
article counts with `norm`, and `ArtList` as a bounded evidence list (default 75, documented
maximum 250). The [GDELT rate-limit guidance](https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/)
confirms that DOC/Context APIs are rate-limited to protect backend clusters. These are source
statements, not successful measurements in this probe. Older documentation about historical
availability is not evidence of today's accessible depth.

The proposed World Pulse v1 product cutoff remains `20:00 America/New_York`, with UTC persisted
windows and DST handled through an IANA timezone implementation. There is no permanent UTC hour
for this local-time cutoff: the local `zoneinfo` check maps 2026-01-15 20:00 New York to
2026-01-16 01:00 UTC, but 2026-07-15 20:00 New York to 2026-07-16 00:00 UTC.
`TimelineVolRaw` would be a candidate measured Media Attention
Observation; ArticleList would be only a sampled Document evidence list. Its length must not be
used as the measured value.

## Next gate

Do not start P2-B or schedule GDELT production collection on this evidence. A later, owner-reviewed
probe may retry a few paced official requests after source access is available. It must capture
small successful Timeline/ArtList/zero-result fixtures, verify interval and identity behavior,
and return a new GO/NO-GO decision before any bounded implementation plan is proposed.
