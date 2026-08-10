import { useEffect, useState } from "react";

import {
  getArxivStatus,
  getResearch,
  getTopic,
  getTopics,
} from "../api/client";
import type {
  ArxivStatus,
  Topic,
  TopicListResponse,
  TopicResearch,
  TopicsQuery,
} from "../types/api";

type ResourceState<T> = {
  data: T | null;
  error: Error | null;
  loading: boolean;
  retry: () => void;
};

export function useTopicsQuery(
  query: TopicsQuery,
): ResourceState<TopicListResponse> {
  const [data, setData] = useState<TopicListResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const queryKey = JSON.stringify(query);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setLoading(true);
    setError(null);
    void getTopics(query, controller.signal)
      .then((response) => setData(response))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof Error
            ? reason
            : new Error("Topic Registry could not be loaded."),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt, queryKey]);

  return {
    data,
    error,
    loading,
    retry: () => setAttempt((value) => value + 1),
  };
}

export function useTopicQuery(slug: string): ResourceState<Topic> {
  const [data, setData] = useState<Topic | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setLoading(true);
    setError(null);
    void getTopic(slug, controller.signal)
      .then((response) => setData(response))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof Error
            ? reason
            : new Error("Topic Registry could not be loaded."),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt, slug]);

  return {
    data,
    error,
    loading,
    retry: () => setAttempt((value) => value + 1),
  };
}

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
    setLoading(true);
    setError(null);
    void loader(controller.signal)
      .then((response) => setData(response))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason : new Error(fallbackMessage));
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

export function useResearchQuery(slug: string): ResourceState<TopicResearch> {
  return useResource(
    (signal) => getResearch(slug, signal),
    slug,
    "Research observations could not be loaded.",
  );
}

export function useArxivStatusQuery(): ResourceState<ArxivStatus> {
  return useResource(
    (signal) => getArxivStatus(signal),
    "arxiv-status",
    "arXiv collector status could not be loaded.",
  );
}
