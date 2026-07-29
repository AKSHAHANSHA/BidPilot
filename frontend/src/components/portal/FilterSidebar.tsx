import { useState } from "react";
import { PortalButton } from "./kit";
import type { CategoryOption } from "./sections";
import { humanise } from "../../lib/format";

export interface ListingFilters {
  q: string;
  category: string | null;
  emirate: string | null;
  budget_min: string;
  budget_max: string;
  closing_within_days: string;
  sort: "deadline" | "newest" | "budget_high" | "budget_low";
}

export const EMPTY_FILTERS: ListingFilters = {
  q: "",
  category: null,
  emirate: null,
  budget_min: "",
  budget_max: "",
  closing_within_days: "",
  sort: "deadline",
};

const EMIRATES = [
  "abu_dhabi",
  "dubai",
  "sharjah",
  "ajman",
  "umm_al_quwain",
  "ras_al_khaimah",
  "fujairah",
];

const CLOSING_WINDOWS = [
  { value: "7", label: "Next 7 days" },
  { value: "14", label: "Next 14 days" },
  { value: "30", label: "Next 30 days" },
  { value: "90", label: "Next 3 months" },
];

export function countActiveFilters(filters: ListingFilters) {
  let count = 0;
  if (filters.q.trim()) count += 1;
  if (filters.category) count += 1;
  if (filters.emirate) count += 1;
  if (filters.budget_min || filters.budget_max) count += 1;
  if (filters.closing_within_days) count += 1;
  return count;
}

/**
 * The browse page's left rail.
 *
 * Fully controlled: it renders the filter object it is given and reports every change up.
 * Keeping the state in the page means the URL, the query, and this panel cannot drift apart
 * — a filter that is visibly checked but not applied is the classic failure here.
 */
