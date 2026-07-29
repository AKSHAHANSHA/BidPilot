import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { PortalShell } from "../../components/portal/PortalShell";
import {
  HeroFigure,
  PipelineFunnel,
  RatioMeter,
  StatTile,
  StatusBars,
  type BarDatum,
} from "../../components/portal/charts";
import { GlassCard, Pill, PortalLinkButton, SectionHeading } from "../../components/portal/kit";
import { Reveal } from "../../components/portal/Reveal";
import { formatMoney, formatPercent, humanise } from "../../lib/format";
import { portal, type VendorStats } from "../../api/portal";
import { useAuth } from "../../lib/auth";

/**
 * The vendor's analytics view.
 *
 * Every figure is read from the API's aggregate; nothing is recomputed in the browser. Where
 * the API returns null — no decided applications, so no win rate — the tile shows an em dash
 * rather than a zero, because "nothing has been decided" and "you lost everything" are
 * different facts and must not look identical.
 */
export function VendorDashboardPage() {
  const { user } = useAuth();
  const stats = useQuery({ queryKey: ["portal", "vendor", "stats"], queryFn: portal.vendorStats });
  const recent = useQuery({
    queryKey: ["portal", "vendor", "applications", "recent"],
    queryFn: () => portal.myApplications({ limit: 6 }),
  });

  const data = stats.data;

  return (
    <PortalShell>
      <div className="mx-auto max-w-7xl px-5 py-12">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionHeading
            eyebrow={user?.organisation?.name ?? "Vendor"}
            title="Your bidding performance"
            description="Counts and money across every application you have made."
          />
          <PortalLinkButton to="/dashboard/projects">Find tenders</PortalLinkButton>
        </div>

        {stats.isError ? (
          <GlassCard className="mt-10 p-6">
            <p className="text-sm text-portal-rose">{(stats.error as Error).message}</p>
          </GlassCard>
        ) : null}

        {data ? (
          <>
            <Reveal>
              <div className="mt-10 grid gap-5 lg:grid-cols-[1fr_2fr]">
                <HeroFigure
                  label="Win rate"
                  value={formatPercent(data.win_rate) ?? "—"}
                  caption={
                    data.win_rate === null || data.win_rate === undefined
                      ? "No application has been decided yet."
                      : `${data.approved} won of ${data.approved + data.rejected} decided.`
                  }
                />
                <div className="grid gap-5 sm:grid-cols-2">
                  <StatTile label="Applications" value={data.total} hint="Every bid, all statuses" />
                  <StatTile
                    label="Waiting for an answer"
                    value={data.waiting}
                    tone={data.waiting > 0 ? "warning" : "neutral"}
                    hint="Submitted, under review or shortlisted"
                  />
                  <StatTile
                    label="Won contract value"
                    value={formatMoney(data.total_bid_value) ?? "—"}
                    tone="positive"
                    hint="Sum of approved bids"
                  />
                  <StatTile
                    label="Expected margin"
                    value={formatMoney(data.total_margin) ?? "—"}
                    hint={
                      data.incomplete_financials
                        ? `${data.incomplete_financials} application(s) excluded — no cost entered`
                        : "Approved bids minus your entered costs"
                    }
                  />
                </div>
              </div>
            </Reveal>

            <Reveal delay={80}>
              <div className="mt-6 grid gap-5 lg:grid-cols-3">
                <div className="lg:col-span-2">
                  <StatusBars
                    title="Applications by status"
                    description="Where every bid you have made currently sits."
                    data={statusBars(data)}
                  />
                </div>
                <RatioMeter
                  label="Margin on won work"
                  ratio={data.margin_percentage ?? null}
                  tone="positive"
                  caption={
                    data.margin_percentage === null || data.margin_percentage === undefined
                      ? "Enter a bid amount and an expected cost on your applications to see this."
                      : "Total margin as a share of won contract value."
                  }
                />
              </div>
            </Reveal>

            <Reveal delay={140}>
              <div className="mt-6">
                <PipelineFunnel
                  title="Application pipeline"
                  description="How far your submissions get. Each bar is a share of everything you submitted."
                  stages={[
                    { key: "submitted", label: "Submitted", value: submittedTotal(data) },
                    { key: "under_review", label: "Under review", value: reviewedTotal(data) },
                    { key: "shortlisted", label: "Shortlisted", value: shortlistedTotal(data) },
                    { key: "approved", label: "Won", value: data.approved },
                  ]}
                />
              </div>
            </Reveal>
          </>
        ) : null}

        <Reveal delay={200}>
          <div className="mt-10">
            <h2 className="text-sm font-semibold">Recent applications</h2>
            <div className="mt-4 space-y-3">
              {(recent.data?.items ?? []).map((application) => (
                <GlassCard key={application.id} className="flex flex-wrap items-center gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/applications/${application.id}`}
                      className="truncate text-sm font-medium transition-colors hover:text-portal-cyan"
                    >
                      {application.listing.title}
                    </Link>
                    <p className="mt-0.5 truncate text-xs text-portal-muted">
                      {application.listing.organisation?.name}
                    </p>
                  </div>
                  {application.screening?.overall_score != null ? (
                    <span className="text-sm font-semibold tabular-nums">
                      {application.screening.overall_score}
                      <span className="text-portal-faint">/100</span>
                    </span>
                  ) : null}
                  <Pill tone={statusTone(application.status)}>{humanise(application.status)}</Pill>
                </GlassCard>
              ))}
              {recent.isSuccess && (recent.data?.items ?? []).length === 0 ? (
                <GlassCard className="px-6 py-10 text-center">
                  <p className="text-sm text-portal-muted">
                    You have not applied to anything yet.
                  </p>
                  <div className="mt-4">
                    <PortalLinkButton to="/dashboard/projects">Browse tenders</PortalLinkButton>
                  </div>
                </GlassCard>
              ) : null}
            </div>
          </div>
        </Reveal>
      </div>
    </PortalShell>
  );
}

