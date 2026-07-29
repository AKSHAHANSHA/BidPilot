import { authedFetch, problemMessage, type ProblemDetail } from "./client";

/**
 * Typed access to the marketplace endpoints.
 *
 * These shapes mirror the Pydantic response models in `backend/app/schemas/`. They are written
 * out rather than pulled from `schema.d.ts` because the public routes must work with no access
 * token at all, and because a hand-declared interface states exactly what the UI depends on —
 * a field the UI never reads is not listed, so a backend rename that does not affect us does
 * not churn this file. The generated client remains the source of truth for the contract; if
 * these drift, the OpenAPI diff in CI is what catches it.
 *
 * Everything here throws a `PortalError` carrying the RFC 7807 `detail` on failure, so callers
 * can surface `error.message` directly.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "";

export type AccountType = "company" | "vendor";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface OrganisationSummary {
  id: string;
  name: string;
  emirate: string;
  city?: string | null;
  industry?: string | null;
  is_verified: boolean;
  website?: string | null;
}

export interface ListingCard {
  id: string;
  title: string;
  summary: string;
  category: string;
  category_label?: string;
  emirate: string;
  city?: string | null;
  budget_min?: string | null;
  budget_max?: string | null;
  currency: string;
  submission_deadline?: string | null;
  days_remaining?: number | null;
  cover_image_url?: string | null;
  application_count?: number;
  tags?: string[];
  organisation?: OrganisationSummary | null;
}

export interface DocumentRequirement {
  id: string;
  document_type: string;
  /** The server's own wording for `document_type`. Named `label` because that is what the
   *  computed field on `DocumentRequirementRead` is called. */
  label?: string;
  is_mandatory: boolean;
  weight: number;
  notes?: string | null;
  display_order: number;
}

export interface ListingDetail extends ListingCard {
  description: string;
  reference?: string | null;
  industry?: string | null;
  status: string;
  questions_deadline?: string | null;
  published_at?: string | null;
  contract_duration_months?: number | null;
  min_years_experience?: number | null;
  required_certifications?: string[];
  requires_bid_bond: boolean;
  bid_bond_percentage?: string | null;
  document_requirements: DocumentRequirement[];
}

export interface CategoryCount {
  category: string;
  label: string;
  count: number;
}

export interface PortalStats {
  published_listings: number;
  buying_organisations: number;
  total_published_value?: string | null;
  currency?: string;
  active_categories: number;
}

export interface SearchInterpretation {
  categories: string[];
  emirates: string[];
  keywords: string[];
  budget_min?: string | null;
  budget_max?: string | null;
  interpretation?: string;
}

export interface SearchMatch {
  listing: ListingCard;
  score: number;
  reasons: string[];
}

export interface SearchResponse {
  interpretation: SearchInterpretation;
  matches: SearchMatch[];
  /** True when no language model ran, so the UI can say so rather than imply one did. */
  degraded: boolean;
}

export interface ScreeningSummary {
  status: string;
  overall_score?: number | null;
  mandatory_met: number;
  mandatory_total: number;
  has_blocking_gap: boolean;
  completed_at?: string | null;
}

export interface ScreeningFinding {
  document_type: string;
  label: string;
  verdict: string;
  is_mandatory: boolean;
  weight: number;
  source_page?: number | null;
  evidence_quote?: string | null;
  /** The reason behind the verdict, in the pipeline's words. For an unverified credential it
   *  names the number that was checked, so the vendor knows what to correct. */
  note?: string | null;
  confidence?: number | null;
}

/** `GET /applications/{id}/screening`. Polled while `status` is pending or processing. */
export interface ScreeningDetail extends ScreeningSummary {
  optional_met: number;
  optional_total: number;
  pages_needing_ocr: number;
  summary?: string | null;
  scoring_version: string;
  error_code?: string | null;
  findings: ScreeningFinding[];
}

