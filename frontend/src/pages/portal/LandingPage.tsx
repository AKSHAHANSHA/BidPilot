import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PortalShell } from "../../components/portal/PortalShell";
import { Hero } from "../../components/portal/Hero";
import {
  CategoryExplorer,
  CategoryMarquee,
  CtaBand,
  FeaturedTenders,
  HowItWorks,
  ListingGrid,
} from "../../components/portal/sections";
import { GlassCard, Pill, SectionHeading } from "../../components/portal/kit";
import { Reveal } from "../../components/portal/Reveal";
import { portal, type SearchResponse } from "../../api/portal";

export function LandingPage() {
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState<SearchResponse | null>(null);

  const stats = useQuery({ queryKey: ["portal", "stats"], queryFn: portal.stats });
  const categories = useQuery({ queryKey: ["portal", "categories"], queryFn: portal.categories });

  // Twelve, because the featured section is a 6×2 grid at its widest breakpoint.
  const featured = useQuery({
    queryKey: ["portal", "listings", "featured"],
    queryFn: () => portal.listings({ sort: "deadline", limit: 12 }),
  });

  const byCategory = useQuery({
    queryKey: ["portal", "listings", "category", category],
    queryFn: () => portal.listings({ category, sort: "deadline", limit: 6 }),
  });

  const searchMutation = useMutation({
    mutationFn: (query: string) => portal.search(query, 12),
    onSuccess: setSearch,
  });

  const runSearch = (query: string) => {
    setSearch(null);
    searchMutation.mutate(query);
    // Results render directly beneath the hero, so bring them into view rather than leaving
    // the reader wondering whether anything happened.
    window.requestAnimationFrame(() =>
      document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth" }),
    );
  };

  return (
    <PortalShell>
      <Hero
        onSearch={runSearch}
        searching={searchMutation.isPending}
        stats={stats.data ?? undefined}
      />

      {searchMutation.isPending || search || searchMutation.isError ? (
        <section id="search-results" className="px-5 pb-6">
          <div className="mx-auto max-w-7xl">
            <SectionHeading
              eyebrow="Matches for your company"
              title="What we found"
              description={
                search?.interpretation?.interpretation ??
                "Ranking is deterministic — the model only reads your description, it never orders the results."
              }
            />

            {search?.degraded ? (
              <div className="mt-4">
                <Pill tone="warning">
                  Keyword matching — no language model is configured on this deployment
                </Pill>
              </div>
            ) : null}

            {search && search.matches.length > 0 ? (
              <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {search.matches.map((match, index) => (
                  <Reveal key={match.listing.id} delay={Math.min(index, 5) * 60}>
                    <div className="flex h-full flex-col gap-2">
                      <MatchReasons reasons={match.reasons} score={match.score} />
                      <div className="flex-1">
                        <ListingGrid listings={[match.listing]} columns="" />
                      </div>
                    </div>
                  </Reveal>
                ))}
              </div>
            ) : null}

            {searchMutation.isPending ? (
              <div className="mt-8">
                <ListingGrid listings={[]} loading skeletonCount={6} />
              </div>
            ) : null}

            {search && search.matches.length === 0 ? (
              <GlassCard className="mt-8 px-6 py-12 text-center">
                <p className="text-sm text-portal-muted">
                  Nothing open matches that description right now. Try a broader phrase, or browse
                  the categories below.
                </p>
              </GlassCard>
            ) : null}

            {searchMutation.isError ? (
              <GlassCard className="mt-8 px-6 py-8 text-center">
                <p className="text-sm text-portal-rose">
                  {(searchMutation.error as Error).message}
                </p>
              </GlassCard>
            ) : null}
          </div>
        </section>
      ) : null}

      <FeaturedTenders
        listings={featured.data?.items ?? []}
        loading={featured.isPending}
        error={featured.isError ? (featured.error as Error).message : null}
      />

      <CategoryMarquee categories={categories.data ?? []} />

      <CategoryExplorer
        categories={categories.data ?? []}
        selected={category}
        onSelect={setCategory}
        listings={byCategory.data?.items ?? []}
        loading={byCategory.isPending}
        error={byCategory.isError ? (byCategory.error as Error).message : null}
      />

      <HowItWorks />

      <CtaBand
        title="Stop finding out what was missing after the deadline"
        body="Register as a vendor and every submission is screened against the buyer's checklist before you send it. Or publish a tender and see applicants ranked by what they actually supplied."
        primary={{ to: "/signup?type=vendor", label: "Register as a vendor" }}
        secondary={{ to: "/signup?type=company", label: "Publish a tender" }}
      />
    </PortalShell>
  );
}

function MatchReasons({ reasons, score }: { reasons: string[]; score: number }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Pill tone="accent">{Math.round(score * 100)}% match</Pill>
      {reasons.slice(0, 2).map((reason) => (
        <span key={reason} className="text-xs text-portal-faint">
          {reason}
        </span>
      ))}
    </div>
  );
}
