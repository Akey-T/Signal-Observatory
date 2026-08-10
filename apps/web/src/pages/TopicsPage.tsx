import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { PageError, PageLoading } from "../components/layout/PageState";
import { Pagination } from "../components/topic/Pagination";
import { TopicExplorerCard } from "../components/topic/TopicExplorerCard";
import { useRegistry } from "../context/RegistryContext";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useTopicsQuery } from "../hooks/useTopicData";
import { categoryDescendantSlugs } from "../lib/topics";
import type { TopicStatus, TopicsQuery } from "../types/api";

const pageSize = 24;
const sourceOptions = [
  ["arxiv", "arXiv"],
  ["github", "GitHub"],
  ["hacker_news", "Hacker News"],
  ["wikipedia", "Wikipedia"],
] as const;
const topicStatuses: TopicStatus[] = ["active", "paused", "deprecated"];

function positivePage(value: string | null): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export function TopicsPage() {
  useDocumentTitle("Topics · Signal Observatory");
  const registry = useRegistry();
  const [parameters, setParameters] = useSearchParams();
  const search = parameters.get("search")?.trim() ?? "";
  const category = parameters.get("category") ?? "";
  const rawStatus = parameters.get("status") ?? "";
  const status = topicStatuses.includes(rawStatus as TopicStatus)
    ? (rawStatus as TopicStatus)
    : "";
  const source = parameters.get("source") ?? "";
  const page = positivePage(parameters.get("page"));
  const [searchInput, setSearchInput] = useState(search);
  const selectedCategory = registry.categories.find(
    (item) => item.slug === category,
  );
  const categorySlugs = selectedCategory
    ? categoryDescendantSlugs(selectedCategory, registry.categories)
    : new Set<string>();
  const hasCategoryChildren = registry.categories.some(
    (item) => item.parent === category,
  );
  const clientFiltered = source !== "" || hasCategoryChildren;
  const query: TopicsQuery = useMemo(
    () => ({
      category: category && !hasCategoryChildren ? category : undefined,
      status: status || undefined,
      search: search || undefined,
      limit: clientFiltered ? 500 : pageSize,
      offset: clientFiltered ? 0 : (page - 1) * pageSize,
    }),
    [category, clientFiltered, hasCategoryChildren, page, search, status],
  );
  const topics = useTopicsQuery(query);

  useEffect(() => setSearchInput(search), [search]);

  const filteredItems = (topics.data?.items ?? []).filter((topic) => {
    const categoryMatches =
      category === "" || categorySlugs.has(topic.category ?? "");
    const sourceMatches =
      source === "" ||
      topic.sources.some(
        (mapping) => mapping.enabled && mapping.source === source,
      );
    return categoryMatches && sourceMatches;
  });
  const total = clientFiltered
    ? filteredItems.length
    : (topics.data?.total ?? 0);
  const visibleItems = clientFiltered
    ? filteredItems.slice((page - 1) * pageSize, page * pageSize)
    : filteredItems;

  const updateParameter = (name: string, value: string) => {
    const next = new URLSearchParams(parameters);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    setParameters(next);
  };

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    updateParameter("search", searchInput.trim());
  };

  const changePage = (nextPage: number) => {
    const next = new URLSearchParams(parameters);
    if (nextPage <= 1) next.delete("page");
    else next.set("page", String(nextPage));
    setParameters(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const clearFilters = () => {
    setSearchInput("");
    setParameters({});
  };

  return (
    <div className="topics-page page-container">
      <header className="page-hero">
        <p className="kicker">Curated observation registry</p>
        <h1>Explore Topics</h1>
        <p>Explore all monitored topics in the Signal Observatory registry.</p>
        {registry.status ? (
          <div className="page-hero__counts">
            <span>
              <strong>{registry.status.topic_count}</strong> monitored topics
            </span>
            <span>
              <strong>{registry.categories.length}</strong> categories
            </span>
          </div>
        ) : null}
      </header>

      <section className="topic-controls" aria-label="Topic filters">
        <form className="topic-search" role="search" onSubmit={submitSearch}>
          <label htmlFor="topic-search">Search topics or aliases</label>
          <div>
            <input
              id="topic-search"
              type="search"
              value={searchInput}
              placeholder="Try DuckDB or MCP"
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <button className="button button--primary" type="submit">
              Search
            </button>
          </div>
        </form>
        <div className="topic-filter-grid">
          <label>
            Category
            <select
              value={category}
              onChange={(event) =>
                updateParameter("category", event.target.value)
              }
            >
              <option value="">All categories</option>
              {registry.categories.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.parent ? "— " : ""}
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(event) =>
                updateParameter("status", event.target.value)
              }
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="deprecated">Deprecated</option>
            </select>
          </label>
          <label>
            Configured source
            <select
              value={source}
              onChange={(event) =>
                updateParameter("source", event.target.value)
              }
            >
              <option value="">All sources</option>
              {sourceOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {topics.loading || registry.loading ? (
        <PageLoading label="Loading Topic Explorer" />
      ) : topics.error || registry.error ? (
        <PageError
          onRetry={() => {
            registry.retry();
            topics.retry();
          }}
        />
      ) : visibleItems.length === 0 ? (
        <section className="empty-state" aria-live="polite">
          <span className="state-code">0 MATCHES</span>
          <h2>No monitored topics match these filters.</h2>
          <p>
            Try a broader search or return to the complete curated registry.
          </p>
          <button
            className="button button--secondary"
            type="button"
            onClick={clearFilters}
          >
            Clear filters
          </button>
        </section>
      ) : (
        <section aria-labelledby="topic-results-title">
          <div className="results-heading">
            <h2 id="topic-results-title">Registry results</h2>
            <span>{total} matching topics</span>
          </div>
          <div className="explorer-grid">
            {visibleItems.map((topic) => (
              <TopicExplorerCard
                categories={registry.categories}
                key={topic.topic_id}
                topic={topic}
              />
            ))}
          </div>
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={changePage}
          />
        </section>
      )}
    </div>
  );
}
