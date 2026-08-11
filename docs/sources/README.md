# Source documentation

Each source must document its official API/feed, authentication, rate limits, checkpoint semantics, source record identity, licensing/terms, schema version strategy, and expected data-quality checks before its collector is enabled.

Implemented sources:

- [arXiv Research metadata](arxiv.md) — live in E03 through the official arXiv API.
- [GitHub Developer metadata](github.md) — E04 implementation complete; authenticated Pilot and
  forward-snapshot acceptance determine whether it is live.

Hacker News and Wikipedia remain Registry mappings only; their collectors are not implemented.
