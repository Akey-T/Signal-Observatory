import { Link, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { PageError, PageLoading } from "../components/layout/PageState";
import {
  LatestResearch,
  ResearchObservations,
} from "../components/signals/ResearchObservations";
import { SignalChannelCard } from "../components/signals/SignalChannelCard";
import { useRegistry } from "../context/RegistryContext";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useResearchQuery, useTopicQuery } from "../hooks/useTopicData";
import { mappingForChannel, signalChannels } from "../lib/channels";
import { categoryPath } from "../lib/topics";
import { titleCase } from "../lib/format";

export function TopicDetailPage() {
  const { slug = "" } = useParams();
  const topic = useTopicQuery(slug);
  const research = useResearchQuery(slug);
  const registry = useRegistry();
  useDocumentTitle(
    topic.data
      ? `${topic.data.canonical_name} · Signal Observatory`
      : "Topic · Signal Observatory",
  );

  if (topic.loading || registry.loading) {
    return (
      <div className="page-container detail-page">
        <PageLoading label="Loading topic record" />
      </div>
    );
  }

  if (topic.error || registry.error || topic.data === null) {
    const missing =
      topic.error instanceof ApiError && topic.error.status === 404;
    return (
      <div className="page-container detail-page">
        <PageError
          title={missing ? "This monitored topic was not found." : undefined}
          message={
            missing
              ? "The slug is not present in the synchronized Topic Registry."
              : undefined
          }
          onRetry={() => {
            registry.retry();
            topic.retry();
          }}
        />
        <Link className="text-link" to="/topics">
          <span aria-hidden="true">←</span> Return to Topic Explorer
        </Link>
      </div>
    );
  }

  const topicData = topic.data;
  const categoryBreadcrumb = categoryPath(
    topicData.category,
    registry.categories,
  );
  const configuredSources = topicData.sources.filter(
    (mapping) => mapping.enabled,
  );

  return (
    <article className="detail-page page-container">
      <Link className="back-link" to="/topics">
        <span aria-hidden="true">←</span> Topic Explorer
      </Link>

      <header className="topic-detail-hero">
        <nav className="category-breadcrumb" aria-label="Topic category">
          {categoryBreadcrumb.map((category, index) => (
            <span key={category.slug}>
              {index > 0 ? <i aria-hidden="true">/</i> : null}
              {category.name}
            </span>
          ))}
        </nav>
        <div className="topic-detail-hero__title">
          <div>
            <p className="kicker">Canonical topic</p>
            <h1>{topicData.canonical_name}</h1>
          </div>
          <span className={`topic-status topic-status--${topicData.status}`}>
            {titleCase(topicData.status)}
          </span>
        </div>
        <p className="topic-detail-hero__description">
          {topicData.description}
        </p>
        <div className="priority-explainer">
          <strong>{topicData.monitoring_priority} / 100</strong>
          <span>
            Monitoring Priority
            <small>
              Editorial scheduling priority used by the observatory. It is not
              popularity or trend strength.
            </small>
          </span>
        </div>
      </header>

      <section
        className="detail-section"
        aria-labelledby="monitoring-channels-title"
      >
        <div className="detail-section__heading">
          <div>
            <p className="kicker">Configuration</p>
            <h2 id="monitoring-channels-title">Monitoring Channels</h2>
          </div>
          <p>
            Configured means the Registry contains an explicit source mapping.
            It does not mean a collector is live.
          </p>
        </div>
        <div className="signal-channel-grid">
          {signalChannels.map((channel) => {
            const mapping = mappingForChannel(topicData.sources, channel);
            return (
              <SignalChannelCard
                channel={channel}
                key={channel.key}
                mapping={mapping}
                showMappingDetails
                state={mapping ? "configured" : "not_configured"}
              />
            );
          })}
        </div>
      </section>

      <div className="detail-two-column">
        <section
          className="detail-section aliases-section"
          aria-labelledby="aliases-title"
        >
          <p className="kicker">Identity</p>
          <h2 id="aliases-title">Aliases</h2>
          {topicData.aliases.length > 0 ? (
            <ul className="alias-list">
              {topicData.aliases.map((alias) => (
                <li key={alias.normalized_alias}>
                  <strong>{alias.value}</strong>
                  <span>{titleCase(alias.type)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted-copy">No curated aliases are registered.</p>
          )}
        </section>

        <section
          className="detail-section metadata-section"
          aria-labelledby="metadata-title"
        >
          <p className="kicker">Administrative record</p>
          <h2 id="metadata-title">Registry Information</h2>
          <dl className="metadata-list">
            <div>
              <dt>Status</dt>
              <dd>{titleCase(topicData.status)}</dd>
            </div>
            <div>
              <dt>Category</dt>
              <dd>
                {categoryBreadcrumb
                  .map((category) => category.name)
                  .join(" / ")}
              </dd>
            </div>
            <div>
              <dt>Monitoring priority</dt>
              <dd>{topicData.monitoring_priority}</dd>
            </div>
            <div>
              <dt>Configured sources</dt>
              <dd>{configuredSources.length}</dd>
            </div>
            <div>
              <dt>Alias count</dt>
              <dd>{topicData.aliases.length}</dd>
            </div>
            <div>
              <dt>Registry version</dt>
              <dd>
                v{topicData.registry_version ?? registry.status?.version ?? "—"}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <section
        className="detail-section observations-section"
        aria-labelledby="observations-title"
      >
        <div className="detail-section__heading">
          <div>
            <p className="kicker">Future signal surface</p>
            <h2 id="observations-title">Observations</h2>
          </div>
          <p>
            Research reflects persisted arXiv observations. The other channels
            remain configuration-only until their collectors are implemented.
          </p>
        </div>
        <div className="signal-channel-grid signal-channel-grid--observations">
          {signalChannels.map((channel) => {
            const mapping = mappingForChannel(topicData.sources, channel);
            if (channel.key === "research") {
              return (
                <ResearchObservations
                  channel={channel}
                  data={research.data}
                  error={research.error}
                  key={channel.key}
                  loading={research.loading}
                  mapping={mapping}
                  onRetry={research.retry}
                />
              );
            }
            return (
              <SignalChannelCard
                channel={channel}
                key={channel.key}
                mapping={mapping}
                state={mapping ? "not_collecting" : "not_configured"}
              />
            );
          })}
        </div>
        <LatestResearch data={research.data} />
      </section>
    </article>
  );
}
