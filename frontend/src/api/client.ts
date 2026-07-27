import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Typed API client generated from the backend OpenAPI contract.
 *
 * The access token lives in memory only (never localStorage), so an XSS payload cannot read a
 * persisted credential. The refresh token is an HttpOnly cookie the browser sends automatically
 * to /api/v1/auth/*. On a 401, one refresh is attempted and the original request retried.
 */

let accessToken: string | null = null;
const listeners = new Set<(token: string | null) => void>();

export function setAccessToken(token: string | null): void {
  accessToken = token;
  for (const listen of listeners) listen(token);
}
export function getAccessToken(): string | null {
  return accessToken;
}
export function onAuthChange(fn: (token: string | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const BASE = "";

let refreshing: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  // Collapse concurrent refreshes into one in-flight call.
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
        if (!res.ok) {
          setAccessToken(null);
          return false;
        }
        const body = (await res.json()) as { access_token: string };
        setAccessToken(body.access_token);
        return true;
      } catch {
        setAccessToken(null);
        return false;
      } finally {
        // Cleared on the next tick so all awaiting callers see the same result first.
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (accessToken) request.headers.set("Authorization", `Bearer ${accessToken}`);
    request.headers.set("credentials", "include");
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: BASE, credentials: "include" });
api.use(authMiddleware);

/**
 * A fetch wrapper that transparently refreshes once on 401. openapi-fetch middleware cannot
 * easily retry, so auth-sensitive calls that must survive an expired access token go through
 * this helper; most calls simply surface the 401 to TanStack Query, which triggers a refresh
 * via the app's error handling.
 */
export async function withRefresh<T>(call: () => Promise<{ response: Response; data?: T; error?: unknown }>): Promise<{
  response: Response;
  data?: T;
  error?: unknown;
}> {
  let result = await call();
  if (result.response.status === 401 && (await refreshOnce())) {
    result = await call();
  }
  return result;
}

/** RFC 7807 problem detail shape the backend returns. */
export interface ProblemDetail {
  title: string;
  detail: string;
  status: number;
  code: string;
  request_id?: string;
  errors?: { field: string; message: string }[];
}

export function problemMessage(error: unknown): string {
  const problem = error as Partial<ProblemDetail> | undefined;
  return problem?.detail || problem?.title || "Something went wrong. Please try again.";
}
