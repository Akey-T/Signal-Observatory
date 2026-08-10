import { Link } from "react-router-dom";

import { mappingForChannel, signalChannels } from "../../lib/channels";
import { categoryName, categoryPath } from "../../lib/topics";
import { titleCase } from "../../lib/format";
import type { Category, Topic } from "../../types/api";

export function FeaturedTopicCard({
  topic,
  categories,
  primary = false,
}: {
  topic: Topic;
  categories: Category[];
  primary?: boolean;
}) {
  const path = categoryPath(topic.category, categories);
  const categoryLabel =
    path.length > 1
      ? path.map((category) => category.name).join(" · ")
      : categoryName(topic.category, categories);
  const selectedAliases = topic.aliases.slice(0, primary ? 3 : 2);

  return (
    <article
      className={`featured-topic${primary ? " featured-topic--primary" : ""}`}
      data-testid="featured-topic"
    >
      <div className="featured-topic__header">
        <span className="topic-category">{categoryLabel}</span>
        <span className="registry-badge">{titleCase(topic.status)}</span>
      </div>
      <div>
        <h3>{topic.canonical_name}</h3>
        <p className="featured-topic__description">{topic.description}</p>
      </div>
      <div className="featured-topic__facts">
        <div>
          <span>Monitoring priority</span>
          <strong>{topic.monitoring_priority} / 100</strong>
        </div>
        <div>
          <span>Curated aliases</span>
          <strong>{topic.aliases.length}</strong>
        </div>
        <div>
          <span>Configured sources</span>
          <strong>
            {topic.sources.filter((source) => source.enabled).length}
          </strong>
        </div>
      </div>
      {selectedAliases.length > 0 ? (
        <div className="alias-row" aria-label="Selected aliases">
          {selectedAliases.map((alias) => (
            <span key={alias.normalized_alias}>{alias.value}</span>
          ))}
        </div>
      ) : null}
      <div
        className="featured-channels"
        aria-label="Configured signal channels"
      >
        {signalChannels.map((channel) => {
          const configured =
            mappingForChannel(topic.sources, channel) !== undefined;
          return (
            <div key={channel.key}>
              <span>{channel.label}</span>
              <strong>{channel.sourceLabel}</strong>
              <em>{configured ? "Configured" : "Not configured"}</em>
            </div>
          );
        })}
      </div>
      <Link className="text-link" to={`/topics/${topic.slug}`}>
        Explore topic <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}
