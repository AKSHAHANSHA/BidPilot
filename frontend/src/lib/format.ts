/** Display formatting for the marketplace.
 *
 * Everything here is presentation only. Nothing rounds, derives, or reinterprets a value that
 * the backend already decided — a card must not be able to disagree with the API about how
 * much a contract is worth or whether it is still open.
 */

const AED = new Intl.NumberFormat("en-AE", {
  style: "currency",
  currency: "AED",
  maximumFractionDigits: 0,
});

/** Compact money for cards: 1.4M, 850K. Full precision belongs on the detail page. */
export function formatMoneyCompact(value: string | number | null | undefined, currency = "AED") {
  if (value === null || value === undefined || value === "") return null;
  const amount = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(amount)) return null;

  const abs = Math.abs(amount);
  if (abs >= 1_000_000) return `${currency} ${(amount / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${currency} ${Math.round(amount / 1_000)}K`;
  return `${currency} ${Math.round(amount)}`;
}

export function formatMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  const amount = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(amount) ? AED.format(amount) : null;
}

/**
 * A budget range as one string. Says "Undisclosed" rather than inventing a number when the
 * buyer chose not to publish one — many public tenders legitimately do not.
 */
export function formatBudgetRange(
  min: string | number | null | undefined,
  max: string | number | null | undefined,
  currency = "AED",
) {
  const low = formatMoneyCompact(min, currency);
  const high = formatMoneyCompact(max, currency);
  if (low && high) return low === high ? low : `${low} – ${high}`;
  if (low) return `From ${low}`;
  if (high) return `Up to ${high}`;
  return "Undisclosed";
}

export function formatDate(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export interface DeadlineState {
  label: string;
  tone: "neutral" | "warning" | "danger";
}

/**
 * Turns a deadline into something a card can show at a glance.
 *
 * `daysRemaining` comes from the API when available — the server's clock is the one that
 * decides whether a tender is open, and a browser with a skewed clock must not be able to
 * present a closed tender as biddable.
 */
export function describeDeadline(
  deadline: string | null | undefined,
  daysRemaining?: number | null,
): DeadlineState {
  if (!deadline) return { label: "No deadline set", tone: "neutral" };

  const days =
    daysRemaining ??
    Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));

  if (!Number.isFinite(days)) return { label: "No deadline set", tone: "neutral" };
  if (days < 0) return { label: "Closed", tone: "danger" };
  if (days === 0) return { label: "Closes today", tone: "danger" };
  if (days === 1) return { label: "1 day left", tone: "warning" };
  if (days <= 7) return { label: `${days} days left`, tone: "warning" };
  return { label: `${days} days left`, tone: "neutral" };
}

/** snake_case enum value → readable label, for the few places the API does not send one. */
export function humanise(value: string | null | undefined) {
  if (!value) return "";
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatPercent(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${(value * 100).toFixed(digits)}%`;
}
