import type {
  ArxivStatus,
  Category,
  GithubStatus,
  CoverageListResponse,
  CoverageQuery,
  OperationsOverview,
  RegistryStatus,
  Topic,
  TopicListResponse,
  TopicDevelopment,
  TopicCoverage,
  TopicResearch,
  TopicsQuery,
} from "../types/api";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new ApiError(
      `Registry request failed with status ${response.status}.`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function getRegistryStatus(
  signal?: AbortSignal,
): Promise<RegistryStatus> {
  return requestJson<RegistryStatus>("/topic-registry/status", signal);
}

export function getCategories(signal?: AbortSignal): Promise<Category[]> {
  return requestJson<Category[]>("/categories", signal);
}

export function getTopics(
  query: TopicsQuery = {},
  signal?: AbortSignal,
): Promise<TopicListResponse> {
  const parameters = new URLSearchParams();
  if (query.category) parameters.set("category", query.category);
  if (query.status) parameters.set("status", query.status);
  if (query.search) parameters.set("search", query.search);
  if (query.limit !== undefined) parameters.set("limit", String(query.limit));
  if (query.offset !== undefined)
    parameters.set("offset", String(query.offset));
  const suffix = parameters.size > 0 ? `?${parameters.toString()}` : "";
  return requestJson<TopicListResponse>(`/topics${suffix}`, signal);
}

export function getTopic(slug: string, signal?: AbortSignal): Promise<Topic> {
  return requestJson<Topic>(`/topics/${encodeURIComponent(slug)}`, signal);
}

export function getResearch(
  slug: string,
  signal?: AbortSignal,
): Promise<TopicResearch> {
  return requestJson<TopicResearch>(
    `/topics/${encodeURIComponent(slug)}/research`,
    signal,
  );
}

export function getArxivStatus(signal?: AbortSignal): Promise<ArxivStatus> {
  return requestJson<ArxivStatus>("/sources/arxiv/status", signal);
}

export function getGithubStatus(signal?: AbortSignal): Promise<GithubStatus> {
  return requestJson<GithubStatus>("/sources/github/status", signal);
}

export function getDevelopment(
  slug: string,
  signal?: AbortSignal,
): Promise<TopicDevelopment> {
  return requestJson<TopicDevelopment>(
    `/topics/${encodeURIComponent(slug)}/development`,
    signal,
  );
}

export function getOperations(
  signal?: AbortSignal,
): Promise<OperationsOverview> {
  return requestJson<OperationsOverview>("/operations", signal);
}

export function getCoverage(
  query: CoverageQuery = {},
  signal?: AbortSignal,
): Promise<CoverageListResponse> {
  const parameters = new URLSearchParams();
  if (query.source) parameters.set("source", query.source);
  if (query.status) parameters.set("status", query.status);
  if (query.topic) parameters.set("topic", query.topic);
  if (query.limit !== undefined) parameters.set("limit", String(query.limit));
  if (query.offset !== undefined)
    parameters.set("offset", String(query.offset));
  const suffix = parameters.size > 0 ? `?${parameters.toString()}` : "";
  return requestJson<CoverageListResponse>(`/coverage${suffix}`, signal);
}

export function getTopicCoverage(
  slug: string,
  signal?: AbortSignal,
): Promise<TopicCoverage> {
  return requestJson<TopicCoverage>(
    `/topics/${encodeURIComponent(slug)}/coverage`,
    signal,
  );
}
