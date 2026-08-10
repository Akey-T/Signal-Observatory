import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { getCategories, getRegistryStatus } from "../api/client";
import type { Category, RegistryStatus } from "../types/api";

type RegistryContextValue = {
  categories: Category[];
  status: RegistryStatus | null;
  loading: boolean;
  error: Error | null;
  retry: () => void;
};

const RegistryContext = createContext<RegistryContextValue | null>(null);

export function RegistryProvider({ children }: { children: ReactNode }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [status, setStatus] = useState<RegistryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void Promise.all([
      getRegistryStatus(controller.signal),
      getCategories(controller.signal),
    ])
      .then(([registryStatus, registryCategories]) => {
        setStatus(registryStatus);
        setCategories(registryCategories);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof Error
            ? reason
            : new Error("Registry status could not be loaded."),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt]);

  return (
    <RegistryContext.Provider
      value={{
        categories,
        status,
        loading,
        error,
        retry: () => setAttempt((value) => value + 1),
      }}
    >
      {children}
    </RegistryContext.Provider>
  );
}

export function useRegistry(): RegistryContextValue {
  const value = useContext(RegistryContext);
  if (value === null)
    throw new Error("useRegistry must be used inside RegistryProvider");
  return value;
}
