# Observation and Evidence Semantics

## Media Attention

Media Attention means:

> The amount or share of monitored media coverage associated with a configured Topic during a
> defined time window.

It is a measured source observation. It is not Public Opinion, Public Concern, Search Interest,
Event Importance, or Trend Score.

## Measurement is not evidence

An `AttentionObservation` records the measured value and its unit. `ObservationEvidence` stores
documents that help explain that value. Evidence count is never a substitute for the measured
value:

```text
numeric_value = 20,000 articles
evidence documents = 20 sampled articles
```

Both facts can be true. A future GDELT Timeline raw count must populate the measurement; an
ArticleList sample must populate evidence. The length of an evidence list cannot be interpreted as
the total media volume.

## Units and definition versions

Every metric declares a unit and definition version. Example fixture metrics are:

| Metric                  | Unit               | Meaning                                      |
| ----------------------- | ------------------ | -------------------------------------------- |
| `MEDIA_MATCH_COUNT`     | `articles`         | matched monitored media count                |
| `REFERENCE_PAGEVIEWS`   | `pageviews`        | reference-page view count                    |
| `COMMUNITY_STORY_COUNT` | `stories`          | community story count                        |
| `SEARCH_INTEREST`       | `normalized_index` | source-defined normalized index, not a count |

`TREND_SCORE`, `MOMENTUM`, `ACCELERATION`, `PUBLIC_ATTENTION_SCORE`, and
`PUBLIC_CONCERN_SCORE` are analytical concepts outside E05. Metric names are normalized
deterministically and analytical score names are rejected by the domain contract.

## Zero, missing, nullable, and partial

These states are not interchangeable:

| State                        | Interpretation                                                                          |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| `numeric_value = 0`, `VALID` | The interval was queried successfully and returned zero                                 |
| No Observation row           | The interval may be missing or not yet collected                                        |
| `numeric_value = NULL`       | The measurement is unavailable or not applicable; never silently zero                   |
| `PARTIAL`                    | Some required evidence or request component is unavailable while the row remains useful |

An Observation can be valid without any Evidence rows. An Observation can have a valid value while
its sampled evidence is unavailable. A missing interval must remain visible to the future Coverage
derivation; it must not be interpolated from adjacent windows.

## Windows and time

Attention measurements use `window_start` and `window_end`, not only a point timestamp. All stored
windows, publication times, event times, and observation times are timezone-aware UTC. A future
hourly collector should use closed UTC buckets and declare its lag/cadence in its source adapter.

## Coverage contract

Future adapters expose coverage strategy, expected-window duration, and observed/missing/partial
UTC windows to the existing `CoverageDeriver`. A successful latest interval does not prove
historical completeness. Bounded history, forward-only collection, missing windows, zero-result
windows, and partial intervals must remain distinguishable.
