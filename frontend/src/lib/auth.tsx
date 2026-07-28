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

export type AccountType = "vendor" | "company";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  account_type: AccountType;
}

export interface RegisterPayload {
  email: string;
  password: string;
  display_name: string;
  account_type: AccountType;
  location?: string;
  primary_category?: string;
  bio?: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, try to restore a session via the refresh cookie.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
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

  const register = useCallback(async (payload: RegisterPayload) => {
    // Sent via raw fetch: RegisterRequest was extended with account_type + role fields after
    // the checked-in OpenAPI schema, so the typed openapi-fetch call would flag them as
    // unknown. The backend validates the same fields either way.
    const res = await fetch("/api/v1/auth/register", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(body?.detail ?? body?.title ?? "Registration failed");
    }
    setAccessToken(body.access_token);
    setUser(body.user as User);
  }, []);

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
