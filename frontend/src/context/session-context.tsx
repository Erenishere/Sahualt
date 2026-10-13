"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { AuthSession } from "@/types/marketplace";
import { fetchSession, login as apiLogin, logout as apiLogout } from "@/services/marketplace-api";

type SessionContextValue = {
  session: AuthSession | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const next = await fetchSession();
    setSession(next);
  }, []);

  useEffect(() => {
    refresh()
      .catch(() => setSession(null))
      .finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      await apiLogin(email, password);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({ session, loading, refresh, login, logout }),
    [session, loading, refresh, login, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
