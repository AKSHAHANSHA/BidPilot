import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchCategories,
  fetchPublicProjects,
  type CategoryDto,
  type ProjectSummaryDto,
} from "../lib/marketplace";
import { ProjectCard } from "../components/marketplace";

/**
 * TenderSphere public landing page.
 *
 * Web3-flavored dark hero with an animated aurora background, chat-style AI search input,
 * a 6×2 featured-project grid, a scrolling category strip, a CTA band, and a footer.
 * No 3D libs — pure CSS gradients and keyframes so the bundle stays small.
 */
export function LandingPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<CategoryDto[]>([]);
  const [projects, setProjects] = useState<ProjectSummaryDto[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [cats, list] = await Promise.all([
          fetchCategories(),
          fetchPublicProjects({ limit: 12 }),
        ]);
        if (!cancelled) {
          setCategories(cats);
          setProjects(list.items);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const categoryBySlug = useMemo(() => {
    const map: Record<string, CategoryDto> = {};
    for (const c of categories) map[c.slug] = c;
    return map;
  }, [categories]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (q) navigate(`/projects?q=${encodeURIComponent(q)}`);
    else navigate("/projects");
  }

  return (
    <div className="bg-[#08090f] text-white min-h-screen">
      <PublicHeader transparent />

      {/* --- Hero ---------------------------------------------------------- */}
      <section className="relative overflow-hidden">
        <AuroraBackground />
        <div className="relative max-w-6xl mx-auto px-6 pt-16 pb-24 sm:pt-24 sm:pb-32 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/15 bg-white/5 text-xs uppercase tracking-widest text-white/70 mb-6 animate-fade-in">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Live UAE government tenders
          </div>
          <h1 className="font-display text-5xl sm:text-6xl md:text-7xl leading-[1.05] tracking-tight animate-fade-up">
            Find the right tender.
            <br />
            <span className="bg-gradient-to-r from-fuchsia-300 via-sky-300 to-emerald-300 bg-clip-text text-transparent">
              Bid with confidence.
            </span>
          </h1>
          <p className="mt-6 text-white/70 max-w-2xl mx-auto text-lg animate-fade-up [animation-delay:120ms]">
            TenderSphere brings every public-sector opportunity into one place, screens each
            vendor submission with explainable AI, and gives your company the signal it needs
            before spending days on a bid.
          </p>

          <form
            onSubmit={submitSearch}
            className="mt-10 max-w-2xl mx-auto animate-fade-up [animation-delay:240ms]"
          >
            <div className="relative flex items-center rounded-2xl border border-white/15 bg-white/5 backdrop-blur-md pl-5 pr-2 py-2 shadow-[0_0_60px_-20px_rgba(180,120,255,0.7)]">
              <span className="text-white/60 mr-3" aria-hidden>
                ✨
              </span>
              <input
                aria-label="Describe your company or the tender you are looking for"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Tell us what your company does — e.g. facilities management in Dubai"
                className="flex-1 bg-transparent outline-none py-2 text-base placeholder:text-white/40"
              />
              <button
                type="submit"
                className="ml-2 px-4 py-2 rounded-xl bg-white text-black text-sm font-semibold hover:bg-white/90"
              >
                Find tenders →
              </button>
            </div>
            <div className="text-xs text-white/40 mt-2">
              AI-ranked results across {projects.length ? projects.length : "hundreds of"} live
              opportunities.
            </div>
          </form>

          <div className="mt-12 flex items-center justify-center gap-3 text-xs uppercase tracking-widest text-white/40">
            <div className="h-px w-8 bg-white/20" />
            Trusted by UAE contractors, service providers and government buyers
            <div className="h-px w-8 bg-white/20" />
          </div>
        </div>
      </section>

      {/* --- Featured projects -------------------------------------------- */}
      <section className="relative">
        <div className="max-w-6xl mx-auto px-6 pt-20 pb-16">
          <div className="flex items-end justify-between mb-8">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] text-white/40">
                Live opportunities
              </div>
              <h2 className="font-display text-3xl sm:text-4xl mt-2">Featured projects</h2>
            </div>
            <Link
              to="/projects"
              className="hidden sm:inline text-sm text-white/70 hover:text-white underline underline-offset-4"
            >
              Browse all →
            </Link>
          </div>
          {loading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {Array.from({ length: 12 }).map((_, i) => (
                <div
                  key={i}
                  className="aspect-[3/4] rounded-lg bg-white/[0.04] animate-pulse border border-white/5"
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {projects.slice(0, 12).map((p) => (
                <ProjectCard
                  key={p.id}
                  project={p}
                  categoryLabel={categoryBySlug[p.category]?.label}
                  variant="dark"
                />
              ))}
            </div>
          )}
          <div className="mt-8 text-center sm:hidden">
            <Link
              to="/projects"
              className="text-sm text-white/70 hover:text-white underline underline-offset-4"
            >
              Browse all projects →
            </Link>
          </div>
        </div>
      </section>

      {/* --- Categories --------------------------------------------------- */}
      <section className="border-t border-white/10 bg-white/[0.02]">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="text-xs uppercase tracking-[0.3em] text-white/40">Categories</div>
          <h2 className="font-display text-3xl sm:text-4xl mt-2">Every sector, one portal.</h2>
          <p className="text-white/60 mt-3 max-w-xl">
            Pick a category to filter live opportunities — from metro-station FM to solar EPC.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {categories.map((c) => (
              <Link
                key={c.slug}
                to={`/projects?category=${c.slug}`}
                className="group inline-flex items-center gap-2 px-4 py-2 rounded-full border border-white/15 bg-white/5 hover:border-white/40 hover:bg-white/10 text-sm transition-colors"
              >
                <span aria-hidden>{c.icon}</span>
                <span>{c.label}</span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* --- CTA band ----------------------------------------------------- */}
      <section className="relative overflow-hidden border-t border-white/10">
        <div
          className="absolute inset-0 opacity-70"
          style={{
            background:
              "radial-gradient(1000px 400px at 20% 0%, rgba(180,120,255,0.35), transparent), radial-gradient(800px 400px at 80% 100%, rgba(90,220,255,0.25), transparent)",
          }}
        />
        <div className="relative max-w-4xl mx-auto px-6 py-24 text-center">
          <h2 className="font-display text-4xl sm:text-5xl leading-tight">
            Ready to bid smarter?
          </h2>
          <p className="text-white/70 mt-4 max-w-2xl mx-auto">
            Create an account in under a minute. Vendors get AI screening of every application;
            companies get scored applicants and a live pipeline dashboard.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              to="/auth?mode=register&role=vendor"
              className="px-6 py-3 rounded-lg bg-white text-black font-semibold hover:bg-white/90"
            >
              Register as a Vendor
            </Link>
            <Link
              to="/auth?mode=register&role=company"
              className="px-6 py-3 rounded-lg border border-white/30 hover:border-white/60"
            >
              Register as a Company
            </Link>
            <Link
              to="/auth?mode=login"
              className="px-6 py-3 rounded-lg text-white/70 hover:text-white"
            >
              Sign in →
            </Link>
          </div>
        </div>
      </section>

      <PublicFooter />

      <style>{keyframesCss}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public header used across landing / projects / auth (dark theme)
// ---------------------------------------------------------------------------

export function PublicHeader({ transparent = false }: { transparent?: boolean }) {
  return (
    <header
      className={`sticky top-0 z-20 border-b ${
        transparent
          ? "bg-[#08090f]/70 backdrop-blur-md border-white/10"
          : "bg-[#08090f] border-white/10"
      }`}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between text-white">
        <Link to="/" className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block w-6 h-6 rounded-full"
            style={{
              background:
                "conic-gradient(from 210deg, #ff8bd4, #7fe4ff, #a3ffcf, #ff8bd4)",
              boxShadow: "0 0 20px rgba(180,120,255,0.6)",
            }}
          />
          <span className="font-display text-xl tracking-tight">TenderSphere</span>
        </Link>
        <nav className="hidden sm:flex items-center gap-6 text-sm text-white/70">
          <Link to="/projects" className="hover:text-white">
            Projects
          </Link>
          <a href="/#categories" className="hover:text-white">
            Categories
          </a>
        </nav>
        <div className="flex items-center gap-3">
          <Link
            to="/auth?mode=login"
            className="text-sm text-white/70 hover:text-white hidden sm:inline"
          >
            Sign in
          </Link>
          <Link
            to="/auth?mode=register"
            className="px-4 py-2 rounded-lg bg-white text-black text-sm font-semibold hover:bg-white/90"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="border-t border-white/10 bg-[#05060b] text-white/60">
      <div className="max-w-6xl mx-auto px-6 py-12 grid gap-8 sm:grid-cols-4">
        <div className="sm:col-span-2">
          <div className="flex items-center gap-2 text-white">
            <span
              aria-hidden
              className="inline-block w-6 h-6 rounded-full"
              style={{
                background:
                  "conic-gradient(from 210deg, #ff8bd4, #7fe4ff, #a3ffcf, #ff8bd4)",
              }}
            />
            <span className="font-display text-xl">TenderSphere</span>
          </div>
          <p className="mt-3 text-sm max-w-sm">
            One portal for UAE government-sector tenders — AI-ranked, cited, and explainable.
          </p>
          <p className="mt-4 text-xs text-white/40">
            Advisory only. AI output is not a legal opinion or an award decision.
          </p>
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest text-white/40 mb-3">Product</div>
          <ul className="space-y-2 text-sm">
            <li>
              <Link to="/projects" className="hover:text-white">
                Browse projects
              </Link>
            </li>
            <li>
              <Link to="/auth?mode=register&role=vendor" className="hover:text-white">
                For vendors
              </Link>
            </li>
            <li>
              <Link to="/auth?mode=register&role=company" className="hover:text-white">
                For companies
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest text-white/40 mb-3">Contact</div>
          <ul className="space-y-2 text-sm">
            <li>support@tendersphere.ae</li>
            <li>+971 4 000 0000</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10 text-center text-xs py-4 text-white/40">
        © {new Date().getFullYear()} TenderSphere — a BidPilot portfolio project.
      </div>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Aurora background
// ---------------------------------------------------------------------------

function AuroraBackground() {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {/* Ambient orbs */}
      <div
        className="absolute -top-32 -left-32 w-[600px] h-[600px] rounded-full blur-[120px] opacity-60 animate-orb-a"
        style={{ background: "radial-gradient(circle, #b46bff, transparent 60%)" }}
      />
      <div
        className="absolute top-20 -right-32 w-[500px] h-[500px] rounded-full blur-[120px] opacity-50 animate-orb-b"
        style={{ background: "radial-gradient(circle, #4bc8ff, transparent 60%)" }}
      />
      <div
        className="absolute bottom-0 left-1/3 w-[500px] h-[500px] rounded-full blur-[120px] opacity-40 animate-orb-c"
        style={{ background: "radial-gradient(circle, #4dffb5, transparent 60%)" }}
      />
      {/* Grid overlay */}
      <div
        className="absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.4) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage:
            "radial-gradient(ellipse at center, black 40%, transparent 75%)",
          WebkitMaskImage:
            "radial-gradient(ellipse at center, black 40%, transparent 75%)",
        }}
      />
    </div>
  );
}

const keyframesCss = `
@keyframes fade-in { from { opacity: 0 } to { opacity: 1 } }
@keyframes fade-up { from { opacity: 0; transform: translateY(12px) } to { opacity: 1; transform: none } }
@keyframes orb-a { 0%,100% { transform: translate(0,0) scale(1) } 50% { transform: translate(80px,60px) scale(1.15) } }
@keyframes orb-b { 0%,100% { transform: translate(0,0) scale(1) } 50% { transform: translate(-60px,80px) scale(1.1) } }
@keyframes orb-c { 0%,100% { transform: translate(0,0) scale(1) } 50% { transform: translate(40px,-70px) scale(1.2) } }
.animate-fade-in { animation: fade-in 700ms ease-out both }
.animate-fade-up { animation: fade-up 800ms ease-out both }
.animate-orb-a { animation: orb-a 18s ease-in-out infinite }
.animate-orb-b { animation: orb-b 22s ease-in-out infinite }
.animate-orb-c { animation: orb-c 26s ease-in-out infinite }
@media (prefers-reduced-motion: reduce) {
  .animate-orb-a, .animate-orb-b, .animate-orb-c { animation: none }
}
`;
