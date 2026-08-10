# Collectors

`collectors/arxiv/` is the first source-specific collector. It performs selective,
topic-driven metadata collection through the official arXiv API. The package owns query
construction, conservative HTTP access, Atom parsing, Raw-response lineage, idempotent Silver
persistence, backfill/incremental orchestration, cursors, status, and sampling services.

It does not scrape arXiv HTML, download PDFs/full text, invent Topic mappings, classify papers
with an LLM, or calculate trend metrics. Shared ingestion contracts and filesystem Raw storage
remain in `packages/collector-core/`.
