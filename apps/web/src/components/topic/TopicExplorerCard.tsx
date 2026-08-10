import { Link } from "react-router-dom";

import { signalChannels } from "../../lib/channels";
import { categoryName } from "../../lib/topics";
import { titleCase } from "../../lib/format";
import type { Category, Topic } from "../../types/api";

export function TopicExplorerCard({
  topic,
  categories,
}: {
  topic: Topic;
  categories: Category[];
}) {
  const sourceNames = signalChannels
    .filter((channel) =>
      topic.sources.some(
        (mapping) => mapping.enabled && mapping.source === channel.source,
      ),
    )
    .map((channel) => channel.sourceLabel);

  return (
    <article className="explorer-topic-card">
      <div className="explorer-topic-card__topline">
        <span>{categoryName(topic.category, categories)}</span>
        <span className={`topic-status topic-status--${topic.status}`}>
          {titleCase(topic.status)}
        </span>
      </div>
      <h2>{topic.canonical_name}</h2>
      <p>{topic.description}</p>
      <dl>
        <div>
          <dt>Monitoring priority</dt>
          <dd>{topic.monitoring_priority}</dd>
        </div>
        <div>
          <dt>Configured channels</dt>
          <dd>{sourceNames.length > 0 ? sourceNames.join(" · ") : "None"}</dd>
        </div>
        <div>
          <dt>Aliases</dt>
          <dd>
            {topic.aliases.length > 0
              ? topic.aliases
                  .slice(0, 3)
                  .map((alias) => alias.value)
                  .join(" · ")
              : "No aliases"}
          </dd>
        </div>
      </dl>
      <Link className="text-link" to={`/topics/${topic.slug}`}>
        View topic <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}