export interface VendorStats {
  draft: number;
  submitted: number;
  under_review: number;
  shortlisted: number;
  approved: number;
  rejected: number;
  withdrawn: number;
  waiting: number;
  total: number;
  total_bid_value?: string | null;
  total_margin?: string | null;
  margin_percentage?: number | null;
  win_rate?: number | null;
  incomplete_financials: number;
}

export interface ApplicationSummary {
  id: string;
  listing_id: string;
  listing: ListingCard;
  status: string;
  bid_amount?: string | null;
  estimated_cost?: string | null;
  margin_amount?: string | null;
  submitted_at?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  screening?: ScreeningSummary | null;
}

export interface ApplicationDocument {
  id: string;
  application_id: string;
  original_filename: string;
  size_bytes: number;
  page_count?: number | null;
  extraction_status: string;
  /** What the vendor said the file is. A hint for screening, never a verdict — which is why
   *  the checklist rows below key off it but never present it as a result. */
  declared_document_type?: string | null;
  declared_document_type_label?: string | null;
  detected_document_type?: string | null;
  detected_document_type_label?: string | null;
  created_at: string;
}

/** The vendor's own view of one application: everything the list row carries, plus the parts
 *  only the detail page needs. `estimated_cost` is here and deliberately absent from every
 *  buyer-facing shape. */
export interface ApplicationDetail extends ApplicationSummary {
  cover_letter?: string | null;
  proposed_duration_months?: number | null;
  withdrawn_at?: string | null;
  documents: ApplicationDocument[];
}

/** Fields a draft edit may set. `null` clears the column; an omitted key leaves it untouched. */
export interface ApplicationUpdate {
  cover_letter?: string | null;
  bid_amount?: string | null;
  estimated_cost?: string | null;
  proposed_duration_months?: number | null;
}

export interface Applicant {
  id: string;
  vendor_organisation: OrganisationSummary;
  cover_letter?: string | null;
  bid_amount?: string | null;
  proposed_duration_months?: number | null;
  status: string;
  submitted_at?: string | null;
  screening?: ScreeningSummary | null;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  listing_id?: string | null;
  application_id?: string | null;
  screening_score?: number | null;
  read_at?: string | null;
  created_at: string;
}

/* ------------------------------------------------------------------ core -- */

/**
 * A failed call, carrying the status alongside the message.
 *
 * Most call sites only ever read `.message`, and extending `Error` keeps that working. A few
 * decisions turn on *which* failure it was: a second application to the same listing comes
 * back 409, and the right answer to that is to open the application the vendor already has,
 * not to show them a red box about a bid they made themselves.
 */
export class PortalError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "PortalError";
    this.status = status;
    this.code = code;
  }
}

async function toError(response: Response): Promise<PortalError> {
  let problem: unknown = null;
  try {
    problem = await response.json();
  } catch {
    /* a non-JSON error body is still an error */
  }
  const detail = problem as Partial<ProblemDetail> | null;
  return new PortalError(problemMessage(problem), response.status, detail?.code);
}

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) throw await toError(response);
  return (await response.json()) as T;
}

/** Public endpoints: no credentials, so a signed-out visitor gets the same catalogue. */
async function publicGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    query.set(key, String(value));
  }
  const suffix = query.toString() ? `?${query}` : "";
  return unwrap<T>(await fetch(`${BASE}${path}${suffix}`));
}

