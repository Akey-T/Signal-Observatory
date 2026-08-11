import type { ReactNode } from "react";

import type { SignalChannel, SignalChannelState } from "../../lib/channels";
import { formatRegistryDate } from "../../lib/format";
import type { SourceMapping, TopicDevelopment } from "../../types/api";
import { SignalChannelCard } from "./SignalChannelCard";

type DeveloperObservationsProps = {
  channel: SignalChannel;
  mapping?: SourceMapping;
  data: TopicDevelopment | null;
  error: Error | null;
  loading: boolean;
  onRetry: () => void;
};

function developerState(
  mapping: SourceMapping | undefined,
  data: TopicDevelopment | null,
  error: Error | null,
): SignalChannelState {
  if (!mapping) return "not_configured";
  if (error) return "error";
  if (data?.state === "live") return "live";
  if (data?.state === "degraded") return "degraded";
  return "not_collecting";
}

function metric(label: string, value: number): ReactNode {
  return (
    <div>
      <strong>{value.toLocaleString()}</strong>
      <span>{label}</span>
    </div>
  );
}

function delta(value: number | null): string {
  if (value === null) return "Baseline only";
  return value > 0 ? `+${value.toLocaleString()}` : value.toLocaleString();
}

export function DeveloperObservations({
  channel,
  mapping,
  data,
  error,
  loading,
  onRetry,
}: DeveloperObservationsProps) {
  const state = developerState(mapping, data, error);
  const hasHistory =
    data !== null && (data.state === "live" || data.state === "degraded");

  return (
    <SignalChannelCard channel={channel} mapping={mapping} state={state}>
      {loading && mapping ? (
        <p className="research-card__note">Checking collector state…</p>
      ) : null}
      {error && mapping ? (
        <div className="research-card__error" role="status">
          <p>Developer observations are temporarily unavailable.</p>
          <button className="button button--secondary" onClick={onRetry}>
            Retry Developer
          </button>
        </div>
      ) : null}
      {data && mapping && data.state === "not_initialized" ? (
        <p className="research-card__note">
          Configured in the Registry; no successful GitHub snapshot yet.
        </p>
      ) : null}
      {hasHistory && data ? (
        <>
          <div
            className="research-card__metrics developer-card__metrics"
            aria-label="Developer metrics"
          >
            {metric("Repositories", data.summary.repositories_tracked)}
            {metric("Stars", data.summary.stars_total)}
            {metric("Forks", data.summary.forks_total)}
            {metric("Pushed · 30 days", data.summary.repositories_pushed_30d)}
          </div>
          <p className="developer-card__delta">
            Snapshot change:{" "}
            {delta(data.summary.stars_delta_since_previous_snapshot)} stars ·{" "}
            {delta(data.summary.forks_delta_since_previous_snapshot)} forks
          </p>
          <p className="research-card__observed">
            Last snapshot:{" "}
            {data.last_snapshot_at
              ? formatRegistryDate(data.last_snapshot_at)
              : "No snapshot observed"}
          </p>
          {data.state === "degraded" ? (
            <p className="research-card__warning">
              The latest snapshot run did not complete. Persisted history
              remains available below.
            </p>
          ) : null}
        </>
      ) : null}
    </SignalChannelCard>
  );
}

export function TrackedRepositories({
  data,
}: {
  data: TopicDevelopment | null;
}) {
  const hasHistory =
    data !== null && (data.state === "live" || data.state === "degraded");
  if (!hasHistory) return null;

  return (
    <section
      className="tracked-repositories"
      aria-labelledby="tracked-repositories-title"
    >
      <div className="latest-research__heading">
        <div>
          <p className="kicker">Persisted GitHub observations</p>
          <h3 id="tracked-repositories-title">Tracked Repositories</h3>
        </div>
        <p>
          {data.summary.repositories_tracked.toLocaleString()} repositories
          tracked
        </p>
      </div>
      {data.top_repositories.length === 0 ? (
        <div className="research-empty">
          <strong>Collector live; no repositories matched this Topic.</strong>
          <p>A zero count is a valid result for the curated GitHub mapping.</p>
        </div>
      ) : (
        <div className="repository-list">
          {data.top_repositories.map((repository) => (
            <article
              className="repository-row"
              key={repository.github_repository_id}
            >
              <div>
                <span className="repository-row__language">
                  {repository.language ?? "Language unavailable"}
                </span>
                <h4>
                  <a
                    href={repository.html_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {repository.full_name}
                  </a>
                </h4>
                <p>{repository.description ?? "No repository description."}</p>
              </div>
              <dl>
                <div>
                  <dt>Stars</dt>
                  <dd>{repository.stars?.toLocaleString() ?? "—"}</dd>
                </div>
                <div>
                  <dt>Forks</dt>
                  <dd>{repository.forks?.toLocaleString() ?? "—"}</dd>
                </div>
                <div>
                  <dt>Delta</dt>
                  <dd>{delta(repository.stars_delta)} stars</dd>
                </div>
              </dl>
              <details className="repository-evidence">
                <summary>Match evidence</summary>
                {repository.match_evidence.map((evidence) => (
                  <p
                    key={`${evidence.source_mapping_id}-${evidence.matched_query}`}
                  >
                    Query: <code>{evidence.matched_query}</code> · Rank{" "}
                    {evidence.discovery_rank} · Raw{" "}
                    {evidence.raw_checksum?.slice(0, 12) ?? "unavailable"}
                  </p>
                ))}
              </details>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
