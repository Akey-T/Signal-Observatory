import { formatRegistryDate } from "../../lib/format";
import type { RegistryStatus } from "../../types/api";

export function RegistryStatusPanel({
  status,
  categoryCount,
}: {
  status: RegistryStatus;
  categoryCount: number;
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
          These values describe the curated registry and its mappings. External
          collectors have not started, so no source is presented as live or
          healthy.
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
            <span>External collectors</span>
            <strong className="status-panel__pending">Not enabled</strong>
          </div>
          <p>
            Configured mappings are ready for future ingestion; they are not
            observations.
          </p>
        </div>
      </div>
    </section>
  );
}
