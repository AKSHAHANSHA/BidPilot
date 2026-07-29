import { useId, type ReactNode } from "react";
import { GlassCard } from "./kit";

/**
 * Dashboard figures.
 *
 * Built as HTML rather than SVG: every chart here is a set of proportional bars, which CSS
 * does natively, responsively, and with real text nodes a screen reader can read. SVG would
 * buy nothing and cost the reflow behaviour.
 *
 * Mark specs are fixed (see the data-visualisation guidance): bars are capped at 24px and
 * carry a 4px rounded data-end with a square baseline, touching marks are separated by a 2px
 * gap in the surface colour rather than a stroke, values are labelled selectively, and axis
 * and label text always wears a text token — never the mark's own colour, which is illegible
 * as text at these steps.
 *
 * Every chart also exposes a table view. Colour is never the only channel.
 */

/* ------------------------------------------------------------ stat tiles -- */

export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "neutral" | "positive" | "warning" | "danger";
}) {
  const accents = {
    neutral: "text-portal-ink",
    positive: "text-portal-emerald",
    warning: "text-portal-amber",
    danger: "text-portal-rose",
  } as const;

  return (
    <GlassCard className="p-5">
      <p className="text-xs uppercase tracking-wide text-portal-faint">{label}</p>
      {/* Proportional figures, not tabular: a standalone value at this size reads loose when
          every digit is forced to the width of a zero. */}
      <p className={`mt-2 text-3xl font-semibold ${accents[tone]}`}>{value}</p>
      {hint ? <p className="mt-1.5 text-xs text-portal-muted">{hint}</p> : null}
    </GlassCard>
  );
}

/** The one number the dashboard leads with. Exactly one per view. */
export function HeroFigure({
  label,
  value,
  caption,
}: {
  label: string;
  value: string;
  caption?: string;
}) {
  return (
    <GlassCard className="flex h-full flex-col justify-center p-6">
      <p className="text-xs uppercase tracking-wide text-portal-faint">{label}</p>
      <p className="mt-2 text-6xl font-semibold leading-none">{value}</p>
      {caption ? <p className="mt-3 text-sm text-portal-muted">{caption}</p> : null}
    </GlassCard>
  );
}

/* ------------------------------------------------------------------ bars -- */

export interface BarDatum {
  key: string;
  label: string;
  value: number;
  /** A CSS colour. Status meaning only — see the token comments in portal.css. */
  color: string;
}

/**
 * Horizontal bars for counts by status.
 *
 * Horizontal because the category names are long words, and a column chart would either
 * rotate them or truncate them. Each bar is directly labelled with its value at the tip, so
 * there is no axis and no legend — the label beside the bar carries identity, and the colour
 * only reinforces it.
 */
export function StatusBars({
  title,
  description,
  data,
  emptyLabel = "No applications yet",
}: {
  title: string;
  description?: string;
  data: BarDatum[];
  emptyLabel?: string;
}) {
  const tableId = useId();
  const max = Math.max(...data.map((d) => d.value), 0);
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <GlassCard className="p-6">
      <header>
        <h3 className="text-sm font-semibold">{title}</h3>
        {description ? <p className="mt-1 text-xs text-portal-muted">{description}</p> : null}
      </header>

      {total === 0 ? (
        <p className="py-10 text-center text-sm text-portal-muted">{emptyLabel}</p>
      ) : (
        <>
          <ul className="mt-5 space-y-3">
            {data.map((datum) => {
              // Share of the largest bar, not of the total: this is a magnitude comparison,
              // not a part-to-whole, and scaling to the total would flatten every bar when one
              // status dominates.
              const pct = max === 0 ? 0 : (datum.value / max) * 100;
              return (
                <li key={datum.key} className="grid grid-cols-[9rem_1fr_2.5rem] items-center gap-3">
                  <span className="truncate text-xs text-portal-muted" title={datum.label}>
                    {datum.label}
                  </span>
                  <span
                    className="relative h-3.5 overflow-hidden rounded-sm bg-portal-void/70"
                    title={`${datum.label}: ${datum.value}`}
                  >
                    <span
                      className="absolute inset-y-0 left-0 rounded-r-[4px] transition-[width] duration-700"
                      style={{ width: `${pct}%`, backgroundColor: datum.color }}
                    />
                  </span>
                  <span className="text-right text-xs font-semibold tabular-nums text-portal-ink">
                    {datum.value}
                  </span>
                </li>
              );
            })}
          </ul>

          <TableView
            id={tableId}
            caption={title}
            head={["Status", "Applications"]}
            rows={data.map((d) => [d.label, String(d.value)])}
          />
        </>
      )}
    </GlassCard>
  );
}

/* --------------------------------------------------------------- funnel --- */

export interface FunnelStage {
  key: string;
  label: string;
  value: number;
}

/**
 * The application pipeline.
 *
 * Ordinal, not categorical: the stages have a fixed order and the reader should see that
 * order in the colour, so it uses a single-hue ramp rather than distinct identity hues.
 * Bars are proportional to the first stage, which is what makes drop-off visible.
 */
