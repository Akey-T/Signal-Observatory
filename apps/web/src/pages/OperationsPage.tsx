import { useMemo, useState } from "react";

import { CoverageBadge } from "../components/operations/CoverageBadge";
import { PageError, PageLoading } from "../components/layout/PageState";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  useCoverageQuery,
  useOperationsQuery,
} from "../hooks/useOperationsData";
import { formatRegistryDate, titleCase } from "../lib/format";
import type {
  CoverageItem,
  CoverageStatus,
  SourceOperationalHealth,
  OperationsOverview,
} from "../types/api";

const coverageOptions: Array<CoverageStatus | "all"> = [
  "all",
  "complete",
  "partial",
  "forward_only",
  "empty",
  "unknown",
];

function numberDetail(source: SourceOperationalHealth, key: string): number {
  const value = source.details[key];
  return typeof value === "number" ? value : 0;
}

function dateDetail(
  source: SourceOperationalHealth,
  key: string,
): string | null {
  const value = source.details[key];
  return typeof value === "string" ? value : null;
}

function SourceCard({
  source,
  coverage,
}: {
  source: SourceOperationalHealth;
  coverage: CoverageItem[];
}) {
  const counts = coverage.reduce<Record<string, number>>((result, item) => {
    result[item.coverage_status] = (result[item.coverage_status] ?? 0) + 1;
    return result;
  }, {});
  const state = source.implemented
    ? titleCase(source.collector_state)
    : "Not collecting";

  return (
    <article className="operations-source-card">
      <header>
        <div>
          <span>{source.label}</span>
          <h3>{source.display_name}</h3>
        </div>
        <strong
          className={`health-state health-state--${source.collector_state}`}
        >
          {state}
        </strong>
      </header>
      {source.source === "arxiv" ? (
        <dl>
          <div>
            <dt>Latest run</dt>
            <dd>{titleCase(source.latest_run_status ?? "not initialized")}</dd>
          </div>
          <div>
            <dt>Last successful observation</dt>
            <dd>
              {source.last_successful_run_at
                ? formatRegistryDate(source.last_successful_run_at)
                : "—"}
            </dd>
          </div>
          <div>
            <dt>Topics configured</dt>
            <dd>{source.active_mappings}</dd>
          </div>
          <div>
            <dt>Complete / Partial / Empty</dt>
            <dd>
              {counts.complete ?? 0} / {counts.partial ?? 0} /{" "}
              {counts.empty ?? 0}
            </dd>
          </div>
        </dl>
      ) : null}
      {source.source === "github" ? (
        <dl>
          <div>
            <dt>Tracked repositories</dt>
            <dd>{numberDetail(source, "tracked_repositories")}</dd>
          </div>
          <div>
            <dt>Snapshot dates</dt>
            <dd>{numberDetail(source, "snapshot_dates")}</dd>
          </div>
          <div>
            <dt>Latest snapshot</dt>
            <dd>
              {dateDetail(source, "latest_snapshot")
                ? formatRegistryDate(
                    dateDetail(source, "latest_snapshot") ?? "",
                  )
                : "—"}
            </dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>Forward only</dd>
          </div>
        </dl>
      ) : null}
      {!source.implemented ? (
        <p className="operations-source-card__empty">
          No collector is implemented. Registry mappings remain configuration
          only.
        </p>
      ) : null}
      <footer>
        <span>Freshness · {titleCase(source.freshness)}</span>
        <span>Errors last run · {source.errors_last_run}</span>
      </footer>
    </article>
  );
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = value / 1024;
  let unit = units[0];
  for (const candidate of units.slice(1)) {
    if (amount < 1024) break;
    amount /= 1024;
    unit = candidate;
  }
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${unit}`;
}

function formatAge(seconds: number): string {
  if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours`;
  return `${Math.floor(seconds / 86400)} days`;
}

