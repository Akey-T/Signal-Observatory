# ADR-010: arXiv Paper and Topic are many-to-many

## Status

Accepted — 2026-08-10.

## Context

One arXiv Paper can appear in several explicit Topic queries, and one Topic can match many Papers.
Putting `topic_id` on `arxiv_papers` would lose valid matches or duplicate Paper identity.

## Decision

Store canonical Papers independently and represent membership with `arxiv_topic_matches`. A match
stores Topic, Paper, source mapping, exact matched query, `ARXIV_API_QUERY` method, first/last match
times, and first/last ingestion runs. Its unique constraint covers Paper, Topic, mapping, and query.

## Consequences

Paper metadata is normalized once while every Topic association remains explainable and
idempotent. Query changes can coexist as distinct historical match explanations. No semantic
relationship beyond inclusion in the configured API result is asserted.
