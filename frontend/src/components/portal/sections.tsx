import type { ReactNode } from "react";
import { Chip, GlassCard, PortalLinkButton, SectionHeading } from "./kit";
import { Reveal } from "./Reveal";
import { ProjectCard, ProjectCardSkeleton, type ProjectCardListing } from "./ProjectCard";
import { humanise } from "../../lib/format";

export interface CategoryOption {
  category: string;
  label?: string | null;
  count?: number;
}

/**
 * The category browser: pick a category, the grid below re-queries.
 *
 * The full taxonomy is shown, including categories with no live tenders, because the point of
 * this section is to tell a visitor whether the marketplace covers their trade at all. Hiding
 * the empty ones would answer "no" by omission.
 */
export function CategoryExplorer({
  categories,
  selected,
  onSelect,
  listings,
  loading,
  error,
}: {
  categories: CategoryOption[];
  selected: string | null;
  onSelect: (category: string | null) => void;
  listings: ProjectCardListing[];
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <section id="categories" className="px-5 py-20">
      <div className="mx-auto max-w-7xl">
        <Reveal>
          <SectionHeading
            eyebrow="Browse by category"
            title={
              <>
                {categories.length} procurement categories,
                <br className="hidden sm:block" /> one place
              </>
            }
            description="Pick a category to filter the live tender list. Counts are the number of tenders currently open for applications."
          />
        </Reveal>

        <Reveal delay={80}>
          <div className="mt-8 flex flex-wrap gap-2">
            <Chip active={selected === null} onClick={() => onSelect(null)}>
              All categories
            </Chip>
            {categories.map((option) => (
              <Chip
                key={option.category}
                active={selected === option.category}
                count={option.count}
                onClick={() => onSelect(option.category)}
              >
                {option.label ?? humanise(option.category)}
              </Chip>
            ))}
          </div>
        </Reveal>

        <div className="mt-10">
          <ListingGrid
            listings={listings}
            loading={loading}
            error={error}
            columns="lg:grid-cols-3"
            emptyTitle="No open tenders in this category"
            emptyBody="Nothing is currently accepting applications here. Try another category, or register to be ready when one opens."
          />
        </div>
      </div>
    </section>
  );
}

/** Shared grid used by the landing sections and the browse page. */
export function ListingGrid({
  listings,
  loading,
  error,
  columns = "lg:grid-cols-3",
  skeletonCount = 6,
  compact = false,
  emptyTitle = "No tenders found",
  emptyBody = "Try widening your filters.",
}: {
  listings: ProjectCardListing[];
  loading?: boolean;
  error?: string | null;
  columns?: string;
  skeletonCount?: number;
  compact?: boolean;
  emptyTitle?: string;
  emptyBody?: string;
}) {
  if (error) {
    return (
      <div className="portal-glass px-6 py-12 text-center">
        <p className="text-sm text-portal-rose">{error}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={`grid gap-5 sm:grid-cols-2 ${columns}`}>
        {Array.from({ length: skeletonCount }, (_, i) => (
          <ProjectCardSkeleton key={i} compact={compact} />
        ))}
      </div>
    );
  }

  if (listings.length === 0) {
    return (
      <div className="portal-glass px-6 py-14 text-center">
        <p className="text-lg font-semibold">{emptyTitle}</p>
        <p className="mx-auto mt-2 max-w-md text-sm text-portal-muted">{emptyBody}</p>
      </div>
    );
  }

  return (
    <div className={`grid gap-5 sm:grid-cols-2 ${columns}`}>
      {listings.map((listing, index) => (
        // Stagger caps out quickly: past a handful of cards a growing delay stops reading as
        // a cascade and starts reading as lag.
        <Reveal key={listing.id} delay={Math.min(index, 5) * 60}>
          <ProjectCard listing={listing} compact={compact} />
        </Reveal>
      ))}
    </div>
  );
}

