import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Button } from "./ui";

const VENDOR_NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/projects", label: "Browse tenders" },
  { to: "/self-check", label: "AI self-check" },
  { to: "/company/profile", label: "Company profile" },
];

const COMPANY_NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/company/projects/new", label: "Post a project" },
  { to: "/company/profile", label: "Company profile" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const isCompany = user?.account_type === "company";
  const nav = isCompany ? COMPANY_NAV : VENDOR_NAV;

  return (
    <div className="min-h-screen grid grid-cols-[220px_1fr] max-md:grid-cols-1">
      {/* Left navigation rail */}
      <nav className="border-r border-rule bg-surface flex flex-col max-md:hidden">
        <Link to="/" className="px-5 py-6 border-b border-rule block group">
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block w-5 h-5 rounded-full"
              style={{
                background:
                  "conic-gradient(from 210deg, #ff8bd4, #7fe4ff, #a3ffcf, #ff8bd4)",
                boxShadow: "0 0 10px rgba(180,120,255,0.4)",
              }}
            />
            <div className="font-display text-xl leading-none">BidPilot</div>
          </div>
          <div className="text-[10px] uppercase tracking-widest text-signal mt-2">
            {isCompany ? "Company workspace" : "Vendor workspace"}
          </div>
        </Link>
        <div className="flex-1 py-4">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block px-5 py-2.5 text-sm border-l-2 ${
                  isActive
                    ? "border-signal text-ink font-semibold bg-paper"
                    : "border-transparent text-ink-muted hover:text-ink"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="px-5 py-4 border-t border-rule-soft text-xs text-ink-muted">
          Advisory only. AI output is not a legal opinion.
        </div>
      </nav>

      <div className="flex flex-col min-w-0">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rule bg-paper">
          <div className="flex items-center gap-3">
            {isCompany ? (
              <Link
                to="/company/projects/new"
                className="px-4 py-2 rounded-[3px] bg-signal text-white text-sm font-semibold hover:shadow-[3px_3px_0_var(--color-ink)]"
              >
                + New project
              </Link>
            ) : (
              <Link
                to="/projects"
                className="px-4 py-2 rounded-[3px] bg-ink text-paper text-sm font-medium hover:shadow-[3px_3px_0_var(--color-signal)]"
              >
                Browse tenders
              </Link>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm">
            {/* Notifications belong to the marketplace dashboards, not to this shell — this is
                the analysis workspace, and a bell here would poll an endpoint nothing on the
                page relates to. */}
            <span className="text-ink-muted max-sm:hidden">{user?.email}</span>
            <Button variant="ghost" onClick={logout}>
              Sign out
            </Button>
          </div>
        </header>
        <main className="flex-1 p-6 max-w-[1400px] w-full">{children}</main>
      </div>
    </div>
  );
}
