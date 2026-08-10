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

## Repository boundaries

- `apps/` contains deployable processes; keep domain logic in packages.
- `packages/collector-core/` owns shared ingestion contracts and Bronze storage.
- `packages/topic-registry/` owns curated Topic schema, validation, diff, and sync logic.
- `db/` owns SQLAlchemy models, repositories, and Alembic migrations.
- `collectors/` is reserved for source-specific collectors; none belong in E00-E02.5.
- `config/topics/` is the administrative source of truth for curated Topics.
- `data/raw/` is runtime state and must never be edited in place.
- Gold analytics are interfaces only until their persisted inputs and metric definitions exist.

## Required checks

Run these from the repository root before declaring work complete:

```text
python -m ruff check .
python -m ruff format --check .
python -m mypy apps packages db
python -m pytest
npm run lint
npm run typecheck
npm run test
npm run build
```

Use `docker compose config` and, when Docker is available, `docker compose up --build` for
infrastructure validation.
