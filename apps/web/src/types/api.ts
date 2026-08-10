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
