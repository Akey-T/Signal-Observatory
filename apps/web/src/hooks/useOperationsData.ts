import { getCoverage, getOperations, getTopicCoverage } from "../api/client";
import type {
  CoverageListResponse,
  CoverageQuery,
  OperationsOverview,
  TopicCoverage,
} from "../types/api";
import { useEffect, useState } from "react";

type ResourceState<T> = {
  data: T | null;
  error: Error | null;
  loading: boolean;
  retry: () => void;
};

function useResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  dependencyKey: string,
  fallbackMessage: string,
): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    setLoading(true);
    void loader(controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error ? reason : new Error(fallbackMessage),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt, dependencyKey]);

  return {
    data,
    error,
    loading,
    retry: () => setAttempt((value) => value + 1),
  };
}

export function useOperationsQuery(): ResourceState<OperationsOverview> {
  return useResource(
    getOperations,
    "operations",
    "Operational health could not be loaded.",
  );
}

export function useCoverageQuery(
  query: CoverageQuery = {},
): ResourceState<CoverageListResponse> {
  const key = JSON.stringify(query);
  return useResource(
    (signal) => getCoverage(query, signal),
    key,
    "Coverage Ledger could not be loaded.",
  );
}

export function useTopicCoverageQuery(
  slug: string,
): ResourceState<TopicCoverage> {
  return useResource(
    (signal) => getTopicCoverage(slug, signal),
    slug,
    "Topic coverage could not be loaded.",
  );
}
