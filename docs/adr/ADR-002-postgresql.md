# ADR-002: PostgreSQL for Silver data

- Status: Accepted
- Date: 2026-08-09

## Context

Silver data needs transactions, uniqueness constraints, indexed time-series access, JSON metadata, and reliable migrations. These needs are relational and do not justify multiple persistence systems.

## Decision

Use PostgreSQL as the production Silver database, SQLAlchemy for mapping, psycopg for connectivity, and Alembic as the only schema-management mechanism. SQLite may be used for fast migration and constraint tests but is not the production database.

## Consequences

The project gains strong constraints and familiar operational tooling. PostgreSQL availability is a readiness dependency. Schema changes must include forward and reverse Alembic operations where practical.
