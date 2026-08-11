import type {
  ArxivStatus,
  Category,
  GithubStatus,
  RegistryStatus,
  SourceMapping,
  Topic,
  TopicDevelopment,
  TopicResearch,
} from "../types/api";

export const categories: Category[] = [
  {
    id: "category-ai",
    name: "Artificial Intelligence",
    slug: "artificial-intelligence",
    description: "AI research, systems and operations.",
    parent: null,
    sort_order: 10,
  },
  {
    id: "category-ai-systems",
    name: "AI Systems",
    slug: "ai-systems",
    description: "Applied AI systems.",
    parent: "artificial-intelligence",
    sort_order: 11,
  },
  {
    id: "category-software",
    name: "Software Development",
    slug: "software-development",
    description: "Software ecosystems.",
    parent: null,
    sort_order: 20,
  },
  {
    id: "category-data",
    name: "Data Systems",
    slug: "data-systems",
    description: "Data technologies.",
    parent: null,
    sort_order: 30,
  },
];

export const registryStatus: RegistryStatus = {
  version: 1,
  checksum: "a".repeat(64),
  last_synced_at: "2026-08-09T11:26:24Z",
  topic_count: 101,
  active_topics: 101,
  alias_count: 109,
  source_mapping_count: 204,
  warnings: 0,
};

export const arxivStatus: ArxivStatus = {
  source: "arxiv",
  enabled: true,
  collector_state: "not_initialized",
  last_run_at: null,
  last_successful_run_at: null,
  last_run_status: null,
  tracked_topics: 1,
  tracked_mappings: 1,
  papers_observed: 0,
  last_24h_new_papers: 0,
  error_count_last_run: 0,
};

export const githubStatus: GithubStatus = {
  source: "github",
  enabled: true,
  auth_configured: false,
  collector_state: "not_configured",
  last_run_at: null,
  last_run_status: null,
  last_discovery_at: null,
  last_snapshot_at: null,
  last_successful_snapshot_at: null,
  tracked_repositories: 0,
  snapshots: 0,
  errors_last_run: 0,
  search_rate: null,
  core_rate: null,
};

export const topicResearch: TopicResearch = {
  topic: {
    slug: "model-context-protocol",
    canonical_name: "Model Context Protocol",
  },
  source: "arxiv",
  state: "not_initialized",
  last_observed_at: null,
  collector_error: null,
  summary: {
    papers_total: 0,
    papers_7d: 0,
    papers_30d: 0,
    unique_authors_30d: 0,
  },
  latest_papers: [],
};

export const liveTopicResearch: TopicResearch = {
  ...topicResearch,
  state: "live",
  last_observed_at: "2026-08-09T06:30:00Z",
  summary: {
    papers_total: 12,
    papers_7d: 3,
    papers_30d: 8,
    unique_authors_30d: 17,
  },
  latest_papers: [
    {
      arxiv_id: "2608.01234",
      title: "Reliable Context Exchange for Agentic Systems",
      authors: ["Ada Example", "Lin Researcher"],
      published_at: "2026-08-08T12:00:00Z",
      updated_at: "2026-08-09T06:30:00Z",
      primary_category: "cs.AI",
      categories: ["cs.AI", "cs.SE"],
      abstract:
        "A persisted example abstract used to verify the Research surface.",
      abs_url: "https://arxiv.org/abs/2608.01234",
      matched_query: 'all:"model context protocol"',
      source_mapping_id: "mapping-arxiv-mcp",
      ingestion_run_id: "run-1",
      raw_checksum: "b".repeat(64),
    },
  ],
};

export const topicDevelopment: TopicDevelopment = {
  topic: {
    slug: "model-context-protocol",
    canonical_name: "Model Context Protocol",
  },
  source: "github",
  state: "not_initialized",
  last_snapshot_at: null,
  last_successful_snapshot_at: null,
  collector_error: null,
  summary: {
    repositories_tracked: 0,
    stars_total: 0,
    forks_total: 0,
    repositories_pushed_30d: 0,
    stars_delta_since_previous_snapshot: null,
    forks_delta_since_previous_snapshot: null,
    previous_snapshot_at: null,
    latest_snapshot_at: null,
  },
  top_repositories: [],
};

