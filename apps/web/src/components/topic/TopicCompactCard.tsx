import { Link } from "react-router-dom";

import { categoryName } from "../../lib/topics";
import type { Category, Topic } from "../../types/api";

export function TopicCompactCard({
  topic,
  categories,
}: {
  topic: Topic;
  categories: Category[];
}) {
  const configuredSources = topic.sources.filter(
    (source) => source.enabled,
  ).length;
  return (
    <Link className="compact-topic" to={`/topics/${topic.slug}`}>
      <span>
        <strong>{topic.canonical_name}</strong>
        <small>{categoryName(topic.category, categories)}</small>
      </span>
      <span className="compact-topic__sources">
        {configuredSources} signal{" "}
        {configuredSources === 1 ? "channel" : "channels"}
      </span>
    </Link>
  );
}
