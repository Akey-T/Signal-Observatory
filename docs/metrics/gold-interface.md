# Gold metric interface

E01 defines only the `GoldMetric` value and `GoldMetricReader` query boundary. A future metric must persist or expose:

- topic ID;
- metric name;
- UTC window start and end;
- numeric value;
- definition version;
- provenance linking the result to persisted Silver/Bronze inputs.

Metric definitions, late-data behavior, aggregation cadence, and backfill rules must be documented before implementation. Trend Score is intentionally not defined in E01.
