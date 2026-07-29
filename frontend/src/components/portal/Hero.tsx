import { useEffect, useState, type FormEvent } from "react";
import { Eyebrow, GradientText, PortalLinkButton, PortalSpinner } from "./kit";
import { Reveal } from "./Reveal";

const EXAMPLE_QUERIES = [
  "MEP contractor in Sharjah, 40 staff, ISO 9001",
  "We build district cooling plants in Abu Dhabi",
  "IT consultancy — cybersecurity audits for government",
  "Facilities management, 200 staff, all seven emirates",
  "Landscaping and irrigation, projects up to AED 5M",
];

interface HeroStats {
  published_listings?: number;
  buyer_count?: number;
  total_value?: string | number | null;
  category_count?: number;
}

/**
 * The hero, including the search bar that is the page's primary action.
 *
 * Presentational: it owns the input text and the placeholder rotation, and hands the submitted
 * query to the caller. Fetching, ranking, and the "no model ran" degraded state belong to the
 * page, which knows about the API.
 */
export function Hero({
  onSearch,
  searching = false,
  stats,
}: {
  onSearch: (query: string) => void;
  searching?: boolean;
  stats?: HeroStats;
}) {
  const [query, setQuery] = useState("");
  const [exampleIndex, setExampleIndex] = useState(0);

  // The placeholder cycles only while the field is empty and untouched — once someone is
  // typing, a moving placeholder underneath is a distraction.
  useEffect(() => {
    if (query) return;
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    const timer = window.setInterval(
      () => setExampleIndex((i) => (i + 1) % EXAMPLE_QUERIES.length),
      3800,
    );
    return () => window.clearInterval(timer);
  }, [query]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed) onSearch(trimmed);
  };

  return (
    <section className="relative overflow-hidden px-5 pb-20 pt-16 sm:pt-24">
      <div className="mx-auto max-w-4xl text-center">
        <Reveal>
          <Eyebrow>Live UAE tender marketplace</Eyebrow>
        </Reveal>

        <Reveal delay={80}>
          <h1 className="mt-6 text-4xl font-semibold leading-[1.08] tracking-tight sm:text-6xl">
            Find the tenders your
            <br />
            company can <GradientText>actually win</GradientText>
          </h1>
        </Reveal>

        <Reveal delay={160}>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-portal-muted sm:text-lg">
            Describe what your company does. BidPilot reads the live tender list, matches it
            against your capability, and screens your submission documents before you send them —
            so you find out what is missing while you can still fix it.
          </p>
        </Reveal>

        {/* Search */}
        <Reveal delay={240}>
          <form onSubmit={submit} className="mx-auto mt-10 max-w-2xl">
            <div className="portal-edge relative overflow-hidden rounded-full">
              {/* The sweep sits behind the field and is clipped by the rounded container. */}
              <span className="portal-sweep absolute inset-0 overflow-hidden rounded-full opacity-40" />
              <div className="relative m-[1px] flex items-center gap-2 rounded-full bg-portal-deep/90 p-1.5 backdrop-blur-xl">
                <label htmlFor="hero-search" className="sr-only">
                  Describe your company to find matching tenders
                </label>
                <input
                  id="hero-search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={EXAMPLE_QUERIES[exampleIndex]}
                  maxLength={500}
                  autoComplete="off"
                  className="min-h-12 w-full bg-transparent px-5 text-sm text-portal-ink outline-none placeholder:text-portal-faint sm:text-base"
                />
                <button
                  type="submit"
                  disabled={searching || !query.trim()}
                  className="min-h-12 shrink-0 rounded-full bg-[linear-gradient(100deg,var(--color-portal-violet),var(--color-portal-cyan))] px-6 text-sm font-semibold text-white transition-transform duration-200 hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
                >
                  {searching ? "Matching…" : "Find tenders"}
                </button>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              <span className="text-xs text-portal-faint">Try:</span>
              {EXAMPLE_QUERIES.slice(0, 3).map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => {
                    setQuery(example);
                    onSearch(example);
                  }}
                  className="rounded-full border border-portal-line px-3 py-1 text-xs text-portal-muted transition-colors hover:border-portal-line-bright hover:text-portal-ink"
                >
                  {example}
                </button>
              ))}
            </div>

            {searching ? (
              <div className="mt-4 flex justify-center">
                <PortalSpinner label="Reading the tender list…" />
              </div>
            ) : null}
          </form>
        </Reveal>

        <Reveal delay={320}>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <PortalLinkButton to="/signup?type=vendor">Register as a vendor</PortalLinkButton>
            <PortalLinkButton to="/signup?type=company" variant="ghost">
              Publish a tender
            </PortalLinkButton>
          </div>
        </Reveal>
      </div>

      {stats ? (
        <Reveal delay={400}>
          <dl className="mx-auto mt-16 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-portal-line bg-portal-line sm:grid-cols-4">
            <Stat label="Open tenders" value={stats.published_listings} />
            <Stat label="Buying bodies" value={stats.buyer_count} />
            <Stat label="Categories" value={stats.category_count} />
            <Stat label="Published value" value={stats.total_value} money />
          </dl>
        </Reveal>
      ) : null}
    </section>
  );
}

function Stat({
  label,
  value,
  money = false,
}: {
  label: string;
  value?: string | number | null;
  money?: boolean;
}) {
  // An absent figure shows an em dash. Rendering 0 for "we did not load this" would be a
  // fabricated statistic on the most prominent part of the page.
  const display =
    value === null || value === undefined
      ? "—"
      : money
        ? formatCompactAed(value)
        : new Intl.NumberFormat("en-AE").format(Number(value));

  return (
    <div className="bg-portal-deep px-5 py-6 text-center">
      <dt className="text-xs uppercase tracking-wide text-portal-faint">{label}</dt>
      <dd className="mt-1.5 text-2xl font-semibold tabular-nums">{display}</dd>
    </div>
  );
}

function formatCompactAed(value: string | number) {
  const amount = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(amount)) return "—";
  if (amount >= 1_000_000_000) return `AED ${(amount / 1_000_000_000).toFixed(1)}B`;
  if (amount >= 1_000_000) return `AED ${Math.round(amount / 1_000_000)}M`;
  if (amount >= 1_000) return `AED ${Math.round(amount / 1_000)}K`;
  return `AED ${Math.round(amount)}`;
}
