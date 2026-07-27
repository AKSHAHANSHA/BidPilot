import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Button } from "./ui";

const NAV = [
  { to: "/", label: "Tender Desk", end: true },
  { to: "/company", label: "Company Profile", end: false },
  { to: "/about", label: "Engineering Notes", end: false },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen grid grid-cols-[220px_1fr] max-md:grid-cols-1">
      {/* Narrow left navigation rail */}
      <nav className="border-r border-rule bg-surface flex flex-col max-md:hidden">
        <div className="px-5 py-6 border-b border-rule">
          <div className="font-display text-2xl leading-none">BidPilot</div>
          <div className="text-xs uppercase tracking-widest text-signal mt-1">UAE</div>
        </div>
        <div className="flex-1 py-4">
          {NAV.map((item) => (
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
        {/* Top utility strip */}
        <header className="flex items-center justify-between px-6 py-3 border-b border-rule bg-paper">
          <Button variant="primary" onClick={() => navigate("/tenders/new")}>
            + New Tender
          </Button>
          <div className="flex items-center gap-4 text-sm">
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
