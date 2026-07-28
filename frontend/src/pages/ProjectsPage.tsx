import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  fetchCategories,
  fetchPublicProjects,
  type CategoryDto,
  type ProjectSummaryDto,
} from "../lib/marketplace";
import { ProjectCard } from "../components/marketplace";
import { PublicFooter, PublicHeader } from "./LandingPage";

/**
 * Browse marketplace projects with a left filter rail and a right card grid.
 * All filter state lives in the URL so a search can be shared and back/forward works.
 */
export function ProjectsPage() {
  const [params, setParams] = useSearchParams();
  const category = params.get("category") ?? "";
  const q = params.get("q") ?? "";
  const budgetMin = params.get("budget_min") ?? "";
  const budgetMax = params.get("budget_max") ?? "";

  const [projects, setProjects] = useState<ProjectSummaryDto[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<CategoryDto[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await fetchPublicProjects({
          category: category || undefined,
          q: q || undefined,
          budget_min: budgetMin ? Number(budgetMin) : undefined,
          budget_max: budgetMax ? Number(budgetMax) : undefined,
          limit: 36,
        });
        if (!cancelled) {
          setProjects(res.items);
          setTotal(res.total);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [category, q, budgetMin, budgetMax]);

  const categoryBySlug = useMemo(() => {
    const map: Record<string, CategoryDto> = {};
    for (const c of categories) map[c.slug] = c;
    return map;
  }, [categories]);

  function update(next: Record<string, string>) {
    const nextParams = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === "") nextParams.delete(key);
      else nextParams.set(key, value);
    }
    setParams(nextParams, { replace: false });
  }

  return (
    <div className="bg-[#08090f] text-white min-h-screen flex flex-col">
      <PublicHeader />
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-8">
        {/* --- Filter rail ------------------------------------------------ */}
        <aside className="lg:sticky lg:top-24 lg:self-start rounded-xl border border-white/10 bg-white/[0.03] p-5 space-y-5">
          <div>
            <div className="text-xs uppercase tracking-widest text-white/40">Search</div>
            <input
              value={q}
              onChange={(e) => update({ q: e.target.value })}
              placeholder="Keyword"
              className="mt-2 w-full rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-3 py-2 text-sm"
            />
          </div>

          <div>
            <div className="text-xs uppercase tracking-widest text-white/40 mb-2">Category</div>
            <div className="max-h-72 overflow-y-auto pr-1 space-y-1 -mx-1">
              <button
                onClick={() => update({ category: "" })}
                className={`w-full text-left text-sm px-2 py-1.5 rounded-md ${
                  category === "" ? "bg-white/10 text-white" : "text-white/60 hover:text-white"
                }`}
              >
                All categories ({total})
              </button>
              {categories.map((c) => (
                <button
                  key={c.slug}
                  onClick={() => update({ category: c.slug })}
                  className={`w-full text-left text-sm px-2 py-1.5 rounded-md flex items-center gap-2 ${
                    category === c.slug
                      ? "bg-white/10 text-white"
                      : "text-white/60 hover:text-white"
                  }`}
                >
                  <span aria-hidden>{c.icon}</span>
                  <span className="truncate">{c.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs uppercase tracking-widest text-white/40 mb-2">
              Budget (AED)
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                min={0}
                placeholder="Min"
                value={budgetMin}
                onChange={(e) => update({ budget_min: e.target.value })}
                className="rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-2 py-1.5 text-sm"
              />
              <input
                type="number"
                min={0}
                placeholder="Max"
                value={budgetMax}
                onChange={(e) => update({ budget_max: e.target.value })}
                className="rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-2 py-1.5 text-sm"
              />
            </div>
          </div>

          {(category || q || budgetMin || budgetMax) && (
            <button
              onClick={() =>
                setParams(new URLSearchParams(), { replace: true })
              }
              className="w-full text-xs text-white/70 underline underline-offset-4 hover:text-white"
            >
              Clear all filters
            </button>
          )}
        </aside>

        {/* --- Card grid --------------------------------------------------- */}
        <section>
          <div className="flex items-end justify-between mb-6">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] text-white/40">Projects</div>
              <h1 className="font-display text-3xl sm:text-4xl mt-1">
                {q ? `Results for "${q}"` : category
                  ? categoryBySlug[category]?.label ?? "Category"
                  : "All open projects"}
              </h1>
            </div>
            <div className="text-sm text-white/60">
              {loading ? "Loading…" : `${projects.length} of ${total}`}
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="aspect-[3/4] rounded-lg bg-white/[0.04] animate-pulse border border-white/5"
                />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <div className="border border-dashed border-white/15 rounded-xl p-12 text-center">
              <div className="font-display text-2xl">No matching projects</div>
              <div className="text-sm text-white/60 mt-2">
                Try broadening your keywords or clearing the filters.
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {projects.map((p) => (
                <ProjectCard
                  key={p.id}
                  project={p}
                  categoryLabel={categoryBySlug[p.category]?.label}
                  variant="dark"
                />
              ))}
            </div>
          )}
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