/* Colours are status tokens, and every bar carries its label and value as text, so identity
   never rests on colour alone. */
function statusBars(data: VendorStats): BarDatum[] {
  return [
    { key: "draft", label: "Draft", value: data.draft, color: "var(--color-chart-muted)" },
    { key: "submitted", label: "Submitted", value: data.submitted, color: "var(--color-chart-cyan)" },
    {
      key: "under_review",
      label: "Under review",
      value: data.under_review,
      color: "var(--color-chart-violet)",
    },
    {
      key: "shortlisted",
      label: "Shortlisted",
      value: data.shortlisted,
      color: "var(--color-chart-amber)",
    },
    { key: "approved", label: "Won", value: data.approved, color: "var(--color-chart-emerald)" },
    { key: "rejected", label: "Rejected", value: data.rejected, color: "var(--color-chart-rose)" },
    {
      key: "withdrawn",
      label: "Withdrawn",
      value: data.withdrawn,
      color: "var(--color-chart-muted)",
    },
  ];
}

// The funnel is cumulative: an application that is now shortlisted was also submitted and
// reviewed. Summing the later buckets into the earlier ones is what makes drop-off readable.
const submittedTotal = (d: VendorStats) =>
  d.submitted + d.under_review + d.shortlisted + d.approved + d.rejected;
const reviewedTotal = (d: VendorStats) => d.under_review + d.shortlisted + d.approved + d.rejected;
const shortlistedTotal = (d: VendorStats) => d.shortlisted + d.approved;

function statusTone(status: string): "neutral" | "positive" | "warning" | "danger" | "accent" {
  if (status === "approved") return "positive";
  if (status === "rejected") return "danger";
  if (status === "shortlisted") return "warning";
  if (status === "under_review" || status === "submitted") return "accent";
  return "neutral";
}
