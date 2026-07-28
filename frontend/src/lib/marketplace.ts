/**
 * Thin fetch wrappers for the TenderSphere marketplace endpoints.
 *
 * These call routes added *after* the checked-in OpenAPI schema, so we use raw fetch
 * rather than the typed openapi-fetch client. Once `./make.ps1 openapi && npm run gen:api`
 * is run, these could be migrated to the typed client.
 *
 * Uses `authedFetch` for the authenticated endpoints so 401s trigger the same silent-refresh
 * behavior as the rest of the app.
 */

import { authedFetch } from "../api/client";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export interface CategoryDto {
  slug: string;
  label: string;
  icon: string;
}

export interface ProjectSummaryDto {
  id: string;
  title: string;
  company_display_name: string;
  category: string;
  location: string | null;
  budget_aed: string | null;
  submission_deadline: string | null;
  cover_image_url: string | null;
  status: string;
  created_at: string;
}

export interface ProjectDetailDto extends ProjectSummaryDto {
  description: string;
  requirements_summary: string | null;
  posted_by_user_id: string;
}

export interface ProjectListResponse {
  items: ProjectSummaryDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApplicationSummaryDto {
  id: string;
  project_id: string;
  vendor_user_id: string;
  status: string;
  ai_score: number | null;
  ai_summary: string | null;
  submitted_at: string;
}

export interface ApplicationDetailDto extends ApplicationSummaryDto {
  ai_assessment: {
    reasons?: string[];
    matched_keywords?: string[];
    category_score?: number;
    keyword_score?: number;
    certification_score?: number;
    [k: string]: unknown;
  } | null;
  document_original_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export interface VendorDashboardDto {
  total_applications: number;
  submitted: number;
  screened: number;
  shortlisted: number;
  rejected: number;
  average_ai_score: number | null;
  applications: ApplicationSummaryDto[];
}

export interface CompanyDashboardDto {
  total_projects: number;
  open_projects: number;
  total_applicants: number;
  average_applicant_score: number | null;
  recent_applications: ApplicationSummaryDto[];
}

export interface NotificationDto {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  payload: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Public endpoints
// ---------------------------------------------------------------------------

export async function fetchCategories(): Promise<CategoryDto[]> {
  const res = await fetch(`${BASE}/api/v1/public/categories`);
  if (!res.ok) throw new Error("Could not load categories");
  return res.json();
}

export async function fetchPublicProjects(
  params: {
    category?: string;
    q?: string;
    budget_min?: number;
    budget_max?: number;
    limit?: number;
    offset?: number;
  } = {},
): Promise<ProjectListResponse> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const res = await fetch(`${BASE}/api/v1/public/projects?${search.toString()}`);
  if (!res.ok) throw new Error("Could not load projects");
  return res.json();
}

export async function fetchPublicProject(id: string): Promise<ProjectDetailDto> {
  const res = await fetch(`${BASE}/api/v1/public/projects/${id}`);
  if (!res.ok) throw new Error("Project not found");
  return res.json();
}

export async function searchProjects(query: string): Promise<ProjectListResponse> {
  const res = await fetch(`${BASE}/api/v1/public/projects/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit: 12 }),
  });
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}

// ---------------------------------------------------------------------------
// Vendor endpoints
// ---------------------------------------------------------------------------

export async function fetchVendorDashboard(): Promise<VendorDashboardDto> {
  const res = await authedFetch("/api/v1/market/vendor/dashboard/summary");
  if (!res.ok) throw new Error("Could not load your dashboard");
  return res.json();
}

export async function fetchVendorApplications(): Promise<ApplicationSummaryDto[]> {
  const res = await authedFetch("/api/v1/market/vendor/applications");
  if (!res.ok) throw new Error("Could not load applications");
  return res.json();
}

export async function submitApplication(
  projectId: string,
  coverLetter: string,
): Promise<ApplicationDetailDto> {
  const res = await authedFetch("/api/v1/market/vendor/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, cover_letter: coverLetter }),
  });
  if (!res.ok) {
    const problem = await res.json().catch(() => null);
    throw new Error(problem?.detail ?? "Could not submit your application");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Company endpoints
// ---------------------------------------------------------------------------

export interface ProjectCreatePayload {
  title: string;
  description: string;
  category: string;
  location?: string | null;
  budget_aed?: number | null;
  submission_deadline?: string | null;
  cover_image_url?: string | null;
  requirements_summary?: string | null;
  is_public?: boolean;
}

export async function fetchCompanyDashboard(): Promise<CompanyDashboardDto> {
  const res = await authedFetch("/api/v1/market/company/dashboard/summary");
  if (!res.ok) throw new Error("Could not load your dashboard");
  return res.json();
}

export async function fetchCompanyProjects(): Promise<ProjectSummaryDto[]> {
  const res = await authedFetch("/api/v1/market/company/projects");
  if (!res.ok) throw new Error("Could not load your projects");
  return res.json();
}

export async function createCompanyProject(
  payload: ProjectCreatePayload,
): Promise<ProjectDetailDto> {
  const res = await authedFetch("/api/v1/market/company/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const problem = await res.json().catch(() => null);
    throw new Error(problem?.detail ?? "Could not create the project");
  }
  return res.json();
}

export async function fetchProjectApplicants(
  projectId: string,
): Promise<ApplicationSummaryDto[]> {
  const res = await authedFetch(`/api/v1/market/company/projects/${projectId}/applications`);
  if (!res.ok) throw new Error("Could not load applicants");
  return res.json();
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export async function fetchNotifications(): Promise<NotificationDto[]> {
  const res = await authedFetch("/api/v1/market/notifications");
  if (!res.ok) return [];
  return res.json();
}

export async function fetchNotificationCounts(): Promise<{ unread: number; total: number }> {
  const res = await authedFetch("/api/v1/market/notifications/counts");
  if (!res.ok) return { unread: 0, total: 0 };
  return res.json();
}

export async function markNotificationRead(id: string): Promise<void> {
  await authedFetch(`/api/v1/market/notifications/${id}/read`, { method: "PATCH" });
}

export async function markAllNotificationsRead(): Promise<void> {
  await authedFetch("/api/v1/market/notifications/read-all", { method: "PATCH" });
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

export function formatBudget(value: string | number | null): string {
  if (value === null || value === undefined) return "—";
  const num = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(num)) return "—";
  if (num >= 1_000_000) return `AED ${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `AED ${(num / 1_000).toFixed(0)}k`;
  return `AED ${num.toFixed(0)}`;
}

export function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const diff = then - Date.now();
  return Math.round(diff / (1000 * 60 * 60 * 24));
}

export function deadlineLabel(iso: string | null): string {
  const days = daysUntil(iso);
  if (days === null) return "No deadline";
  if (days < 0) return "Closed";
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}
