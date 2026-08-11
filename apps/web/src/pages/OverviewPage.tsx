import { Link } from "react-router-dom";

import { PageError, PageLoading } from "../components/layout/PageState";
import { RegistryStats } from "../components/registry/RegistryStats";
import { RegistryStatusPanel } from "../components/registry/RegistryStatusPanel";
import { FeaturedTopicCard } from "../components/topic/FeaturedTopicCard";
import { TopicCompactCard } from "../components/topic/TopicCompactCard";
import { TopicUniverseSection } from "../components/topic/TopicUniverseSection";
import { useRegistry } from "../context/RegistryContext";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  useArxivStatusQuery,
  useGithubStatusQuery,
  useTopicsQuery,
} from "../hooks/useTopicData";
import { selectFeaturedTopics, selectSupportingTopics } from "../lib/topics";

const observationPath = [
  ["Research", "arXiv"],
  ["Developer", "GitHub"],
  ["Community", "Hacker News"],
  ["Public", "Wikipedia"],
] as const;

export function OverviewPage() {
  useDocumentTitle("Signal Observatory");
  const registry = useRegistry();
  const topics = useTopicsQuery({ limit: 500, offset: 0 });
  const arxiv = useArxivStatusQuery();
  const github = useGithubStatusQuery();
  const researchLive =
    arxiv.data?.collector_state === "healthy" &&
    arxiv.data.last_successful_run_at !== null;
  const developerLive =
    github.data?.collector_state === "healthy" &&
    github.data.last_successful_snapshot_at !== null;
  const retry = () => {
    registry.retry();
    topics.retry();
  };
  const topicItems = topics.data?.items ?? [];
  const featured = selectFeaturedTopics(topicItems, registry.categories);
  const supporting = selectSupportingTopics(topicItems, featured, 30);

  return (
    <>
      <section
        className="overview-hero page-container"
        aria-labelledby="overview-title"
      >
        <div className="overview-hero__copy">
          <p className="kicker">Signal Observatory</p>
          <h1 id="overview-title">
            Watching technology before it becomes obvious.
          </h1>
          <p className="overview-hero__lede">
            A long-term observatory tracking how technology moves from research
            to developers, technical communities and public attention.
          </p>
          <div className="truth-note">
            <span aria-hidden="true" />
            Topic Registry ready · Research collector{" "}
            {researchLive ? "live" : "not live"} · Developer collector{" "}
            {developerLive ? "live" : "not live"}
          </div>
        </div>

        <div
          className="observation-path"
          aria-label="Future observation channels"
        >
          {observationPath.map(([stage, source], index) => (
            <div className="observation-path__step" key={stage}>
              <span>0{index + 1}</span>
              <strong>{stage}</strong>
              <em>{source}</em>
              <small>
                {stage === "Research"
                  ? researchLive
                    ? "arXiv · Live"
                    : "arXiv · Not live"
                  : stage === "Developer"
                    ? developerLive
                      ? "GitHub · Live"
                      : "GitHub · Not live"
                    : "Configured / ready"}
              </small>
            </div>
          ))}
        </div>

        {registry.status ? (
          <RegistryStats
            status={registry.status}
            categoryCount={registry.categories.length}
          />
        ) : registry.error ? (
          <div className="registry-stats-unavailable" role="status">
            Registry status unavailable · No fallback numbers shown
          </div>
        ) : (
          <div
            className="registry-stats-skeleton"
            aria-label="Loading Registry statistics"
          />
        )}
      </section>

      {topics.loading || registry.loading ? (
        <div className="page-container">
          <PageLoading label="Loading monitored topics" />
        </div>
      ) : topics.error || registry.error ? (
        <div className="page-container">
          <PageError onRetry={retry} />
        </div>
      ) : topics.data && registry.status ? (
        <>
          <section
            className="featured-section section-frame"
            aria-labelledby="featured-title"
          >
            <div className="section-intro">
              <div>
                <p className="kicker">Topics we&apos;re watching</p>
                <h2 id="featured-title">
                  Three editorially prioritized topics.
                </h2>
              </div>
              <p>
                Selected deterministically by active status, monitoring priority
                and domain diversity. Featured does not mean trending.
              </p>
            </div>
            <div className="featured-grid">
              {featured.map((topic, index) => (
                <FeaturedTopicCard
                  categories={registry.categories}
                  key={topic.topic_id}
                  primary={index === 0}
                  topic={topic}
                />
              ))}
            </div>
          </section>

          <section
            className="supporting-section section-frame"
            aria-labelledby="supporting-title"
          >
            <div className="section-intro section-intro--compact">
              <div>
                <p className="kicker">Also watching</p>
                <h2 id="supporting-title">
                  A broader field of monitored technology.
                </h2>
              </div>
              <p>
                Showing {supporting.length} of {topics.data.total} monitored
                topics.
              </p>
            </div>
            <div className="compact-topic-grid">
              {supporting.map((topic) => (
                <TopicCompactCard
                  categories={registry.categories}
                  key={topic.topic_id}
                  topic={topic}
                />
              ))}
            </div>
            <Link className="section-cta" to="/topics">
              Explore all {topics.data.total} topics{" "}
              <span aria-hidden="true">→</span>
            </Link>
          </section>

          <TopicUniverseSection
            categories={registry.categories}
            topics={topicItems}
          />
          <RegistryStatusPanel
            categoryCount={registry.categories.length}
            collectorError={arxiv.error !== null}
            collectorStatus={arxiv.data}
            githubError={github.error !== null}
            githubStatus={github.data}
            status={registry.status}
          />
        </>
      ) : null}
    </>
  );
}
