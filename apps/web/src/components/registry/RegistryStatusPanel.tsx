import { formatRegistryDate } from "../../lib/format";
import type { ArxivStatus, RegistryStatus } from "../../types/api";

export function RegistryStatusPanel({
  status,
  categoryCount,
  collectorStatus,
  collectorError,
}: {
  status: RegistryStatus;
  categoryCount: number;
  collectorStatus: ArxivStatus | null;
  collectorError: boolean;
}) {
  const entries = [
    ["Registry", `v${status.version}`],
    ["Topics", status.topic_count],
    ["Active", status.active_topics],
    ["Aliases", status.alias_count],
    ["Categories", categoryCount],
    ["Signal mappings", status.source_mapping_count],
    ["Warnings", status.warnings],
  ] as const;
  const collectorLabel = collectorError
    ? "Unavailable"
    : collectorStatus === null
      ? "Checking"
      : collectorStatus.collector_state === "healthy" &&
          collectorStatus.last_successful_run_at !== null
        ? "Live"
        : collectorStatus.collector_state === "degraded"
          ? "Degraded"
          : "Not initialized";

  return (
    <section
      className="status-section section-frame"
      aria-labelledby="status-title"
    >
      <div className="section-intro">
        <div>
          <p className="kicker">Observatory status</p>
          <h2 id="status-title">Registry health, not collector health.</h2>
        </div>
        <p>
          These metrics describe only the curated Registry and its mappings.
          Research collector state is reported separately and never changes
          Registry health.
        </p>
      </div>
      <div className="status-panel">
        <div className="status-panel__metrics">
          {entries.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
        <div className="status-panel__meta">
          <div>
            <span>Last registry sync</span>
            <strong>{formatRegistryDate(status.last_synced_at)}</strong>
          </div>
          <div>
            <span>Research collector</span>
            <strong
              className={
                collectorLabel === "Live"
                  ? "status-panel__live"
                  : "status-panel__pending"
              }
            >
              {collectorLabel}
            </strong>
          </div>
          <p>
            arXiv is the only implemented observation source. GitHub, Hacker
            News and Wikipedia mappings are not collecting yet.
          </p>
        </div>
      </div>
    </section>
  );
}
