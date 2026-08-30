"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { initializeAuth, keycloak } from "../../lib/auth";

interface AuthContextValue {
  error: string;
  isAuthenticated: boolean;
  isReady: boolean;
  roles: string[];
  username: string;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isReady, setIsReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    initializeAuth()
      .then(setIsAuthenticated)
      .catch((reason: unknown) => setError(String(reason)))
      .finally(() => setIsReady(true));
  }, []);

  const value = useMemo(() => ({
    error,
    isAuthenticated,
    isReady,
    roles: (keycloak().tokenParsed?.realm_access?.roles as string[] | undefined) ?? [],
    username: String(keycloak().tokenParsed?.preferred_username ?? "пользователь"),
  }), [error, isAuthenticated, isReady]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