async function publicPost<T>(path: string, body: unknown): Promise<T> {
  return unwrap<T>(
    await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers =
    init.body && !(init.body instanceof FormData)
      ? { "Content-Type": "application/json", ...(init.headers as Record<string, string>) }
      : (init.headers as Record<string, string>);
  return unwrap<T>(await authedFetch(path, { ...init, headers }));
}

/** For the endpoints that answer 204. Calling `.json()` on an empty body throws. */
async function authedVoid(path: string, init: RequestInit = {}): Promise<void> {
  const response = await authedFetch(path, init);
  if (!response.ok) throw await toError(response);
}

/* --------------------------------------------------------------- public --- */

/** A type alias, not an interface: only the former is assignable to `Record<string, unknown>`,
 *  which is what the query-string builder takes. */
export type ListingQuery = {
  category?: string | null;
  emirate?: string | null;
  q?: string;
  budget_min?: string | number;
  budget_max?: string | number;
  closing_within_days?: string | number;
  sort?: string;
  limit?: number;
  offset?: number;
};

export const portal = {
  listings: (query: ListingQuery = {}) =>
    publicGet<Page<ListingCard>>("/api/v1/public/listings", query),

  listing: (listingId: string) =>
    publicGet<ListingDetail>(`/api/v1/public/listings/${listingId}`),

  // The endpoint returns the standard `Page` envelope, not a bare array. Unwrapping it here
  // means every caller works with the list it actually wants.
  categories: async () =>
    (await publicGet<Page<CategoryCount>>("/api/v1/public/categories")).items,

  stats: () => publicGet<PortalStats>("/api/v1/public/stats"),

  search: (query: string, limit = 12) =>
    publicPost<SearchResponse>("/api/v1/public/search", { query, limit }),

  /* ------------------------------------------------------------ vendor --- */

  vendorStats: () => authed<VendorStats>("/api/v1/applications/stats"),

  myApplications: (params: { status?: string; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      query.set(key, String(value));
    }
    const suffix = query.toString() ? `?${query}` : "";
    return authed<Page<ApplicationSummary>>(`/api/v1/applications${suffix}`);
  },

  application: (applicationId: string) =>
    authed<ApplicationDetail>(`/api/v1/applications/${applicationId}`),

  createApplication: (body: {
    listing_id: string;
    cover_letter?: string;
    bid_amount?: string;
    estimated_cost?: string;
    proposed_duration_months?: number;
  }) => authed<ApplicationDetail>("/api/v1/applications", {
    method: "POST",
    body: JSON.stringify(body),
  }),

  updateApplication: (applicationId: string, body: ApplicationUpdate) =>
    authed<ApplicationDetail>(`/api/v1/applications/${applicationId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  submitApplication: (applicationId: string) =>
    authed<ApplicationDetail>(`/api/v1/applications/${applicationId}/submit`, { method: "POST" }),

  uploadApplicationDocument: (applicationId: string, file: File, declaredType?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (declaredType) form.append("declared_document_type", declaredType);
    return authed<ApplicationDocument>(`/api/v1/applications/${applicationId}/documents`, {
      method: "POST",
      body: form,
    });
  },

  deleteApplicationDocument: (applicationId: string, documentId: string) =>
    authedVoid(`/api/v1/applications/${applicationId}/documents/${documentId}`, {
      method: "DELETE",
    }),

  screening: (applicationId: string) =>
    authed<ScreeningDetail>(`/api/v1/applications/${applicationId}/screening`),

  /* ----------------------------------------------------------- company --- */

  myListings: (params: { status?: string; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      query.set(key, String(value));
    }
    const suffix = query.toString() ? `?${query}` : "";
    return authed<Page<ListingDetail>>(`/api/v1/listings${suffix}`);
  },

  applicants: (listingId: string) =>
    authed<Page<Applicant>>(`/api/v1/listings/${listingId}/applications`),

  decide: (applicationId: string, status: string, note?: string) =>
    authed<unknown>(`/api/v1/applications/${applicationId}/decision`, {
      method: "PATCH",
      body: JSON.stringify({ status, note }),
    }),

  /* ----------------------------------------------------- notifications --- */

  notifications: (unreadOnly = false) =>
    authed<Page<Notification>>(
      `/api/v1/notifications${unreadOnly ? "?unread_only=true" : ""}`,
    ),

  markNotificationRead: (notificationId: string) =>
    authed<unknown>(`/api/v1/notifications/${notificationId}/read`, { method: "POST" }),

  markAllNotificationsRead: () =>
    authed<unknown>("/api/v1/notifications/read-all", { method: "POST" }),
};
