# Source collectors

Source-specific clients, parsers, query builders, persistence orchestration, and read models live
under this directory. They reuse `collector-core` Raw contracts and the shared ingestion lifecycle;
they do not create a parallel framework.

- `arxiv/`: E03 Research metadata, resumable cursors, and Paper evidence.
- `github/`: E04 Repository discovery, numeric identity, immutable daily snapshots, and Developer
  evidence.

Generic Topic models never contain source query logic. Each collector executes only explicit
Registry mappings and may not modify curated YAML from observations.