function DataProtectionSection({
  data,
}: {
  data: OperationsOverview["data_protection"];
}) {
  const verified = data.latest_verified_backup;
  const latest = data.latest_backup;
  const drill = data.latest_restore_drill;
  const backupState = latest?.verification_state ?? "unverified";
  const stateClass =
    backupState === "pass"
      ? "healthy"
      : backupState === "warning"
        ? "degraded"
        : backupState === "fail"
          ? "failed"
          : "not_initialized";

  return (
    <section
      className="operations-section data-protection"
      aria-labelledby="data-protection-title"
    >
      <div className="operations-section__heading">
        <div>
          <p className="kicker">Recovery unit</p>
          <h2 id="data-protection-title">Data Protection</h2>
        </div>
        <p>
          PostgreSQL, immutable Raw, Registry configuration and provenance are
          verified together.
        </p>
      </div>
      {!verified ? (
        <div className="data-protection__empty">
          <h3>No verified backup yet.</h3>
          <p>
            Operations will report real backup evidence after a verified run.
          </p>
        </div>
      ) : (
        <dl className="data-protection__grid">
          <div>
            <dt>Latest verified backup</dt>
            <dd>{formatRegistryDate(verified.completed_at)}</dd>
            <small>{verified.backup_id}</small>
          </div>
          <div>
            <dt>Verification</dt>
            <dd>
              <span className={`health-state health-state--${stateClass}`}>
                {titleCase(backupState)}
              </span>
            </dd>
            <small>
              Age {formatAge(data.latest_verified_backup_age_seconds ?? 0)}
            </small>
          </div>
          <div>
            <dt>Recovery payload</dt>
            <dd>{formatBytes(verified.total_backup_bytes)}</dd>
            <small>
              DB {formatBytes(verified.database_size_bytes)} · Raw{" "}
              {verified.raw_objects} objects
            </small>
          </div>
          <div>
            <dt>Latest restore drill</dt>
            <dd
              className={
                drill?.result === "fail"
                  ? "data-protection__failure"
                  : undefined
              }
            >
              {drill ? titleCase(drill.result) : "Not run"}
            </dd>
            <small>
              {drill
                ? formatRegistryDate(drill.restore_completed_at)
                : "No restore drill recorded."}
            </small>
          </div>
        </dl>
      )}
      {latest?.verification_state === "fail" ? (
        <p className="data-protection__alert">
          The latest backup failed verification. The previous verified backup
          remains the recovery candidate.
        </p>
      ) : null}
    </section>
  );
}

