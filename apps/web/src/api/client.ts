import type {
  ArxivStatus,
  Category,
  RegistryStatus,
  Topic,
  TopicListResponse,
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
