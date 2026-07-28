import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchCompanyDashboard,
  fetchCompanyProjects,
  fetchProjectApplicants,
  formatBudget,
  deadlineLabel,
  type ApplicationSummaryDto,
  type CompanyDashboardDto,
  type ProjectSummaryDto,
} from "../lib/marketplace";
import { Card, Spinner } from "../components/ui";
import { EmptyState, StatTile } from "../components/marketplace";

/**
 * Company dashboard: tenders you posted + who has applied, with each applicant's AI screening
 * score front and center. Selecting a project reveals its applicant list inline.
 */
export function CompanyDashboardPage() {
  const [summary, setSummary] = useState<CompanyDashboardDto | null>(null);
  const [projects, setProjects] = useState<ProjectSummaryDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [applicants, setApplicants] = useState<ApplicationSummaryDto[]>([]);
  const [applicantsLoading, setApplicantsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [dash, projs] = await Promise.all([
          fetchCompanyDashboard(),
          fetchCompanyProjects(),
        ]);
        if (!cancelled) {
          setSummary(dash);
          setProjects(projs);
          setSelectedId(projs[0]?.id ?? null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setApplicants([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setApplicantsLoading(true);
      try {
        const rows = await fetchProjectApplicants(selectedId);
        if (!cancelled) setApplicants(rows);
      } finally {
        if (!cancelled) setApplicantsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  if (loading || !summary) {
    return (
      <div className="p-8">
        <Spinner label="Loading your company dashboard…" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] text-ink-muted">Company</div>
          <h1 className="font-display text-4xl">Your tender pipeline</h1>
        </div>
        <Link
          to="/company/projects/new"
          className="px-4 py-2 rounded-[3px] bg-signal text-white text-sm font-semibold hover:shadow-[3px_3px_0_var(--color-ink)]"
        >
          + Post new project
        </Link>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Total projects" value={summary.total_projects} />
        <StatTile
          label="Open"
          value={summary.open_projects}
          tone={summary.open_projects > 0 ? "success" : "default"}
        />
        <StatTile
          label="Total applicants"
          value={summary.total_applicants}
          tone={summary.total_applicants > 0 ? "info" : "default"}
        />
        <StatTile
          label="Avg applicant score"
          value={summary.average_applicant_score ?? "—"}
          hint="Deterministic AI screening"
        />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
        <Card className="p-4">
          <h2 className="font-display text-lg mb-3">Your projects</h2>
          {projects.length === 0 ? (
            <EmptyState
              title="No projects yet"
              body="Post your first tender to start collecting AI-scored applicants."
              cta={
                <Link
                  to="/company/projects/new"
                  className="px-3 py-2 rounded-[3px] bg-ink text-paper text-sm font-medium"
                >
                  Post a project
                </Link>
              }
            />
          ) : (
            <ul className="space-y-1">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => setSelectedId(p.id)}
                    className={`w-full text-left px-3 py-2 rounded-[2px] border ${
                      selectedId === p.id
                        ? "border-ink bg-paper"
                        : "border-transparent hover:border-rule-soft"
                    }`}
                  >
                    <div className="font-medium text-sm line-clamp-2">{p.title}</div>
                    <div className="text-xs text-ink-muted mt-1 flex justify-between">
                      <span>{p.category.replaceAll("_", " ")}</span>
                      <span>{deadlineLabel(p.submission_deadline)}</span>
                    </div>
                    <div className="text-xs font-mono text-signal">
                      {formatBudget(p.budget_aed)}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-6">
          <h2 className="font-display text-xl mb-4">Applicants</h2>
          {applicantsLoading ? (
            <Spinner label="Loading applicants…" />
          ) : applicants.length === 0 ? (
            <EmptyState
              title="No applicants yet"
              body="Vendors' AI-screened applications will appear here as they submit."
            />
          ) : (
            <div className="space-y-3">
              {applicants.map((a) => (
                <div
                  key={a.id}
                  className="border border-rule-soft p-4 rounded-[3px] flex gap-4 items-start"
                >
                  <div className="text-center">
                    <div className="font-display text-3xl">{a.ai_score ?? "—"}</div>
                    <div className="text-xs text-ink-muted">/ 100</div>
                  </div>
                  <div className="flex-1">
                    <div className="text-sm text-ink-muted flex items-center gap-2">
                      <span className="inline-block px-2 py-0.5 text-xs border border-rule-soft rounded-sm uppercase tracking-widest">
                        {a.status.replace(/_/g, " ")}
                      </span>
                      <span>{new Date(a.submitted_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-2 text-sm">{a.ai_summary}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