export function OperationsPage() {
  const operations = useOperationsQuery();
  const coverage = useCoverageQuery({ limit: 1000 });
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<CoverageStatus | "all">(
    "all",
  );
  useDocumentTitle("Operations · Signal Observatory");

  const filteredCoverage = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (coverage.data?.items ?? []).filter(
      (item) =>
        (sourceFilter === "all" || item.source === sourceFilter) &&
        (statusFilter === "all" || item.coverage_status === statusFilter) &&
        (!query ||
          item.topic.canonical_name.toLocaleLowerCase().includes(query) ||
          item.topic.slug.toLocaleLowerCase().includes(query)),
    );
  }, [coverage.data, search, sourceFilter, statusFilter]);

  const matrixRows = useMemo(() => {
    const rows = new Map<
      string,
      { name: string; research?: CoverageItem; developer?: CoverageItem }
    >();
    for (const item of filteredCoverage) {
      const row = rows.get(item.topic.slug) ?? {
        name: item.topic.canonical_name,
      };
      if (item.source === "arxiv") row.research = item;
      if (item.source === "github") row.developer = item;
      rows.set(item.topic.slug, row);
    }
    return [...rows.entries()].sort((left, right) =>
      left[1].name.localeCompare(right[1].name),
    );
  }, [filteredCoverage]);

  if (operations.loading || coverage.loading) {
    return (
      <div className="page-container operations-page">
        <PageLoading label="Loading observatory operations" />
      </div>
    );
  }
  if (
    operations.error ||
    coverage.error ||
    !operations.data ||
    !coverage.data
  ) {
    return (
      <div className="page-container operations-page">
        <PageError
          title="Operational health could not be loaded."
          message="No health or coverage values have been substituted."
          onRetry={() => {
            operations.retry();
            coverage.retry();
          }}
        />
      </div>
    );
  }

  const data = operations.data;
  const coverageBySource = (source: string) =>
    coverage.data?.items.filter((item) => item.source === source) ?? [];

  return (
    <article className="operations-page page-container">
      <header className="operations-hero">
        <p className="kicker">System reliability</p>
        <h1>Observatory Operations</h1>
        <p>Collection health, source coverage and data quality.</p>
      </header>

      <section
        className="observatory-state"
        aria-labelledby="observatory-state-title"
      >
        <div>
          <span>Observatory state</span>
          <h2 id="observatory-state-title">{titleCase(data.overall_state)}</h2>
        </div>
        <p>{data.explanation}</p>
      </section>

      <DataProtectionSection data={data.data_protection} />

      <section className="operations-section" aria-labelledby="sources-title">
        <div className="operations-section__heading">
          <div>
            <p className="kicker">Collectors</p>
            <h2 id="sources-title">Source Status</h2>
          </div>
          <p>Collector health is independent from historical data coverage.</p>
        </div>
        <div className="operations-source-grid">
          {data.sources.map((source) => (
            <SourceCard
              coverage={coverageBySource(source.source)}
              key={source.source}
              source={source}
            />
          ))}
        </div>
      </section>

      <section className="operations-section" aria-labelledby="quality-title">
        <div className="operations-section__heading">
          <div>
            <p className="kicker">Persisted checks</p>
            <h2 id="quality-title">Data Quality</h2>
          </div>
          <p>
            Unknown integrity counts remain unknown until a Raw sample is
            verified.
          </p>
        </div>
        <dl className="quality-grid">
          <div>
            <dt>Ingestion errors · 24h</dt>
            <dd>{data.data_quality.ingestion_errors_last_24h}</dd>
          </div>
          <div>
            <dt>Partial mappings</dt>
            <dd>{data.data_quality.partial_mappings}</dd>
          </div>
          <div>
            <dt>Stale cursors</dt>
            <dd>{data.data_quality.stale_cursors}</dd>
          </div>
          <div>
            <dt>Missing snapshot dates</dt>
            <dd>{data.data_quality.missing_snapshot_dates}</dd>
          </div>
          <div>
            <dt>Raw checksum failures</dt>
            <dd>{data.data_quality.raw_checksum_failures ?? "Not verified"}</dd>
          </div>
          <div>
            <dt>Registry warnings</dt>
            <dd>{data.data_quality.registry_warnings}</dd>
          </div>
          <div>
            <dt>Missed schedules · 24h</dt>
            <dd>{data.data_quality.scheduler_missed_last_24h}</dd>
          </div>
          <div>
            <dt>Interrupted schedules · 24h</dt>
            <dd>{data.data_quality.scheduler_interrupted_last_24h}</dd>
          </div>
          <div>
            <dt>Partial schedules · 24h</dt>
            <dd>{data.data_quality.scheduler_partial_last_24h}</dd>
          </div>
          <div>
            <dt>Failed schedules · 24h</dt>
            <dd>{data.data_quality.scheduler_failed_last_24h}</dd>
          </div>
        </dl>
      </section>

      <section
        className="operations-section coverage-matrix"
        aria-labelledby="matrix-title"
      >
        <div className="operations-section__heading">
          <div>
            <p className="kicker">Topic × Source</p>
            <h2 id="matrix-title">Coverage Matrix</h2>
          </div>
          <p>
            Statuses and dates are derived facts. No completeness percentage is
            displayed.
          </p>
        </div>
        <div className="coverage-filters">
          <label>
            Search topic
            <input
              aria-label="Search coverage topics"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Topic name or slug"
              type="search"
              value={search}
            />
          </label>
          <label>
            Source
            <select
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
            >
              <option value="all">All sources</option>
              <option value="arxiv">Research / arXiv</option>
              <option value="github">Developer / GitHub</option>
            </select>
          </label>
          <label>
            Coverage state
            <select
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value as CoverageStatus | "all")
              }
            >
              {coverageOptions.map((option) => (
                <option key={option} value={option}>
                  {titleCase(option)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="coverage-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Topic</th>
                <th>Research</th>
                <th>Developer</th>
              </tr>
            </thead>
            <tbody>
              {matrixRows.map(([slug, row]) => (
                <tr key={slug}>
                  <th scope="row">{row.name}</th>
                  <td>
                    {row.research ? <CoverageCell item={row.research} /> : "—"}
                  </td>
                  <td>
                    {row.developer ? (
                      <CoverageCell item={row.developer} />
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {matrixRows.length === 0 ? (
          <p className="coverage-empty">
            No Topic × Source coverage matches these filters.
          </p>
        ) : null}
      </section>
    </article>
  );
}

function CoverageCell({ item }: { item: CoverageItem }) {
  return (
    <div className="coverage-cell">
      <CoverageBadge status={item.coverage_status} />
      <small>
        {item.coverage_start
          ? `${formatRegistryDate(item.coverage_start)} → ${formatRegistryDate(item.coverage_end ?? item.coverage_start)}`
          : (item.partial_reason ?? "No observed date")}
      </small>
    </div>
  );
}
