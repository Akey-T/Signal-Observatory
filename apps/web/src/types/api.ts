export type TopicStatus = "active" | "paused" | "deprecated";

export type TopicAlias = {
  value: string;
  normalized_alias: string;
  type: string;
  match_mode: string;
  case_sensitive: boolean;
  status: string;
  confidence: number;
  metadata: Record<string, unknown>;
};

export type SourceMapping = {
  source: string;
  enabled: boolean;
  mapping_type: string;
  external_identifier: string | null;
  query: string | null;
  configuration: Record<string, unknown>;
};

export type Topic = {
  topic_id: string;
  canonical_name: string;
  slug: string;
  description: string | null;
  category: string | null;
  status: TopicStatus;
  monitoring_priority: number;
  deprecated_at: string | null;
  registry_version: number | null;
  metadata: Record<string, unknown>;
  aliases: TopicAlias[];
  sources: SourceMapping[];
};

export type TopicListResponse = {
  items: Topic[];
  total: number;
  limit: number;
  offset: number;
};

export type Category = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  parent: string | null;
  sort_order: number;
};

export type RegistryStatus = {
  version: number;
  checksum: string;
  last_synced_at: string;
  topic_count: number;
  active_topics: number;
  alias_count: number;
  source_mapping_count: number;
  warnings: number;
};

export type TopicsQuery = {
  category?: string;
  status?: TopicStatus;
  search?: string;
  limit?: number;
  offset?: number;
};

export type ArxivStatus = {
  source: "arxiv";
  enabled: boolean;
  collector_state: string;
  last_run_at: string | null;
  last_successful_run_at: string | null;
  last_run_status: string | null;
  tracked_topics: number;
  tracked_mappings: number;
  papers_observed: number;
  last_24h_new_papers: number;
  error_count_last_run: number;
};

export type ResearchPaper = {
  arxiv_id: string;
  title: string;
  authors: string[];
  published_at: string;
  updated_at: string;
  primary_category: string;
  categories: string[];
  abstract: string;
  abs_url: string;
  matched_query: string;
  source_mapping_id: string;
  ingestion_run_id: string;
  raw_checksum: string | null;
};

export type TopicResearch = {
  topic: {
    slug: string;
    canonical_name: string;
  };
  source: "arxiv";
  state: "not_configured" | "not_initialized" | "live" | "degraded";
  last_observed_at: string | null;
  collector_error: string | null;
  summary: {
    papers_total: number;
    papers_7d: number;
    papers_30d: number;
    unique_authors_30d: number;
  };
  latest_papers: ResearchPaper[];
};

export type GithubRateBudget = {
  limit?: number;
  remaining?: number;
  used?: number;
  reset_at?: string | null;
  resource?: string;
};

export type GithubStatus = {
  source: "github";
  enabled: boolean;
  auth_configured: boolean;
  collector_state: string;
  last_run_at: string | null;
  last_run_status: string | null;
  last_discovery_at: string | null;
  last_snapshot_at: string | null;
  last_successful_snapshot_at: string | null;
  tracked_repositories: number;
  snapshots: number;
  errors_last_run: number;
  search_rate: GithubRateBudget | null;
  core_rate: GithubRateBudget | null;
};

export type DevelopmentMatchEvidence = {
  matched_query: string;
  source_mapping_id: string;
  discovery_rank: number;
  discovery_run_id: string;
  raw_checksum: string | null;
};

export type DevelopmentRepository = {
  github_repository_id: number;
  full_name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  stars: number | null;
  forks: number | null;
  pushed_at: string | null;
  archived: boolean;
  disabled: boolean;
  latest_snapshot_at: string | null;
  previous_snapshot_at: string | null;
  stars_delta: number | null;
  forks_delta: number | null;
  match_evidence: DevelopmentMatchEvidence[];
};

export type TopicDevelopment = {
  topic: {
    slug: string;
    canonical_name: string;
  };
  source: "github";
  state: "not_configured" | "not_initialized" | "live" | "degraded";
  last_snapshot_at: string | null;
  last_successful_snapshot_at: string | null;
  collector_error: string | null;
  summary: {
    repositories_tracked: number;
    stars_total: number;
    forks_total: number;
    repositories_pushed_30d: number;
    stars_delta_since_previous_snapshot: number | null;
    forks_delta_since_previous_snapshot: number | null;
    previous_snapshot_at: string | null;
    latest_snapshot_at: string | null;
  };
  top_repositories: DevelopmentRepository[];
};
