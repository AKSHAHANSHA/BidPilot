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

export type AccountType = "company" | "vendor";

export interface OrganisationSummary {
  id: string;
  name: string;
  emirate: string;
  city?: string | null;
  industry?: string | null;
  is_verified: boolean;
  website?: string | null;
}

interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  account_type: AccountType;
  organisation?: OrganisationSummary | null;
}

/** The organisation block registration requires. Only four fields are mandatory. */
export interface OrganisationInput {
  name: string;
  description: string;
  emirate: string;
  contact_email: string;
  city?: string;
  address_line?: string;
  industry?: string;
  registration_number?: string;
  contact_phone?: string;
  website?: string;
  year_established?: number;
  employee_count?: number;
}

export interface RegisterInput {
  email: string;
  password: string;
  display_name: string;
  account_type: AccountType;
  organisation: OrganisationInput;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  resetPassword: (token: string, newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

const BASE = import.meta.env.VITE_API_BASE ?? "";

/**
 * POST to an auth endpoint with plain fetch.
 *
 * The generated OpenAPI client is the right tool for most calls, but these four are either
 * unauthenticated or shape the session itself, and `/auth/refresh` already uses raw fetch here
 * for the same reason: they must work before the client has a token to attach.
 */
async function postAuth<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let problem: unknown = null;
    try {
      problem = await response.json();
    } catch {
      /* a non-JSON error body is still an error */
    }
    throw new Error(problemMessage(problem));
  }

  return (await response.json()) as T;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, try to restore a session via the refresh cookie, then load the user.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
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
    const body = await postAuth<{ access_token: string; user: User }>("/api/v1/auth/login", {
      email,
      password,
    });
    setAccessToken(body.access_token);
    setUser(body.user);
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const body = await postAuth<{ access_token: string; user: User }>(
      "/api/v1/auth/register",
      input,
    );
    setAccessToken(body.access_token);
    setUser(body.user);
  }, []);

  const logout = useCallback(async () => {
    await api.POST("/api/v1/auth/logout", {});
    setAccessToken(null);
    setUser(null);
  }, []);

  // Always resolves when the request itself succeeded. The backend answers identically whether
  // or not the address exists, and surfacing any difference here would rebuild the account
  // enumeration oracle the endpoint is designed to avoid.
  const requestPasswordReset = useCallback(async (email: string) => {
    await postAuth<unknown>("/api/v1/auth/password-reset/request", { email });
  }, []);

  const resetPassword = useCallback(async (token: string, newPassword: string) => {
    await postAuth<unknown>("/api/v1/auth/password-reset/confirm", {
      token,
      new_password: newPassword,
    });
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, requestPasswordReset, resetPassword }),
    [user, loading, login, register, logout, requestPasswordReset, resetPassword],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
