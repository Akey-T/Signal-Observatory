import type { RegistryStatus } from "../../types/api";

type RegistryStatsProps = {
  status: RegistryStatus;
  categoryCount: number;
};

export function RegistryStats({ status, categoryCount }: RegistryStatsProps) {
  const stats = [
    [status.topic_count, "Monitored topics"],
    [categoryCount, "Categories"],
    [status.source_mapping_count, "Signal mappings"],
    [status.warnings, "Registry warnings"],
  ] as const;

  return (
    <div className="registry-stats" aria-label="Topic Registry statistics">
      {stats.map(([value, label]) => (
        <div className="registry-stat" key={label}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
      <div className="registry-stat registry-stat--version">
        <strong>v{status.version}</strong>
        <span>Registry version</span>
      </div>
    </div>
  );
}
