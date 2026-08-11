import { Link } from "react-router-dom";

import type { TopicCoverage } from "../../types/api";
import { formatRegistryDate, titleCase } from "../../lib/format";
import { CoverageBadge } from "./CoverageBadge";

export function TopicCoverageSection({
  data,
  loading,
  error,
  onRetry,
}: {
  data: TopicCoverage | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  return (
    <section
      className="detail-section topic-coverage"
      aria-labelledby="coverage-title"
    >
      <div className="detail-section__heading">
        <div>
          <p className="kicker">Trust boundary</p>
          <h2 id="coverage-title">Data Coverage</h2>
        </div>
        <Link className="text-link" to="/operations">
          View operations <span aria-hidden="true">→</span>
        </Link>
      </div>
      {loading ? (
        <p className="muted-copy">Reading persisted coverage…</p>
      ) : null}
      {error ? (
        <div className="coverage-inline-error" role="alert">
          <p>Coverage is temporarily unavailable. No status was substituted.</p>
          <button className="text-button" type="button" onClick={onRetry}>
            Retry coverage
          </button>
        </div>
      ) : null}
      {data ? (
        <div className="topic-coverage-grid">
          {data.channels.map((channel) => (
            <article key={channel.channel}>
              <span>{channel.label}</span>
              {channel.coverage ? (
                <>
                  <CoverageBadge status={channel.coverage.coverage_status} />
                  <p>
                    {channel.coverage.coverage_start
                      ? `${formatRegistryDate(channel.coverage.coverage_start)} → ${formatRegistryDate(channel.coverage.coverage_end ?? channel.coverage.coverage_start)}`
                      : (channel.coverage.partial_reason ??
                        "No observed date yet.")}
                  </p>
                </>
              ) : (
                <>
                  <strong>Not started</strong>
                  <p>{titleCase(channel.source)} is not collecting.</p>
                </>
              )}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
