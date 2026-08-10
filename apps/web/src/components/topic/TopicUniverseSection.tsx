import { Link } from "react-router-dom";

import { buildTopicUniverse } from "../../lib/topics";
import type { Category, Topic } from "../../types/api";

export function TopicUniverseSection({
  topics,
  categories,
}: {
  topics: Topic[];
  categories: Category[];
}) {
  const groups = buildTopicUniverse(topics, categories);
  return (
    <section
      className="universe-section section-frame"
      aria-labelledby="universe-title"
    >
      <div className="section-intro">
        <div>
          <p className="kicker">Topic universe</p>
          <h2 id="universe-title">Five domains. One curated registry.</h2>
        </div>
        <p>
          Topics are organized for long-term observation across technology
          research, software, data, infrastructure and emerging systems.
        </p>
      </div>
      <div className="universe-grid">
        {groups.map((group, index) => (
          <article className="universe-group" key={group.category.slug}>
            <span className="universe-group__number">0{index + 1}</span>
            <div>
              <h3>{group.category.name}</h3>
              <p>{group.count} monitored topics</p>
            </div>
            <ul>
              {group.topics.map((topic) => (
                <li key={topic.topic_id}>
                  <Link to={`/topics/${topic.slug}`}>
                    {topic.canonical_name}
                  </Link>
                </li>
              ))}
            </ul>
            <Link
              className="universe-group__link"
              to={`/topics?category=${group.category.slug}`}
            >
              Explore domain <span aria-hidden="true">→</span>
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