export const liveTopicDevelopment: TopicDevelopment = {
  ...topicDevelopment,
  state: "live",
  last_snapshot_at: "2026-08-11T03:00:00Z",
  last_successful_snapshot_at: "2026-08-11T03:01:00Z",
  summary: {
    repositories_tracked: 6,
    stars_total: 12500,
    forks_total: 980,
    repositories_pushed_30d: 5,
    stars_delta_since_previous_snapshot: 42,
    forks_delta_since_previous_snapshot: 7,
    previous_snapshot_at: "2026-08-10T03:00:00Z",
    latest_snapshot_at: "2026-08-11T03:00:00Z",
  },
  top_repositories: [
    {
      github_repository_id: 123456,
      full_name: "modelcontextprotocol/servers",
      description: "Reference servers for the Model Context Protocol.",
      html_url: "https://github.com/modelcontextprotocol/servers",
      language: "TypeScript",
      stars: 10000,
      forks: 800,
      pushed_at: "2026-08-11T01:00:00Z",
      archived: false,
      disabled: false,
      latest_snapshot_at: "2026-08-11T03:00:00Z",
      previous_snapshot_at: "2026-08-10T03:00:00Z",
      stars_delta: 40,
      forks_delta: 6,
      match_evidence: [
        {
          matched_query: '"model context protocol" in:name,description,readme',
          source_mapping_id: "mapping-github-mcp",
          discovery_rank: 1,
          discovery_run_id: "run-github-1",
          raw_checksum: "c".repeat(64),
        },
      ],
    },
  ],
};

function sourceMapping(source: string): SourceMapping {
  return {
    source,
    enabled: true,
    mapping_type: "registry",
    external_identifier: source === "wikipedia" ? "Example page" : null,
    query: source === "arxiv" ? "example topic" : null,
    configuration:
      source === "github"
        ? { search_queries: ["example/topic"] }
        : source === "hacker_news"
          ? { terms: ["Example Topic"] }
          : source === "wikipedia"
            ? { page_titles: ["Example Topic"] }
            : { search_terms: ["example topic"] },
  };
}

export function makeTopic(
  index: number,
  overrides: Partial<Topic> = {},
): Topic {
  const categoryCycle = ["ai-systems", "software-development", "data-systems"];
  return {
    topic_id: `topic-${index}`,
    canonical_name: `Topic ${String(index).padStart(2, "0")}`,
    slug: `topic-${index}`,
    description: `A durable description for monitored technology topic ${index}.`,
    category: categoryCycle[index % categoryCycle.length],
    status: "active",
    monitoring_priority: 100 - index,
    deprecated_at: null,
    registry_version: 1,
    metadata: {},
    aliases: [
      {
        value: `T${index}`,
        normalized_alias: `t${index}`,
        type: "abbreviation",
        match_mode: "exact",
        case_sensitive: false,
        status: "active",
        confidence: 1,
        metadata: {},
      },
    ],
    sources: [sourceMapping("arxiv"), sourceMapping("wikipedia")],
    ...overrides,
  };
}

export const modelContextProtocol = makeTopic(200, {
  topic_id: "mcp",
  canonical_name: "Model Context Protocol",
  slug: "model-context-protocol",
  description:
    "An open protocol connecting AI applications to tools and contextual data sources.",
  category: "ai-systems",
  monitoring_priority: 98,
  aliases: [
    {
      value: "MCP",
      normalized_alias: "MCP",
      type: "abbreviation",
      match_mode: "exact",
      case_sensitive: true,
      status: "active",
      confidence: 1,
      metadata: {},
    },
    {
      value: "MCP server",
      normalized_alias: "MCP server",
      type: "search_term",
      match_mode: "phrase",
      case_sensitive: true,
      status: "active",
      confidence: 1,
      metadata: {},
    },
  ],
  sources: [
    sourceMapping("arxiv"),
    sourceMapping("github"),
    sourceMapping("hacker_news"),
    sourceMapping("wikipedia"),
  ],
});
