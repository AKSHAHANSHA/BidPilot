import { Link } from "react-router-dom";
import { GlassCard, Pill, Tag } from "./kit";
import { describeDeadline, formatBudgetRange, formatDate, humanise } from "../../lib/format";

/**
 * The shape a card needs to render.
 *
 * Declared as what this component *requires* rather than imported from the generated API
 * types, so the card is usable with a listing summary, a search hit, or a seeded fixture.
 * TypeScript is structural, so the real API responses satisfy it without any mapping layer,
 * and a field the API renames will still fail the build at the call site.
 */
export interface ProjectCardListing {
  id: string;
  title: string;
  summary: string;
  category: string;
  category_label?: string | null;
  emirate: string;
  city?: string | null;
  budget_min?: string | number | null;
  budget_max?: string | number | null;
  currency?: string;
  submission_deadline?: string | null;
  days_remaining?: number | null;
  cover_image_url?: string | null;
  application_count?: number;
  tags?: string[];
  organisation?: { name: string; emirate?: string; is_verified?: boolean } | null;
  requirement_count?: number | null;
}

/**
 * A single opportunity.
 *
 * `compact` drops the image and the secondary metadata for the landing grid, where twelve
 * cards share the viewport and the job is to scan; the full form is for the dashboard, where
 * the reader is deciding whether to bid.
 */
export function ProjectCard({
  listing,
  to,
  compact = false,
}: {
  listing: ProjectCardListing;
  to?: string;
  compact?: boolean;
}) {
  const deadline = describeDeadline(listing.submission_deadline, listing.days_remaining);
  const budget = formatBudgetRange(listing.budget_min, listing.budget_max, listing.currency);
  const category = listing.category_label ?? humanise(listing.category);
  const href = to ?? `/tenders/${listing.id}`;

  return (
    <GlassCard interactive className="group relative flex h-full flex-col overflow-hidden">
      {!compact && listing.cover_image_url ? (
        <div className="relative h-36 overflow-hidden border-b border-portal-line">
          <img
            src={listing.cover_image_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover opacity-70 transition-[transform,opacity] duration-500 group-hover:scale-105 group-hover:opacity-90"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-portal-deep via-portal-deep/30 to-transparent" />
        </div>
      ) : null}

      <div className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <Pill tone="accent">{category}</Pill>
          <Pill tone={deadline.tone === "neutral" ? "neutral" : deadline.tone}>
            {deadline.label}
          </Pill>
        </div>

        <h3 className="text-base font-semibold leading-snug">
          <Link to={href} className="transition-colors hover:text-portal-cyan">
            {/* Stretched link: the whole card is the hit target, but only one link is in the
                accessibility tree, so a screen reader is not read twelve duplicate links. */}
            <span className="absolute inset-0" aria-hidden="true" />
            {listing.title}
          </Link>
        </h3>

        {listing.organisation ? (
          <p className="flex items-center gap-1.5 text-xs text-portal-muted">
            <span className="truncate">{listing.organisation.name}</span>
            {listing.organisation.is_verified ? (
              <span className="text-portal-cyan" title="Verified buyer">
                ✓
              </span>
            ) : null}
          </p>
        ) : null}

        <p className={`text-sm leading-relaxed text-portal-muted ${compact ? "line-clamp-2" : "line-clamp-3"}`}>
          {listing.summary}
        </p>

        {!compact && listing.tags?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {listing.tags.slice(0, 3).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
        ) : null}

        <dl className="mt-auto grid grid-cols-2 gap-3 border-t border-portal-line pt-3 text-xs">
          <div>
            <dt className="text-portal-faint">Contract value</dt>
            <dd className="mt-0.5 font-semibold text-portal-ink">{budget}</dd>
          </div>
          <div>
            <dt className="text-portal-faint">Closes</dt>
            <dd className="mt-0.5 font-semibold text-portal-ink">
              {formatDate(listing.submission_deadline) ?? "—"}
            </dd>
          </div>
          {!compact ? (
            <>
              <div>
                <dt className="text-portal-faint">Location</dt>
                <dd className="mt-0.5 text-portal-muted">
                  {listing.city ? `${listing.city}, ` : ""}
                  {humanise(listing.emirate)}
                </dd>
              </div>
              <div>
                <dt className="text-portal-faint">
                  {listing.requirement_count != null ? "Documents required" : "Applicants"}
                </dt>
                <dd className="mt-0.5 text-portal-muted">
                  {listing.requirement_count ?? listing.application_count ?? 0}
                </dd>
              </div>
            </>
          ) : null}
        </dl>
      </div>
    </GlassCard>
  );
}

export function ProjectCardSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className="portal-glass h-full overflow-hidden">
      {!compact ? <div className="portal-shimmer h-36" /> : null}
      <div className="space-y-3 p-5">
        <div className="portal-shimmer h-5 w-28 rounded-full" />
        <div className="portal-shimmer h-4 w-4/5 rounded" />
        <div className="portal-shimmer h-3 w-full rounded" />
        <div className="portal-shimmer h-3 w-2/3 rounded" />
        <div className="portal-shimmer h-8 w-full rounded" />
      </div>
    </div>
  );
}
