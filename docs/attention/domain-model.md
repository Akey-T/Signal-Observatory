# Attention Domain Model

E05 defines the source-neutral vocabulary used by future Public Attention collectors. It does not
collect external data and does not claim that any Attention source is live.

## Two signal families

```text
Signal Observatory
├── Technology Signals
│   ├── Research (arXiv)
│   └── Developer (GitHub)
└── Attention Signals
    ├── Media
    ├── Search
    ├── Community
    └── Reference
```

Technology Signals remain unchanged. Attention Channel is not a replacement name for Research or
Developer, and Source is not a synonym for Channel.

## Core objects

| Object               | Meaning                                                                | E05 persistence       |
| -------------------- | ---------------------------------------------------------------------- | --------------------- |
| Topic                | Curated long-lived monitoring subject                                  | Reuses Topic Registry |
| Entity               | Curated real-world person, organization, company, location, or product | Contract only         |
| Event                | Curated time-bounded real-world occurrence                             | Contract only         |
| AttentionDocument    | Source-provided evidence document without a required full text body    | Persisted             |
| AttentionObservation | Numeric or nullable measurement over a UTC interval                    | Persisted             |
| ObservationEvidence  | Role-labelled link from an Observation to a sampled Document           | Persisted             |

`Topic`, `Entity`, `Event`, `AttentionDocument`, and `AttentionObservation` are distinct concepts.
A Document is evidence; it is not itself an attention measurement. An Event is not inferred from a
Document, and an Entity is not created from a name found in a Document.

## Source and Channel

E05 reuses the existing `sources` identity and `topic_source_mappings` Registry boundary. A future
adapter can declare, for example, `source = gdelt` and `channel = MEDIA`, or `source = wikipedia`
and `channel = REFERENCE`. The four supported channels are `MEDIA`, `SEARCH`, `COMMUNITY`, and
`REFERENCE`. There is deliberately no `PUBLIC_CONCERN` channel.

## Persisted Document

`attention_documents` stores a source-local key, source, optional canonical URL/title/published
time, document type, first/last observed times, metadata, and timestamps. It does not store a
generic full-text/body field. `(source_id, source_document_key)` is the logical identity; global
entity resolution is a separate governance problem.

## Persisted Observation

`attention_observations` stores Topic, Source, explicit Source Mapping, Channel, closed UTC window,
metric name, nullable numeric value, unit, metric definition version, collection state, optional
ingestion run lineage, observed timestamps, and metadata. Its logical identity includes:

```text
topic + source + source mapping + channel + metric + window start + window end
```

The database enforces `window_end > window_start` and prevents duplicate logical intervals. The
existing `CoverageStrategy` enum is reused for future adapters, including bounded historical and
forward-only semantics. `AttentionCoverageContract` also carries the expected window duration and
normalized observed, missing, and partial UTC windows; E05 does not materialize those future source
coverage rows.

`AttentionSourceAdapter` is a contract only: it declares source identity, channel, metric
definitions, evidence semantics, source-local document identity, and coverage. It performs no
network I/O, persistence, topic creation, entity resolution, event clustering, or trend
calculation.

## Evidence

`attention_observation_evidence` connects one Observation to one Document with an explicit role
(`SAMPLE`, `MATCH`, `EXAMPLE`, or `SOURCE_RECORD`). The same relation cannot be inserted twice.
Evidence is intentionally sampled: a measured value of 20,000 articles may have 20 evidence
Documents and remain valid.

## Provenance boundary

Production adapters must be able to trace:

```text
Observation → Source Mapping → Ingestion Run → source Raw response
Document → source match → Ingestion Run → source Raw response
```

E05 does not produce Raw records. It only provides the foreign-key and lineage fields that a later
collector must populate. Raw logical keys remain owned by the existing RawStore system; machine
absolute paths do not enter these models.
