"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

interface ApiResource<T> {
  data?: T;
  error: string;
  isLoading: boolean;
  reload: () => void;
}

export function useApiResource<T>(path: string): ApiResource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [requestNumber, setRequestNumber] = useState(0);
  const reload = useCallback(() => setRequestNumber((current) => current + 1), []);

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    setError("");
    api<T>(path)
      .then((response) => { if (isActive) setData(response); })
      .catch((reason: unknown) => { if (isActive) setError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (isActive) setIsLoading(false); });
    return () => { isActive = false; };
  }, [path, requestNumber]);

  return { data, error, isLoading, reload };
}
