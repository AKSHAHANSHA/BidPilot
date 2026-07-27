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

// Empty in development so requests are relative and the Vite proxy forwards /api to the backend
// (same-origin, simplest cookies). In production, set VITE_API_BASE to the backend origin
// (e.g. https://bidpilot-api.onrender.com) — the backend's CORS allowlist and SameSite=None
// refresh cookie are configured for that cross-site call.
const BASE = import.meta.env.VITE_API_BASE ?? "";

let refreshing: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  // Collapse concurrent refreshes into one in-flight call.
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
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

// Requests are cloned here (before the body is sent, so the clone's body stream is still
// intact) and kept only long enough to retry once if the response comes back 401 — an expired
// access token, not a rejected credential. Retrying with a stale clone after a genuine auth
// failure just reproduces the same 401, which is the correct outcome.
const pendingForRetry = new Map<string, Request>();

const authMiddleware: Middleware = {
  async onRequest({ id, request }) {
    if (accessToken) request.headers.set("Authorization", `Bearer ${accessToken}`);
    pendingForRetry.set(id, request.clone());
    return request;
  },
  async onResponse({ id, response }) {
    const retry = pendingForRetry.get(id);
    pendingForRetry.delete(id);
    if (response.status !== 401 || !retry || !(await refreshOnce())) return undefined;
    if (accessToken) retry.headers.set("Authorization", `Bearer ${accessToken}`);
    return fetch(retry);
  },
};

export const api = createClient<paths>({ baseUrl: BASE, credentials: "include" });
api.use(authMiddleware);

/**
 * For the few call sites that use raw `fetch` instead of the typed client (multipart uploads,
 * which openapi-fetch handles awkwardly). Applies the same refresh-once-on-401 behavior.
 */
export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const withAuth = (): RequestInit => ({
    ...init,
    credentials: "include",
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });
  let res = await fetch(`${BASE}${path}`, withAuth());
  if (res.status === 401 && (await refreshOnce())) {
    res = await fetch(`${BASE}${path}`, withAuth());
  }
  return res;
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
