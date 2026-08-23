"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { keycloak } from "../../lib/auth";

interface AuthContextValue {
  error: string;
  isAuthenticated: boolean;
  isReady: boolean;
  username: string;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isReady, setIsReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    keycloak()
      .init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false })
      .then(setIsAuthenticated)
      .catch((reason: unknown) => setError(String(reason)))
      .finally(() => setIsReady(true));
  }, []);

  const value = useMemo(() => ({
    error,
    isAuthenticated,
    isReady,
    username: String(keycloak().tokenParsed?.preferred_username ?? "пользователь"),
  }), [error, isAuthenticated, isReady]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
