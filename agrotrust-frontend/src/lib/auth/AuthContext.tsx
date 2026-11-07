import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as authApi from "@/features/auth/api";
import { clearTokens, getRefreshToken, setAccessToken, setRefreshToken } from "./tokenStorage";
import type { User } from "@/types/api";

interface AuthContextValue {
  user: User | null;
  status: "loading" | "authenticated" | "unauthenticated";
  login: (phone: string, password: string) => Promise<void>;
  logout: () => void;
  refetchProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");

  const loadProfile = useCallback(async () => {
    try {
      const profile = await authApi.fetchProfile();
      setUser(profile);
      setStatus("authenticated");
    } catch {
      clearTokens();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    // On boot there is no access token in memory, only a possible refresh
    // token in localStorage. The /api/v1/me call below relies on the API
    // client's own 401-triggers-refresh path to exchange it, so this single
    // call both restores the session and validates the stored token.
    if (!getRefreshToken()) {
      setStatus("unauthenticated");
      return;
    }
    void loadProfile();
  }, [loadProfile]);

  const login = useCallback(
    async (phone: string, password: string) => {
      const tokens = await authApi.login(phone, password);
      setAccessToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      await loadProfile();
    },
    [loadProfile],
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo(
    () => ({ user, status, login, logout, refetchProfile: loadProfile }),
    [user, status, login, logout, loadProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