export function FilterSidebar({
  filters,
  categories,
  onChange,
  onReset,
  totalResults,
}: {
  filters: ListingFilters;
  categories: CategoryOption[];
  onChange: (next: ListingFilters) => void;
  onReset: () => void;
  totalResults?: number;
}) {
  const [categoryQuery, setCategoryQuery] = useState("");
  const set = <K extends keyof ListingFilters>(key: K, value: ListingFilters[K]) =>
    onChange({ ...filters, [key]: value });

  const active = countActiveFilters(filters);
  const visibleCategories = categoryQuery.trim()
    ? categories.filter((option) =>
        (option.label ?? humanise(option.category))
          .toLowerCase()
          .includes(categoryQuery.trim().toLowerCase()),
      )
    : categories;

  return (
    <aside className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Filters</h2>
          {totalResults !== undefined ? (
            <p className="mt-0.5 text-xs text-portal-muted">
              {totalResults.toLocaleString("en-AE")} tender{totalResults === 1 ? "" : "s"}
            </p>
          ) : null}
        </div>
        {active > 0 ? (
          <button
            type="button"
            onClick={onReset}
            className="text-xs text-portal-cyan transition-colors hover:text-portal-ink"
          >
            Clear ({active})
          </button>
        ) : null}
      </div>

      <Group label="Keyword">
        <input
          value={filters.q}
          onChange={(event) => set("q", event.target.value)}
          placeholder="e.g. district cooling"
          className="min-h-10 w-full rounded-lg border border-portal-line bg-portal-void/60 px-3 text-sm outline-none placeholder:text-portal-faint focus:border-portal-violet"
        />
      </Group>

      <Group label="Sort by">
        <select
          value={filters.sort}
          onChange={(event) => set("sort", event.target.value as ListingFilters["sort"])}
          className="min-h-10 w-full rounded-lg border border-portal-line bg-portal-void/60 px-3 text-sm outline-none focus:border-portal-violet"
        >
          <option value="deadline">Closing soonest</option>
          <option value="newest">Newest first</option>
          <option value="budget_high">Highest value</option>
          <option value="budget_low">Lowest value</option>
        </select>
      </Group>

      <Group label="Closing within">
        <div className="flex flex-wrap gap-1.5">
          {CLOSING_WINDOWS.map((window) => {
            const isActive = filters.closing_within_days === window.value;
            return (
              <button
                key={window.value}
                type="button"
                aria-pressed={isActive}
                onClick={() => set("closing_within_days", isActive ? "" : window.value)}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                  isActive
                    ? "border-portal-violet bg-portal-violet/15 text-portal-ink"
                    : "border-portal-line text-portal-muted hover:border-portal-line-bright"
                }`}
              >
                {window.label}
              </button>
            );
          })}
        </div>
      </Group>

      <Group label="Emirate">
        <div className="flex flex-wrap gap-1.5">
          {EMIRATES.map((emirate) => {
            const isActive = filters.emirate === emirate;
            return (
              <button
                key={emirate}
                type="button"
                aria-pressed={isActive}
                onClick={() => set("emirate", isActive ? null : emirate)}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                  isActive
                    ? "border-portal-violet bg-portal-violet/15 text-portal-ink"
                    : "border-portal-line text-portal-muted hover:border-portal-line-bright"
                }`}
              >
                {humanise(emirate)}
              </button>
            );
          })}
        </div>
      </Group>

      <Group label="Contract value (AED)">
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={filters.budget_min}
            onChange={(event) => set("budget_min", event.target.value)}
            placeholder="Min"
            className="min-h-10 w-full rounded-lg border border-portal-line bg-portal-void/60 px-3 text-sm outline-none placeholder:text-portal-faint focus:border-portal-violet"
          />
          <span className="text-portal-faint">–</span>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={filters.budget_max}
            onChange={(event) => set("budget_max", event.target.value)}
            placeholder="Max"
            className="min-h-10 w-full rounded-lg border border-portal-line bg-portal-void/60 px-3 text-sm outline-none placeholder:text-portal-faint focus:border-portal-violet"
          />
        </div>
      </Group>

      <Group label="Category">
        {categories.length > 8 ? (
          <input
            value={categoryQuery}
            onChange={(event) => setCategoryQuery(event.target.value)}
            placeholder="Find a category"
            className="mb-2 min-h-10 w-full rounded-lg border border-portal-line bg-portal-void/60 px-3 text-sm outline-none placeholder:text-portal-faint focus:border-portal-violet"
          />
        ) : null}
        {/* Scrolls rather than growing: thirty categories would push every other filter off
            the screen, and the rail has to stay usable at laptop height. */}
        <ul className="max-h-72 space-y-0.5 overflow-y-auto pr-1">
          <li>
            <CategoryRow
              label="All categories"
              active={filters.category === null}
              onClick={() => set("category", null)}
            />
          </li>
          {visibleCategories.map((option) => (
            <li key={option.category}>
              <CategoryRow
                label={option.label ?? humanise(option.category)}
                count={option.count}
                active={filters.category === option.category}
                onClick={() =>
                  set("category", filters.category === option.category ? null : option.category)
                }
              />
            </li>
          ))}
          {visibleCategories.length === 0 ? (
            <li className="px-2 py-3 text-xs text-portal-faint">No category matches that.</li>
          ) : null}
        </ul>
      </Group>

      {active > 0 ? (
        <PortalButton variant="ghost" onClick={onReset} className="w-full">
          Reset filters
        </PortalButton>
      ) : null}
    </aside>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-portal-faint">
        {label}
      </h3>
      {children}
    </div>
  );
}

function CategoryRow({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
        active
          ? "bg-portal-violet/15 text-portal-ink"
          : "text-portal-muted hover:bg-portal-deep hover:text-portal-ink"
      }`}
    >
      <span className="truncate">{label}</span>
      {count !== undefined ? <span className="shrink-0 text-portal-faint">{count}</span> : null}
    </button>
  );
}
