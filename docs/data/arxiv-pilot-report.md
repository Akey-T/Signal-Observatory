# arXiv Pilot Backfill Report

Date: 2026-08-10 UTC
Collector version: 0.1.0
Primary run: `3096b25e-408d-49ad-9010-608e331434d7`

## Scope and safety

The controlled Pilot covered five explicit enabled Registry mappings over 2026-07-01 through
2026-08-10 inclusive (API submitted-date boundary ended at 2026-08-11 00:00 UTC). Page size was
10 and `--max-pages 1` was used for each resulting date window. Requests ran serially through the
hard minimum three-second limiter. No HTML, PDF, full text, or non-API arXiv surface was accessed.

| Pilot role           | Topic                            | Exact base query                       | Result                                       |
| -------------------- | -------------------------------- | -------------------------------------- | -------------------------------------------- |
| AI, high volume      | `artificial-intelligence`        | `all:"artificial intelligence"`        | partial; recursive date partition + page cap |
| AI, active research  | `retrieval-augmented-generation` | `all:"retrieval augmented generation"` | partial; page cap                            |
| Data                 | `data-lakehouse`                 | `all:"data lakehouse"`                 | succeeded                                    |
| Developer/operations | `site-reliability-engineering`   | `all:"site reliability engineering"`   | succeeded                                    |
| Emerging/specific    | `model-context-protocol`         | `all:"model context protocol"`         | partial; page cap                            |

Dry-run planned five initial windows and estimated 12 seconds of minimum delay. The real broad
Artificial Intelligence response exceeded the configured large-query threshold and recursively
split its date range. As a result, the actual request count was 19. This is an important planning
limitation: dry-run cannot know remote `totalResults`, so its request estimate is a lower bound when
large-query partitioning occurs. The real run still remained within configured run limits and
finished in 54.8 seconds.

## Collection results

| Measure                                      |                                                Result |
| -------------------------------------------- | ----------------------------------------------------: |
| Topics tested                                |                                                     5 |
| API responses / Raw payloads                 |                                                    19 |
| HTTP 200 responses                           |                                                    19 |
| Entries present across Raw feeds             |                                                   174 |
| Entries normalized after large-window probes |                                                   104 |
| Unique Silver Papers                         |                                                   104 |
| Topic matches                                |                                                   104 |
| New Paper rows                               |                                                   104 |
| Parse errors                                 |                                                     0 |
| Ingestion errors                             |                                                     0 |
| Primary run status                           |                     `partial` (intentional page caps) |
| Runtime                                      |                                          54.8 seconds |
| Raw directory after Pilot                    | 172,565 bytes; 19 payloads + 19 sidecars + `.gitkeep` |
| PostgreSQL database after Pilot              |     11 MB total database size; not a Pilot-only delta |

The 70 feed entries not normalized were carried by high-volume parent-window probe responses.
Those Raw responses were preserved, then the collector subdivided the window before persisting
matches. Among the 104 normalized entries, there were 104 canonical Papers and 104 Topic matches:
the observed Silver duplicate ratio was 0%. The Raw-to-Silver distinction is intentional and makes
the partition decision auditable.

Matches by Topic:

| Topic                            | Matches |
| -------------------------------- | ------: |
| `artificial-intelligence`        |      80 |
| `model-context-protocol`         |      10 |
| `retrieval-augmented-generation` |      10 |
| `site-reliability-engineering`   |       3 |
| `data-lakehouse`                 |       1 |

## Idempotency and resume

The identical range was rerun for the two completed mappings in run
`856428ae-2cc0-4cdb-8a1e-891f39965c79`. Both completed cursors were recognized and skipped:

```text
API requests:       0
Raw payloads:       0
entries received:   0
Paper inserts:      0
Paper updates:      0
Topic matches added: 0
status:             succeeded
```

The three intentionally page-capped mappings retained `next_start = 10` partial checkpoints. A
future rerun resumes rather than replaying page zero. Automated integration tests separately cover
interruption after a durable page, resume at the next page, metadata updates, and an identical
second backfill.

## Manual mapping-quality sample

Twenty matches were inspected using title, abstract preview, exact matched query, published date,
source mapping ID, last ingestion run ID, and Raw checksum. All sampled rows used
`ARXIV_API_QUERY` and traced to the primary run and one of the 19 immutable Raw payloads.

