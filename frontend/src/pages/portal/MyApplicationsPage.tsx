import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { PortalShell } from "../../components/portal/PortalShell";
import {
  Chip,
  EmptyState,
  GlassCard,
  Pill,
  PortalAlert,
  PortalButton,
  PortalLinkButton,
  SectionHeading,
  Skeleton,
} from "../../components/portal/kit";
import { formatDate, formatMoney, humanise } from "../../lib/format";
import { portal } from "../../api/portal";
import { useAuth } from "../../lib/auth";

const PAGE_SIZE = 20;

/** The filter rail. `null` is "everything", which is not a status the API accepts. */
const STATUS_FILTERS: { value: string | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "submitted", label: "Submitted" },
  { value: "under_review", label: "Under review" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "approved", label: "Won" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
];

/**
 * Every bid this vendor has made.
 *
 * The dashboard answers "how am I doing"; this page answers "where is that one". So it is a
 * list rather than a chart, filterable by the only axis that matters when you are looking for
 * something — its status.
 */
export function MyApplicationsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const applications = useQuery({
    queryKey: ["portal", "vendor", "applications", { status, offset }],
    queryFn: () => portal.myApplications({ status: status ?? undefined, limit: PAGE_SIZE, offset }),
    // Changing a filter should not collapse the list to skeletons and lose the scroll position.
    placeholderData: keepPreviousData,
    enabled: user?.account_type === "vendor",
  });

  if (user && user.account_type !== "vendor") {
    return (
      <PortalShell>
        <div className="mx-auto max-w-3xl px-5 py-16">
          <EmptyState
            title="This page belongs to vendor accounts"
            description="You are signed in as a buying organisation. Applications are made by vendors; your side of the marketplace is the listings you publish and the applicants on them."
            action={<PortalLinkButton to="/dashboard">Go to your dashboard</PortalLinkButton>}
          />
        </div>
      </PortalShell>
    );
  }

  const items = applications.data?.items ?? [];
  const total = applications.data?.total ?? 0;
  const hasMore = offset + items.length < total;

  const applyFilter = (next: string | null) => {
    setStatus(next);
    setOffset(0); // a new filter always starts at page one
  };

  return (
    <PortalShell>
      <div className="mx-auto max-w-5xl px-5 py-12">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionHeading
            eyebrow="Your applications"
            title="Every bid you have made"
            description="Drafts you have not sent, submissions waiting on a buyer, and the ones that have been decided."
          />
          <PortalLinkButton to="/tenders" variant="ghost">
            Find more tenders
          </PortalLinkButton>
        </div>

        <div className="mt-8 flex flex-wrap gap-2">
          {STATUS_FILTERS.map((filter) => (
            <Chip
              key={filter.label}
              active={status === filter.value}
              onClick={() => applyFilter(filter.value)}
            >
              {filter.label}
            </Chip>
          ))}
        </div>

        {applications.isError ? (
          <div className="mt-8">
            <PortalAlert message={(applications.error as Error).message} />
          </div>
        ) : null}

        {applications.isPending ? (
          <div className="mt-8 space-y-3">
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-24 w-full" />
            ))}
          </div>
        ) : null}

        {applications.isSuccess && items.length === 0 ? (
          <div className="mt-8">
            <EmptyState
              title={status === null ? "No applications yet" : "Nothing with that status"}
              description={
                status === null
                  ? "Browse the marketplace and apply to a tender. A draft costs nothing and is editable until you submit it."
                  : "Try another filter, or clear it to see everything you have applied to."
              }
              action={
                status === null ? (
                  <PortalLinkButton to="/tenders">Browse tenders</PortalLinkButton>
                ) : (
                  <PortalButton variant="ghost" onClick={() => applyFilter(null)}>
                    Show everything
                  </PortalButton>
                )
              }
            />
          </div>
        ) : null}

        <ul className="mt-8 space-y-3">
          {items.map((application) => (
            <li key={application.id}>
              <GlassCard interactive className="relative p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold leading-snug">
                      <Link
                        to={`/applications/${application.id}`}
                        className="transition-colors hover:text-portal-cyan"
                      >
                        {/* Stretched link: the card is the hit target, but only one link is in
                            the accessibility tree. */}
                        <span className="absolute inset-0" aria-hidden="true" />
                        {application.listing.title}
                      </Link>
                    </h2>
                    <p className="mt-1 text-xs text-portal-muted">
                      {application.listing.organisation?.name ?? "Buying organisation"}
                      {application.submitted_at
                        ? ` · submitted ${formatDate(application.submitted_at)}`
                        : " · not submitted"}
                    </p>
                  </div>

                  <div className="flex shrink-0 items-center gap-3">
                    <ScreeningScore screening={application.screening} />
                    <ApplicationStatusPill status={application.status} />
                  </div>
                </div>

                <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2 border-t border-portal-line pt-3 text-xs">
                  <div>
                    <dt className="text-portal-faint">Your bid</dt>
                    <dd className="mt-0.5 font-medium">
                      {formatMoney(application.bid_amount) ?? "Not entered"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-portal-faint">Tender closes</dt>
                    <dd className="mt-0.5 font-medium">
                      {formatDate(application.listing.submission_deadline) ?? "—"}
                    </dd>
                  </div>
                  {application.decided_at ? (
                    <div>
                      <dt className="text-portal-faint">Decided</dt>
                      <dd className="mt-0.5 font-medium">{formatDate(application.decided_at)}</dd>
                    </div>
                  ) : null}
                </dl>
              </GlassCard>
            </li>
          ))}
        </ul>

        {hasMore ? (
          <div className="mt-8 flex justify-center">
            <PortalButton
              variant="ghost"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={applications.isFetching}
            >
              {applications.isFetching
                ? "Loading…"
                : `Show more (${total - offset - items.length} left)`}
            </PortalButton>
          </div>
        ) : null}
      </div>
    </PortalShell>
  );
}

/**
 * The status pill, shared with the application detail page.
 *
 * The tone is chosen from meaning rather than derived from the string, so a status this build
 * has never seen renders as neutral instead of accidentally reading as a win. Same treatment
 * as the vendor dashboard's recent-applications list.
 */
export function ApplicationStatusPill({ status }: { status: string }) {
  const tone =
    status === "approved"
      ? "positive"
      : status === "rejected"
        ? "danger"
        : status === "shortlisted"
          ? "warning"
          : status === "submitted" || status === "under_review"
            ? "accent"
            : "neutral";
  return <Pill tone={tone}>{status === "approved" ? "Won" : humanise(status)}</Pill>;
}

/** The score, or what is standing between the vendor and one. Never a fabricated number. */
function ScreeningScore({
  screening,
}: {
  screening?: { status: string; overall_score?: number | null } | null;
}) {
  if (!screening) return null;

  if (screening.status === "completed" && screening.overall_score != null) {
    return (
      <span className="text-sm font-semibold tabular-nums" title="Document readiness">
        {screening.overall_score}
        <span className="text-portal-faint">/100</span>
      </span>
    );
  }

  return <Pill tone="neutral">{humanise(screening.status)}</Pill>;
}
