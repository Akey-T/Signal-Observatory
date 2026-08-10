import type {
  Category,
  RegistryStatus,
  SourceMapping,
  Topic,
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