export function PipelineFunnel({
  title,
  description,
  stages,
}: {
  title: string;
  description?: string;
  stages: FunnelStage[];
}) {
  const tableId = useId();
  const RAMP = [
    "var(--color-chart-step-1)",
    "var(--color-chart-step-2)",
    "var(--color-chart-step-3)",
    "var(--color-chart-step-4)",
    "var(--color-chart-step-5)",
  ];
  const base = stages[0]?.value ?? 0;

  return (
    <GlassCard className="p-6">
      <header>
        <h3 className="text-sm font-semibold">{title}</h3>
        {description ? <p className="mt-1 text-xs text-portal-muted">{description}</p> : null}
      </header>

      {base === 0 ? (
        <p className="py-10 text-center text-sm text-portal-muted">
          Nothing submitted yet — the pipeline fills as you apply.
        </p>
      ) : (
        <>
          {/* 2px gap between touching segments, in the surface colour: the separation is the
              gap, never a stroke around the mark. */}
          <ol className="mt-5 space-y-[2px]">
            {stages.map((stage, index) => {
              const pct = base === 0 ? 0 : Math.min(100, (stage.value / base) * 100);
              const carried = index === 0 ? null : `${Math.round(pct)}% of submitted`;
              return (
                <li key={stage.key} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 truncate text-xs text-portal-muted">
                    {stage.label}
                  </span>
                  <span className="relative h-6 flex-1 overflow-hidden rounded-sm bg-portal-void/70">
                    <span
                      className="absolute inset-y-0 left-0 rounded-r-[4px] transition-[width] duration-700"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: RAMP[Math.min(index, RAMP.length - 1)],
                      }}
                    />
                  </span>
                  <span className="w-24 shrink-0 text-right text-xs tabular-nums text-portal-ink">
                    <span className="font-semibold">{stage.value}</span>
                    {carried ? (
                      <span className="ml-1 text-portal-faint">·&nbsp;{Math.round(pct)}%</span>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ol>

          <TableView
            id={tableId}
            caption={title}
            head={["Stage", "Applications", "Share of submitted"]}
            rows={stages.map((s) => [
              s.label,
              String(s.value),
              base === 0 ? "—" : `${Math.round((s.value / base) * 100)}%`,
            ])}
          />
        </>
      )}
    </GlassCard>
  );
}

/* ---------------------------------------------------------------- meter --- */

/**
 * A single ratio against a limit.
 *
 * The unfilled track is a lighter step of the same ramp rather than a neutral gray, so the
 * state reads across the whole bar instead of only the filled part.
 */
export function RatioMeter({
  label,
  ratio,
  caption,
  tone = "accent",
}: {
  label: string;
  /** 0–1, or null when there is nothing to divide by. */
  ratio: number | null;
  caption?: string;
  tone?: "accent" | "positive" | "warning";
}) {
  const fills = {
    accent: "var(--color-chart-violet)",
    positive: "var(--color-chart-emerald)",
    warning: "var(--color-chart-amber)",
  } as const;

  const pct = ratio === null ? null : Math.max(0, Math.min(1, ratio)) * 100;

  return (
    <GlassCard className="p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-xs uppercase tracking-wide text-portal-faint">{label}</p>
        <p className="text-lg font-semibold">
          {/* Null is shown as an em dash, never 0%. "Nothing has been decided yet" and "you
              lost every bid" are different facts and must not render identically. */}
          {pct === null ? "—" : `${pct.toFixed(0)}%`}
        </p>
      </div>
      <div
        className="mt-3 h-2.5 overflow-hidden rounded-full"
        style={{ backgroundColor: "color-mix(in srgb, " + fills[tone] + " 22%, transparent)" }}
        role="img"
        aria-label={pct === null ? `${label}: not available` : `${label}: ${pct.toFixed(0)} percent`}
      >
        {pct !== null ? (
          <div
            className="h-full rounded-r-[4px] transition-[width] duration-700"
            style={{ width: `${pct}%`, backgroundColor: fills[tone] }}
          />
        ) : null}
      </div>
      {caption ? <p className="mt-2 text-xs text-portal-muted">{caption}</p> : null}
    </GlassCard>
  );
}

/* ----------------------------------------------------------- table view --- */

/** Every chart ships one. Colour and length are never the only way to read a value. */
function TableView({
  id,
  caption,
  head,
  rows,
}: {
  id: string;
  caption: string;
  head: string[];
  rows: string[][];
}) {
  return (
    <details className="mt-5 border-t border-portal-line pt-3">
      <summary className="cursor-pointer text-xs text-portal-faint transition-colors hover:text-portal-muted">
        View as table
      </summary>
      <table id={id} className="mt-3 w-full text-left text-xs">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-portal-faint">
            {head.map((cell) => (
              <th key={cell} scope="col" className="pb-1.5 font-medium">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-portal-muted">
          {rows.map((row) => (
            <tr key={row[0]} className="border-t border-portal-line/60">
              {row.map((cell, i) => (
                <td key={i} className={`py-1.5 ${i > 0 ? "tabular-nums" : ""}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
