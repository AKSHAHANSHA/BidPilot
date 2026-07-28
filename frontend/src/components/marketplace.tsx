import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { ProjectSummaryDto } from "../lib/marketplace";
import { deadlineLabel, formatBudget } from "../lib/marketplace";

/**
 * Marketplace-specific presentational components. Kept separate from the "Procurement Ledger"
 * UI kit in `ui.tsx` so the marketplace's midnight/gradient aesthetic doesn't bleed into the
 * authenticated back-office pages.
 */

export function ProjectCard({
  project,
  categoryLabel,
  variant = "paper",
}: {
  project: ProjectSummaryDto;
  categoryLabel?: string;
  variant?: "paper" | "dark";
}) {
  const isDark = variant === "dark";
  return (
    <Link
      to={`/projects/${project.id}`}
      className={`group block rounded-lg overflow-hidden border transition-all duration-200 hover:-translate-y-0.5 focus-visible:-translate-y-0.5 outline-none ${
        isDark
          ? "border-white/10 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.06]"
          : "border-rule-soft bg-surface hover:border-ink hover:shadow-[3px_3px_0_var(--color-signal)]"
      }`}
    >
      <div
        className="aspect-[16/9] w-full overflow-hidden relative"
        style={{
          background: project.cover_image_url
            ? `center / cover no-repeat url("${project.cover_image_url}"), linear-gradient(135deg, #232433, #0a0b12)`
            : "linear-gradient(135deg, #232433, #0a0b12)",
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
        <div className="absolute top-3 left-3">
          <span className="inline-block px-2 py-0.5 text-[10px] uppercase tracking-widest bg-white/90 text-black rounded-sm font-semibold">
            {categoryLabel ?? project.category.replaceAll("_", " ")}
          </span>
        </div>
        <div className="absolute bottom-3 right-3">
          <span className="inline-block px-2 py-0.5 text-[10px] uppercase tracking-widest bg-black/70 text-white rounded-sm font-semibold">
            {deadlineLabel(project.submission_deadline)}
          </span>
        </div>
      </div>
      <div className={`p-4 space-y-2 ${isDark ? "text-white" : ""}`}>
        <div
          className={`text-xs uppercase tracking-widest ${
            isDark ? "text-white/50" : "text-ink-muted"
          }`}
        >
          {project.company_display_name}
        </div>
        <h3
          className={`font-display text-lg leading-snug line-clamp-2 ${
            isDark ? "text-white" : "text-ink"
          }`}
        >
          {project.title}
        </h3>
        <div
          className={`flex items-center justify-between text-sm pt-2 border-t ${
            isDark ? "border-white/10 text-white/70" : "border-rule-soft text-ink-muted"
          }`}
        >
          <span>{project.location ?? "UAE"}</span>
          <span className="font-mono font-semibold text-signal">
            {formatBudget(project.budget_aed)}
          </span>
        </div>
      </div>
    </Link>
  );
}

export function StatTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  const toneClass = {
    default: "border-rule-soft",
    success: "border-success",
    warning: "border-warning",
    danger: "border-signal",
    info: "border-info",
  }[tone];
  return (
    <div className={`bg-surface border ${toneClass} p-4 rounded-[3px]`}>
      <div className="text-xs uppercase tracking-widest text-ink-muted">{label}</div>
      <div className="font-display text-3xl leading-none mt-2">{value}</div>
      {hint ? <div className="text-xs text-ink-muted mt-2">{hint}</div> : null}
    </div>
  );
}

export function BarRow({
  label,
  value,
  max,
  tone = "ink",
}: {
  label: string;
  value: number;
  max: number;
  tone?: "ink" | "success" | "warning" | "signal";
}) {
  const pct = max === 0 ? 0 : Math.min(100, Math.round((value / max) * 100));
  const bar = {
    ink: "bg-ink",
    success: "bg-success",
    warning: "bg-warning",
    signal: "bg-signal",
  }[tone];
  return (
    <div className="flex items-center gap-3">
      <div className="w-40 text-sm text-ink-muted flex-shrink-0">{label}</div>
      <div className="flex-1 h-3 bg-rule-soft rounded-[2px] overflow-hidden">
        <div className={`h-full ${bar} transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <div className="w-10 text-right text-sm font-mono">{value}</div>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  cta,
}: {
  title: string;
  body: string;
  cta?: ReactNode;
}) {
  return (
    <div className="border border-dashed border-rule-soft rounded-[3px] p-8 text-center bg-surface">
      <div className="font-display text-xl">{title}</div>
      <div className="text-sm text-ink-muted mt-2 max-w-md mx-auto">{body}</div>
      {cta ? <div className="mt-4">{cta}</div> : null}
    </div>
  );
}
