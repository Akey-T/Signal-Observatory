import type { ReactNode } from "react";

import type { SignalChannel, SignalChannelState } from "../../lib/channels";
import { formatRegistryDate } from "../../lib/format";
import type { SourceMapping, TopicResearch } from "../../types/api";
import { SignalChannelCard } from "./SignalChannelCard";

type ResearchObservationsProps = {
  channel: SignalChannel;
  mapping?: SourceMapping;
  data: TopicResearch | null;
  error: Error | null;
  loading: boolean;
  onRetry: () => void;
};

function researchState(
  mapping: SourceMapping | undefined,
  data: TopicResearch | null,
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

export function ResearchObservations({
  channel,
  mapping,
  data,
  error,
  loading,
  onRetry,
}: ResearchObservationsProps) {
  const state = researchState(mapping, data, error);
  const hasHistory =
    data !== null && (data.state === "live" || data.state === "degraded");

  return (
    <SignalChannelCard channel={channel} mapping={mapping} state={state}>
      {loading && mapping ? (
        <p className="research-card__note">Checking collector state…</p>
      ) : null}
      {error && mapping ? (
        <div className="research-card__error" role="status">
          <p>Research observations are temporarily unavailable.</p>
          <button className="button button--secondary" onClick={onRetry}>
            Retry Research
          </button>
        </div>
      ) : null}
      {data && mapping && data.state === "not_initialized" ? (
        <p className="research-card__note">
          Configured in the Registry; no successful arXiv collection yet.
        </p>
      ) : null}
      {hasHistory && data ? (
        <>
          <div className="research-card__metrics" aria-label="Research metrics">
            {metric("Papers · 7 days", data.summary.papers_7d)}
            {metric("Papers · 30 days", data.summary.papers_30d)}
            {metric("Authors · 30 days", data.summary.unique_authors_30d)}
          </div>
          <p className="research-card__observed">
            Last observed:{" "}
            {data.last_observed_at
              ? formatRegistryDate(data.last_observed_at)
              : "No papers observed"}
          </p>
          {data.state === "degraded" ? (
            <p className="research-card__warning">
              The latest collection did not complete. Persisted history remains
              available below.
            </p>
          ) : null}
        </>
      ) : null}
    </SignalChannelCard>
  );
}

export function LatestResearch({ data }: { data: TopicResearch | null }) {
  const hasHistory =
    data !== null && (data.state === "live" || data.state === "degraded");
  if (!hasHistory) return null;

  return (
    <section
      className="latest-research"
      aria-labelledby="latest-research-title"
    >
      <div className="latest-research__heading">
        <div>
          <p className="kicker">Persisted Silver observations</p>
          <h3 id="latest-research-title">Latest Research</h3>
        </div>
        <p>{data.summary.papers_total.toLocaleString()} matched papers total</p>
      </div>
      {data.latest_papers.length === 0 ? (
        <div className="research-empty">
          <strong>Collector live; no matched papers observed yet.</strong>
          <p>A zero count is a valid result for the current topic mapping.</p>
        </div>
      ) : (
        <div className="research-paper-list">
          {data.latest_papers.map((paper) => (
            <article className="research-paper" key={paper.arxiv_id}>
              <div className="research-paper__meta">
                <span>{paper.primary_category}</span>
                <time dateTime={paper.published_at}>
                  {formatRegistryDate(paper.published_at)}
                </time>
              </div>
              <h4>
                <a href={paper.abs_url} rel="noreferrer" target="_blank">
                  {paper.title}
                </a>
              </h4>
              <p className="research-paper__authors">
                {paper.authors.join(", ")}
              </p>
              <p className="research-paper__abstract">{paper.abstract}</p>
              <a
                className="research-paper__link"
                href={paper.abs_url}
                rel="noreferrer"
                target="_blank"
              >
                View official arXiv record <span aria-hidden="true">↗</span>
              </a>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
