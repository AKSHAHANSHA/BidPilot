/** Controlled vocabularies mirrored from the backend enums, for populating select inputs.
 *  These match app/domain/enums.py; the backend remains the source of truth and validator. */

export const EMIRATES = [
  "abu_dhabi",
  "dubai",
  "sharjah",
  "ajman",
  "umm_al_quwain",
  "ras_al_khaimah",
  "fujairah",
];

export const EVIDENCE_CATEGORIES = [
  "trade_licence",
  "certification",
  "insurance",
  "financial_statement",
  "previous_project",
  "client_reference",
  "staff_cv",
  "technical_capability",
  "equipment_asset",
  "policy",
  "registration",
  "other",
];

export const VERIFICATION_STATUSES = ["unverified", "verified", "rejected"];

export const REVENUE_RANGES = [
  "under_1m_aed",
  "1m_to_5m_aed",
  "5m_to_20m_aed",
  "20m_to_50m_aed",
  "over_50m_aed",
];

export const PROJECT_STATUSES = ["completed", "current"];

export const COMPLIANCE_STATUSES = [
  "unreviewed",
  "met",
  "partially_met",
  "not_met",
  "needs_clarification",
  "not_applicable",
];

export function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\baed\b/i, "AED");
}
