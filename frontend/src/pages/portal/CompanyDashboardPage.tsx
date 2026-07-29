import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PortalShell } from "../../components/portal/PortalShell";
import { StatTile } from "../../components/portal/charts";
import {
  GlassCard,
  Pill,
  PortalButton,
  PortalSpinner,
  SectionHeading,
} from "../../components/portal/kit";
import { Reveal } from "../../components/portal/Reveal";
import { formatMoney, humanise } from "../../lib/format";
import { portal, type Applicant, type ListingDetail } from "../../api/portal";
import { useAuth } from "../../lib/auth";

/**
 * The buying organisation's view: its tenders, and who applied to each with their screening
 * score and the assessment behind it.
 */
export function CompanyDashboardPage() {
  const { user } = useAuth();
  const [selected, setSelected] = useState<string | null>(null);

  const listings = useQuery({
    queryKey: ["portal", "company", "listings"],
    queryFn: () => portal.myListings({ limit: 50 }),
  });

  const notifications = useQuery({
    queryKey: ["portal", "notifications"],
    queryFn: () => portal.notifications(),
    // Screening finishes in the background, so the buyer's list has to catch up on its own.
    refetchInterval: 30_000,
  });

  const items = listings.data?.items ?? [];
  const activeListingId = selected ?? items[0]?.id ?? null;
  const unread = (notifications.data?.items ?? []).filter((n) => !n.read_at);

  return (
    <PortalShell>
      <div className="mx-auto max-w-7xl px-5 py-12">
        <SectionHeading
          eyebrow={user?.organisation?.name ?? "Buying organisation"}
          title="Your tenders and applicants"
          description="Applicants are ranked by document readiness — how much of your requirement checklist their submission actually contained."
        />

        <Reveal>
          <div className="mt-10 grid gap-5 sm:grid-cols-3">
            <StatTile label="Published tenders" value={items.filter(isOpen).length} />
            <StatTile
              label="Total applicants"
              value={items.reduce((sum, l) => sum + (l.application_count ?? 0), 0)}
            />
            <StatTile
              label="Unread notifications"
              value={unread.length}
              tone={unread.length ? "warning" : "neutral"}
            />
          </div>
        </Reveal>

        <NotificationFeed />

        <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,20rem)_1fr]">
          <div className="lg:sticky lg:top-24 lg:self-start">
            <h2 className="text-sm font-semibold">Your tenders</h2>
            {listings.isPending ? (
              <div className="mt-4">
                <PortalSpinner label="Loading…" />
              </div>
            ) : null}
            <ul className="mt-4 space-y-2">
              {items.map((listing) => (
                <li key={listing.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(listing.id)}
                    aria-pressed={activeListingId === listing.id}
                    className={`w-full rounded-xl border p-3 text-left transition-colors ${
                      activeListingId === listing.id
                        ? "border-portal-violet bg-portal-violet/10"
                        : "border-portal-line bg-portal-deep/40 hover:border-portal-line-bright"
                    }`}
                  >
                    <p className="truncate text-sm font-medium">{listing.title}</p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <Pill tone={listing.status === "published" ? "positive" : "neutral"}>
                        {humanise(listing.status)}
                      </Pill>
                      <span className="text-xs text-portal-faint">
                        {listing.application_count ?? 0} applicant
                        {(listing.application_count ?? 0) === 1 ? "" : "s"}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
              {listings.isSuccess && items.length === 0 ? (
                <li className="rounded-xl border border-portal-line p-4 text-sm text-portal-muted">
                  You have not published a tender yet.
                </li>
              ) : null}
            </ul>
          </div>

          <div>{activeListingId ? <ApplicantList listingId={activeListingId} /> : null}</div>
        </div>
      </div>
    </PortalShell>
  );
}

const isOpen = (listing: ListingDetail) => listing.status === "published";

function NotificationFeed() {
  const queryClient = useQueryClient();
  const notifications = useQuery({
    queryKey: ["portal", "notifications"],
    queryFn: () => portal.notifications(),
    refetchInterval: 30_000,
  });

  const markAll = useMutation({
    mutationFn: portal.markAllNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal", "notifications"] }),
  });

  const items = notifications.data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <Reveal delay={80}>
      <div className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Notifications</h2>
          <PortalButton
            variant="quiet"
            onClick={() => markAll.mutate()}
            disabled={markAll.isPending || items.every((n) => n.read_at)}
          >
            Mark all read
          </PortalButton>
        </div>

        <ul className="mt-4 space-y-2">
          {items.slice(0, 6).map((notification) => (
            <li key={notification.id}>
              <GlassCard
                className={`flex flex-wrap items-center gap-3 p-4 ${
                  notification.read_at ? "opacity-60" : ""
                }`}
              >
                {!notification.read_at ? (
                  <span
                    aria-hidden="true"
                    className="h-2 w-2 shrink-0 rounded-full bg-portal-cyan"
                  />
                ) : null}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{notification.title}</p>
                  <p className="mt-0.5 text-xs text-portal-muted">{notification.body}</p>
                </div>
                {notification.screening_score != null ? (
                  <span className="text-sm font-semibold tabular-nums">
                    {notification.screening_score}
                    <span className="text-portal-faint">/100</span>
                  </span>
                ) : null}
              </GlassCard>
            </li>
          ))}
        </ul>
      </div>
    </Reveal>
  );
}