| Topic                          | arXiv ID   | Title                                                      | Review                                                                   |
| ------------------------------ | ---------- | ---------------------------------------------------------- | ------------------------------------------------------------------------ |
| Artificial Intelligence        | 2608.05490 | Innovation-Residual Auditing of Autonomous Analysis Agents | Relevant; autonomous AI-agent analysis                                   |
| Artificial Intelligence        | 2608.05472 | Matrix Zonotopic Attention                                 | Relevant; attention/model method                                         |
| Artificial Intelligence        | 2608.05466 | Recursive Synthesis for Long-Horizon Terminal Tasks        | Relevant; terminal agents                                                |
| Artificial Intelligence        | 2608.05455 | Stochasticity Is Not the Hard Part                         | Borderline; instructional sequencing with AI context, broad mapping risk |
| Artificial Intelligence        | 2608.05439 | SCP-NL2TL                                                  | Relevant; natural-language AI and formal verification                    |
| Artificial Intelligence        | 2608.05436 | The ethics of artificial intelligence in the life sciences | Direct match                                                             |
| Data Lakehouse                 | 2607.09762 | BatteryLake                                                | Direct; abstract describes a governed data lakehouse                     |
| Model Context Protocol         | 2607.10569 | When Does Restricting a Coding Agent to execute_code Help? | Direct; compares MCP tool surface                                        |
| Model Context Protocol         | 2607.10123 | A Large-Scale Dataset of MCP Implementations on GitHub     | Direct                                                                   |
| Model Context Protocol         | 2607.20531 | DynamicMCPBench                                            | Direct                                                                   |
| Model Context Protocol         | 2607.08495 | The Context Access Divide                                  | Relevant; MCP-based agent access                                         |
| Model Context Protocol         | 2607.07461 | Mitigating Taint-Style Vulnerabilities in MCP Servers      | Direct                                                                   |
| Retrieval-Augmented Generation | 2607.00972 | Bayesian Uncertainty Propagation for Agentic RAG Pipelines | Direct                                                                   |
| Retrieval-Augmented Generation | 2607.01299 | HYPIC                                                      | Relevant systems angle; abstract explicitly covers RAG serving           |
| Retrieval-Augmented Generation | 2607.00895 | Beyond Document Grounding                                  | Direct; RAG hallucination detection                                      |
| Retrieval-Augmented Generation | 2607.00798 | ClinRAG-GRAPH                                              | Direct                                                                   |
| Retrieval-Augmented Generation | 2607.00725 | Recall Is Not Enough                                       | Direct                                                                   |
| Site Reliability Engineering   | 2607.23169 | Bifrost                                                    | Relevant operations/fault diagnosis; SRE appears in abstract context     |
| Site Reliability Engineering   | 2607.08529 | Log-Insight                                                | Direct operations/SRE incident diagnosis                                 |
| Site Reliability Engineering   | 2607.01788 | KRCA                                                       | Relevant root-cause analysis for production microservices                |

No clear false positive was found in the 20-paper sample. One broad Artificial Intelligence match
was marked borderline, and the query generated much higher volume than the other mappings. The SRE
mapping also retrieves adjacent operations work whose titles do not always say “SRE,” though the
sampled abstracts were relevant. These are human review findings, not automatic classifications.

## Mapping conclusions

- `model-context-protocol` appeared precise in the sample.
- `retrieval-augmented-generation` appeared precise, with a mix of modeling and serving work.
- `data-lakehouse` was sparse and precise in this range.
- `site-reliability-engineering` was relevant but includes adjacent incident-diagnosis and
  root-cause-analysis work.
- `artificial-intelligence` is intentionally broad and needs stricter operational window/page
  limits for larger backfills. Its breadth is not evidence for an automatic query rewrite.

No Registry YAML was changed. The collector observes; a human curator decides whether mappings
should change.

## UI and API observation

`data-lakehouse` and `site-reliability-engineering` have successful mapping cursors and therefore
expose `live` Topic Research state. The three page-capped Topics expose `degraded` while retaining
their persisted papers. After the zero-request idempotency run, global arXiv collector status is
healthy with a real successful run. GitHub, Hacker News, and Wikipedia remain not collecting.

## Follow-up

Before a broader production backfill:

1. Treat dry-run request estimates as lower bounds for queries that may be partitioned.
2. Backfill broad mappings in narrower explicit date ranges with conservative per-run request and
   result limits.
3. Continue human samples, especially for broad Artificial Intelligence and adjacent SRE matches.
4. Resume partial mappings deliberately; do not discard or reset their checkpoints.