/** The featured 6×2 grid on the landing page. */
export function FeaturedTenders({
  listings,
  loading,
  error,
}: {
  listings: ProjectCardListing[];
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <section className="px-5 py-20">
      <div className="mx-auto max-w-7xl">
        <Reveal>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <SectionHeading
              eyebrow="Closing soon"
              title="Open tenders"
              description="The next twelve tenders to close. Every one is accepting applications right now."
            />
            <PortalLinkButton to="/tenders" variant="ghost">
              View all tenders
            </PortalLinkButton>
          </div>
        </Reveal>

        <div className="mt-10">
          <ListingGrid
            listings={listings}
            loading={loading}
            error={error}
            columns="lg:grid-cols-3 xl:grid-cols-6"
            skeletonCount={12}
            compact
            emptyTitle="No open tenders right now"
            emptyBody="New opportunities are published regularly. Register to be notified when one matches your capability."
          />
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  {
    step: "01",
    title: "Describe your company",
    body: "Tell the search bar what you do, where you work, and how big you are. It reads the live tender list and ranks what fits.",
  },
  {
    step: "02",
    title: "Apply with your documents",
    body: "Upload your trade licence, financials, certifications and proposal. One application per tender, editable until you submit.",
  },
  {
    step: "03",
    title: "Get screened before the buyer sees it",
    body: "Text and OCR extraction reads every page, matches it against the buyer's checklist, and scores what is present, expired, unreadable or missing.",
  },
  {
    step: "04",
    title: "Fix the gaps, then send",
    body: "The score is arithmetic, not a model's opinion, and every match points at the page it came from. You see exactly what to fix.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="px-5 py-20">
      <div className="mx-auto max-w-7xl">
        <Reveal>
          <SectionHeading
            eyebrow="How it works"
            title="Screening that shows its working"
            description="A language model reads your documents and proposes what satisfies each requirement. Python verifies every quote against the page it claims to come from, then calculates the score."
            align="center"
          />
        </Reveal>

        <div className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((item, index) => (
            <Reveal key={item.step} delay={index * 80}>
              <GlassCard interactive className="h-full p-6">
                <span className="font-mono text-xs text-portal-cyan">{item.step}</span>
                <h3 className="mt-3 text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-portal-muted">{item.body}</p>
              </GlassCard>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

export function CtaBand({
  title,
  body,
  primary,
  secondary,
}: {
  title: ReactNode;
  body: string;
  primary: { to: string; label: string };
  secondary?: { to: string; label: string };
}) {
  return (
    <section className="px-5 py-20">
      <Reveal>
        <div className="portal-edge relative mx-auto max-w-5xl overflow-hidden rounded-3xl border border-portal-line bg-portal-deep/70 px-6 py-16 text-center backdrop-blur-xl sm:px-14">
          {/* Decorative glow, kept inside the panel so it cannot bleed into neighbouring sections. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-24 left-1/2 h-64 w-[36rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,var(--color-portal-violet),transparent_70%)] opacity-30 blur-3xl"
          />
          <h2 className="relative text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h2>
          <p className="relative mx-auto mt-4 max-w-2xl text-base leading-relaxed text-portal-muted">
            {body}
          </p>
          <div className="relative mt-8 flex flex-wrap items-center justify-center gap-3">
            <PortalLinkButton to={primary.to}>{primary.label}</PortalLinkButton>
            {secondary ? (
              <PortalLinkButton to={secondary.to} variant="ghost">
                {secondary.label}
              </PortalLinkButton>
            ) : null}
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/** Infinite category marquee — decorative, hidden from assistive technology. */
export function CategoryMarquee({ categories }: { categories: CategoryOption[] }) {
  if (categories.length === 0) return null;
  // The track is duplicated so the -50% translation lands exactly on a seam.
  const row = [...categories, ...categories];

  return (
    <div
      className="portal-marquee relative overflow-hidden border-y border-portal-line py-4"
      aria-hidden="true"
    >
      <div className="portal-marquee-track gap-3" style={{ ["--portal-marquee-duration" as string]: "60s" }}>
        {row.map((option, index) => (
          <span
            key={`${option.category}-${index}`}
            className="whitespace-nowrap rounded-full border border-portal-line px-4 py-1.5 text-sm text-portal-muted"
          >
            {option.label ?? humanise(option.category)}
          </span>
        ))}
      </div>
      {/* Feathered edges so items enter and leave rather than being cut off. */}
      <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-portal-void to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-portal-void to-transparent" />
    </div>
  );
}
