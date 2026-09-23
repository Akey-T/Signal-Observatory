# Signal Observatory Agent Guide

These rules apply to the entire repository.

## Non-negotiable rules

1. Data integrity takes priority over feature velocity.
2. Raw records are immutable.
3. Every ingestion must be idempotent.
4. Every database schema change requires an Alembic migration.
5. Store timestamps in UTC.
6. Never remove tests to fix CI.
7. Prefer official APIs or feeds over scraping.
8. Never bypass authentication, CAPTCHA, rate limits, or anti-bot controls.
9. All metrics must be reproducible from persisted data.
10. LLM output must never modify raw observations.
11. Avoid unnecessary infrastructure.
12. Keep issues narrowly scoped.
13. Run lint, type checking, and tests before completing work.
14. Update documentation when architecture changes.
15. Never create a new canonical Topic solely because a new keyword was observed.
16. Alias ambiguity must be surfaced, never silently resolved.
17. Topic deletion is prohibited after observations exist.
18. Registry YAML is the administrative source of truth.
19. Registry sync must remain idempotent.
20. Source-specific mapping logic must not leak into generic Topic models.
21. Automatic topic discovery must remain separate from curated registry data.
22. Do not use LLMs to silently alter curated registry entries.
23. Never display fabricated trend metrics.
24. Monitoring priority must never be labeled as popularity or trend strength.
25. A configured source mapping does not mean a collector is live.
26. Curated topics must not be labeled as trending without observation data.
27. UI must distinguish registry configuration from observed signals.
28. Prefer existing read-only APIs over duplicated frontend data.
29. Do not add UI-only database tables for homepage presentation.
30. Never scrape arXiv human HTML pages for metadata.
31. Respect arXiv machine-access guidance and request pacing.
32. Every external response must be persisted to Raw before normalization.
33. arXiv topic matches must remain explainable by explicit Registry mappings.
34. Never silently generate or modify arXiv queries from aliases.
35. Paper/topic is many-to-many.
36. Cursor advancement must occur only after durable successful persistence.
37. Re-running collection must remain idempotent.
38. Collector errors must not destroy already persisted Raw data.
39. Do not download PDFs or full text in E03.
40. Do not derive Trend Score from paper counts in E03.
41. External observations and Registry configuration remain separate concepts.
42. Never scrape GitHub human-facing HTML for E04 data.
43. Use GitHub repository numeric ID as persistent identity.
44. Repository `full_name` is mutable.
45. Every GitHub HTTP response must have Raw provenance.
46. Never log authentication tokens.
47. GitHub Topic matching must be explainable by explicit Registry mappings.
48. Do not silently generate GitHub queries from Topic aliases.
49. Search discovery and Repository snapshotting are separate concerns.
50. Historical Repository snapshots are immutable.
51. Never fabricate pre-observation star history.
52. Do not collect individual Stargazer histories in E04.
53. Use conditional requests where appropriate.
54. Respect rate-limit and retry headers.
55. Do not interpret stars as Trend Score.
56. Do not use contributor-level data unless a later Epic explicitly approves it.
57. A missing daily Snapshot must remain observable as missing data.
58. GitHub failures must not modify arXiv Research evidence.
59. Never infer complete coverage solely from a successful latest run.
60. Collector health and historical coverage are separate concepts.
61. GitHub Snapshot history is forward-only from first observation.
62. Missing observation dates must not be interpolated.
63. Partial historical collection must remain visibly partial.
64. Coverage status must be deterministic.
65. Analytics must eventually consume coverage metadata.
66. Coverage derivation must remain rebuildable.
67. Do not use LLMs to decide completeness.
68. Operations UI must not display fabricated percentage scores.
69. PostgreSQL, immutable Raw, Registry configuration, and provenance form one recovery unit.
70. A published backup must contain a custom-format PostgreSQL dump and a checksummed Raw copy.
71. Never publish an unverified or failed backup from staging.
72. Backup manifests and reports must never contain credentials or authentication tokens.
73. Backup identifiers and evidence timestamps must use UTC.
74. Raw paths persisted in the database must be portable logical keys, not machine-local paths.
75. Backup creation must dump the database before copying Raw.
76. Raw records newer than the database snapshot must be reported as extras, never hidden.
77. Restore targets must be explicit, empty, and distinct from active Observatory storage.
78. Restore tooling must never offer an overwrite or force mode.
79. Restore verification must compare exact table counts, migration head, Registry, Raw, and lineage.
80. Disaster-recovery drills must use isolated PostgreSQL and Raw targets.
81. A backup on the same physical disk is not the sole acceptable disaster-recovery copy.
82. E03 soak and E04 cross-day evidence must remain independent from backup acceptance evidence.
83. Media Attention must never be labeled Public Concern.
84. Attention Source and Attention Channel are different concepts.
85. Topic, Event, Entity, Document, and Observation are distinct domain objects.
86. A Document is evidence; it is not itself an attention measurement.
87. Evidence count must never substitute for a measured observation value.
88. Zero-valued observations and missing observations are different.
89. Source collectors must not automatically create canonical Events.
90. Source collectors must not automatically create canonical Entities.
91. Source collectors must not automatically create canonical Topics.
92. Event detection must remain separate from canonical Event governance.
93. Entity extraction must remain separate from canonical Entity governance.
94. Attention metrics must declare their unit and definition version.
95. Attention observations must preserve source, channel, UTC window, and provenance.
96. No Public Attention Score or Public Concern Score may be introduced in E05.
97. No Trend Score may be introduced in E05.

## Repository boundaries

- `apps/` contains deployable processes; keep domain logic in packages.
- `packages/collector-core/` owns shared ingestion contracts and Bronze storage.
- `packages/topic-registry/` owns curated Topic schema, validation, diff, and sync logic.
- `db/` owns SQLAlchemy models, repositories, and Alembic migrations.
- `collectors/` contains source-specific collectors; `collectors/arxiv/` owns E03 arXiv logic and
  `collectors/github/` owns E04 GitHub logic.
- `config/topics/` is the administrative source of truth for curated Topics.
- `data/raw/` is runtime state and must never be edited in place.
- `data/backups/` is ignored runtime state; only manifests/reports quoted in acceptance docs are
  versioned.
- Gold analytics are interfaces only until their persisted inputs and metric definitions exist.

## Required checks

Run these from the repository root before declaring work complete:

```text
python -m ruff check .
python -m ruff format --check .
python -m mypy apps packages config db collectors
python -m pytest
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
```

Use `docker compose config` and, when Docker is available, `docker compose up --build` for
infrastructure validation.
