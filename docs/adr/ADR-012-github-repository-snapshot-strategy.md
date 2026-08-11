# ADR-012: GitHub Repository snapshot strategy

- Status: Accepted
- Date: 2026-08-11

## Decision

Signal Observatory records at most one immutable Repository snapshot per UTC observation date.
The first successful Repository response is the baseline and defines the beginning of historical
coverage. Later scheduled polls append forward observations; they never synthesize dates before
the baseline and never fill a day on which no successful observation occurred.

The current `github_repositories` row is mutable identity metadata. Historical values belong only
to `github_repository_snapshots`, including the `full_name` observed that day. A repeated logical
run on the same date returns the existing snapshot. The same values observed on a later date are a
new, meaningful time-series point.

## Rationale

GitHub exposes the current Repository counters, not an authoritative daily star history for every
past date. Reconstructing prior values would create evidence the Observatory never observed.
Daily forward snapshots provide a simple reproducible series whose gaps remain visible.

## Consequences

- First observation date equals historical coverage start.
- A missed day remains missing and is not interpolated in Silver.
- Stars are current `stargazers_count`; `watchers_count` is not treated as another metric.
- No individual Stargazer history, Trend Score, momentum, or inferred backfill is collected.
