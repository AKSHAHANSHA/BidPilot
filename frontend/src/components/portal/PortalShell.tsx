import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { PortalLinkButton } from "./kit";
import { useAuth } from "../../lib/auth";

/** The wordmark. A drawn mark rather than an image so it stays crisp and themeable. */
export function PortalLogo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span className="relative inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[linear-gradient(135deg,var(--color-portal-violet),var(--color-portal-cyan))]">
        <span className="text-sm font-bold text-white">B</span>
      </span>
      {!compact ? (
        <span className="text-lg font-semibold tracking-tight">
          Bid<span className="text-portal-cyan">Pilot</span>
        </span>
      ) : null}
    </span>
  );
}

const PUBLIC_LINKS = [
  { to: "/tenders", label: "Browse tenders" },
  { to: "/categories", label: "Categories" },
  { to: "/how-it-works", label: "How it works" },
];

export function PortalNav() {
  const { user } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  // The bar only gains its backdrop once the page has moved, so at rest it sits directly on
  // the hero instead of cutting a band across it.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-40 transition-[background,border-color,backdrop-filter] duration-300 ${
        scrolled
          ? "border-b border-portal-line bg-portal-void/80 backdrop-blur-xl"
          : "border-b border-transparent"
      }`}
    >
      <nav className="mx-auto flex max-w-7xl items-center gap-6 px-5 py-4">
        <Link to="/" className="shrink-0">
          <PortalLogo />
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          {PUBLIC_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `rounded-full px-3.5 py-2 text-sm transition-colors ${
                  isActive ? "text-portal-ink" : "text-portal-muted hover:text-portal-ink"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </div>

        <div className="ml-auto hidden items-center gap-2 md:flex">
          {user ? (
            <PortalLinkButton to="/dashboard" variant="primary">
              Dashboard
            </PortalLinkButton>
          ) : (
            <>
              <PortalLinkButton to="/signin" variant="quiet">
                Sign in
              </PortalLinkButton>
              <PortalLinkButton to="/signup">Get started</PortalLinkButton>
            </>
          )}
        </div>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label="Toggle navigation"
          className="ml-auto rounded-lg border border-portal-line px-3 py-2 text-sm text-portal-muted md:hidden"
        >
          {open ? "Close" : "Menu"}
        </button>
      </nav>

      {open ? (
        <div className="border-t border-portal-line bg-portal-void/95 px-5 py-4 md:hidden">
          <div className="flex flex-col gap-1">
            {PUBLIC_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm text-portal-muted hover:bg-portal-deep hover:text-portal-ink"
              >
                {link.label}
              </Link>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            {user ? (
              <PortalLinkButton to="/dashboard" className="flex-1">
                Dashboard
              </PortalLinkButton>
            ) : (
              <>
                <PortalLinkButton to="/signin" variant="ghost" className="flex-1">
                  Sign in
                </PortalLinkButton>
                <PortalLinkButton to="/signup" className="flex-1">
                  Get started
                </PortalLinkButton>
              </>
            )}
          </div>
        </div>
      ) : null}
    </header>
  );
}

const FOOTER_GROUPS = [
  {
    title: "Marketplace",
    links: [
      { to: "/tenders", label: "Browse tenders" },
      { to: "/categories", label: "Categories" },
      { to: "/signup?type=company", label: "Publish a tender" },
    ],
  },
  {
    title: "Vendors",
    links: [
      { to: "/signup?type=vendor", label: "Register as vendor" },
      { to: "/how-it-works", label: "How screening works" },
      { to: "/signin", label: "Sign in" },
    ],
  },
  {
    title: "Project",
    links: [
      { to: "/about", label: "Engineering notes" },
      { to: "/how-it-works", label: "About BidPilot" },
    ],
  },
];

export function PortalFooter() {
  return (
    <footer className="mt-24 border-t border-portal-line bg-portal-deep/40">
      <div className="mx-auto max-w-7xl px-5 py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div>
            <PortalLogo />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-portal-muted">
              The UAE tender marketplace with AI document screening. Buyers publish, vendors bid,
              and every submission is checked against the requirement list before anyone reads it.
            </p>
          </div>

          {FOOTER_GROUPS.map((group) => (
            <div key={group.title}>
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-portal-faint">
                {group.title}
              </h3>
              <ul className="mt-4 space-y-2.5">
                {group.links.map((link) => (
                  <li key={link.to + link.label}>
                    <Link
                      to={link.to}
                      className="text-sm text-portal-muted transition-colors hover:text-portal-ink"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-portal-line pt-6 text-xs text-portal-faint sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} BidPilot. A portfolio project, not a government service.</p>
          <p>
            AI output is advisory. Readiness and screening scores are calculated in code, not by a
            language model.
          </p>
        </div>
      </div>
    </footer>
  );
}

/** Wraps every public page: opts into the theme and paints the ambient background once. */
export function PortalShell({ children }: { children: ReactNode }) {
  return (
    <div className="portal">
      <div className="portal-field" aria-hidden="true" />
      <div className="portal-grid" aria-hidden="true" />
      <PortalNav />
      <main>{children}</main>
      <PortalFooter />
    </div>
  );
}