function ApplicantList({ listingId }: { listingId: string }) {
  const queryClient = useQueryClient();
  const applicants = useQuery({
    queryKey: ["portal", "company", "applicants", listingId],
    queryFn: () => portal.applicants(listingId),
  });

  const decide = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portal.decide(id, status),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["portal", "company", "applicants", listingId],
      }),
  });

  if (applicants.isPending) return <PortalSpinner label="Loading applicants…" />;
  if (applicants.isError) {
    return <GlassCard className="p-6 text-sm text-portal-rose">
      {(applicants.error as Error).message}
    </GlassCard>;
  }

  const items = applicants.data?.items ?? [];
  if (items.length === 0) {
    return (
      <GlassCard className="px-6 py-12 text-center">
        <p className="text-sm text-portal-muted">
          No applications yet. They appear here as soon as a vendor submits, with a screening
          score once their documents have been read.
        </p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold">
        {items.length} applicant{items.length === 1 ? "" : "s"}, best-scored first
      </h2>
      {items.map((applicant, index) => (
        <Reveal key={applicant.id} delay={Math.min(index, 5) * 60}>
          <ApplicantCard
            applicant={applicant}
            onDecide={(status) => decide.mutate({ id: applicant.id, status })}
            deciding={decide.isPending}
          />
        </Reveal>
      ))}
    </div>
  );
}

function ApplicantCard({
  applicant,
  onDecide,
  deciding,
}: {
  applicant: Applicant;
  onDecide: (status: string) => void;
  deciding: boolean;
}) {
  const screening = applicant.screening;
  const score = screening?.overall_score;
  const decided = applicant.status === "approved" || applicant.status === "rejected";

  return (
    <GlassCard className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 font-medium">
            {applicant.vendor_organisation.name}
            {applicant.vendor_organisation.is_verified ? (
              <span className="text-portal-cyan" title="Verified">
                ✓
              </span>
            ) : null}
          </p>
          <p className="mt-0.5 text-xs text-portal-muted">
            {humanise(applicant.vendor_organisation.emirate)}
            {applicant.bid_amount ? ` · bid ${formatMoney(applicant.bid_amount)}` : ""}
            {applicant.proposed_duration_months
              ? ` · ${applicant.proposed_duration_months} months`
              : ""}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {screening?.status === "completed" && score != null ? (
            <div className="text-right">
              <p className="text-2xl font-semibold leading-none tabular-nums">{score}</p>
              <p className="text-[11px] text-portal-faint">document readiness</p>
            </div>
          ) : screening ? (
            <Pill tone="neutral">{humanise(screening.status)}</Pill>
          ) : null}
          <Pill tone={applicant.status === "approved" ? "positive" : "neutral"}>
            {humanise(applicant.status)}
          </Pill>
        </div>
      </div>

      {screening?.status === "completed" ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-portal-line pt-4">
          <Pill tone={screening.has_blocking_gap ? "danger" : "positive"}>
            {screening.mandatory_met}/{screening.mandatory_total} mandatory documents
          </Pill>
          {screening.has_blocking_gap ? (
            <span className="text-xs text-portal-muted">
              A mandatory document was not found in this submission.
            </span>
          ) : (
            <span className="text-xs text-portal-muted">
              Every mandatory document was matched to a page of their upload.
            </span>
          )}
        </div>
      ) : null}

      {applicant.cover_letter ? (
        <p className="mt-4 line-clamp-3 text-sm leading-relaxed text-portal-muted">
          {applicant.cover_letter}
        </p>
      ) : null}

      {!decided ? (
        <div className="mt-5 flex flex-wrap gap-2">
          <PortalButton onClick={() => onDecide("shortlisted")} disabled={deciding} variant="ghost">
            Shortlist
          </PortalButton>
          <PortalButton onClick={() => onDecide("approved")} disabled={deciding}>
            Award
          </PortalButton>
          <PortalButton onClick={() => onDecide("rejected")} disabled={deciding} variant="quiet">
            Reject
          </PortalButton>
        </div>
      ) : null}
    </GlassCard>
  );
}
