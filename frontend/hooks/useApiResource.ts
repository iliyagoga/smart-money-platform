"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

interface ApiResource<T> {
  data?: T;
  error: string;
  isLoading: boolean;
  reload: () => void;
}

export function useApiResource<T>(path: string, debounceMs = 0): ApiResource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [requestNumber, setRequestNumber] = useState(0);
  const reload = useCallback(() => setRequestNumber((current) => current + 1), []);

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    setError("");
    const timer = setTimeout(() => {
      api<T>(path)
        .then((response) => { if (isActive) setData(response); })
        .catch((reason: unknown) => { if (isActive) setError(reason instanceof Error ? reason.message : String(reason)); })
        .finally(() => { if (isActive) setIsLoading(false); });
    }, debounceMs);
    return () => { isActive = false; clearTimeout(timer); };
  }, [path, requestNumber, debounceMs]);

  return { data, error, isLoading, reload };
}
