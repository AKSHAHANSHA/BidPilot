import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, onAuthChange, setAccessToken, problemMessage } from "../api/client";

interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, try to restore a session via the refresh cookie, then load the user.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" });
        if (res.ok) {
          const body = (await res.json()) as { access_token: string; user: User };
          setAccessToken(body.access_token);
          if (active) setUser(body.user);
        }
      } catch {
        /* not signed in */
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  // If a background refresh (triggered by an expired access token on some later request)
  // definitively fails — the refresh cookie itself is gone or invalid — clear the signed-in
  // state so route protection sends the user back to the sign-in screen instead of leaving
  // stale UI that will keep failing.
  useEffect(() => {
    return onAuthChange((token) => {
      if (token === null) setUser((prev) => (prev ? null : prev));
    });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data, error } = await api.POST("/api/v1/auth/login", { body: { email, password } });
    if (error || !data) throw new Error(problemMessage(error));
    setAccessToken(data.access_token);
    setUser(data.user as User);
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      const { data, error } = await api.POST("/api/v1/auth/register", {
        body: { email, password, display_name: displayName },
      });
      if (error || !data) throw new Error(problemMessage(error));
      setAccessToken(data.access_token);
      setUser(data.user as User);
    },
    [],
  );

  const logout = useCallback(async () => {
    await api.POST("/api/v1/auth/logout", {});
    setAccessToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
