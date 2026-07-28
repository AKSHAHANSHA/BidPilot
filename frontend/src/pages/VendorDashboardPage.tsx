import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchVendorDashboard,
  fetchVendorApplications,
  type ApplicationSummaryDto,
  type VendorDashboardDto,
} from "../lib/marketplace";
import { Card, Spinner } from "../components/ui";
import { BarRow, EmptyState, StatTile } from "../components/marketplace";

/**
 * Vendor dashboard — two conceptual pages in one route:
 *
 * 1. Top: a stats & charts strip aggregating this vendor's applications.
 * 2. Bottom: the list of applications with AI score, status, and links back to the project.
 *
 * The old BidPilot bid-readiness self-check is linked from here as an internal tool.
 */
export function VendorDashboardPage() {
  const [data, setData] = useState<VendorDashboardDto | null>(null);
  const [list, setList] = useState<ApplicationSummaryDto[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [summary, apps] = await Promise.all([
          fetchVendorDashboard(),
          fetchVendorApplications(),
        ]);
        if (!cancelled) {
          setData(summary);
          setList(apps);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading || !data) {
    return (
      <div className="p-8">
        <Spinner label="Loading your dashboard…" />
      </div>
    );
  }

  const max = Math.max(
    data.total_applications,
    data.submitted,
    data.screened,
    data.shortlisted,
    data.rejected,
    1,
  );

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] text-ink-muted">Vendor</div>
          <h1 className="font-display text-4xl">Your pipeline</h1>
        </div>
        <div className="flex gap-2">
          <Link
            to="/projects"
            className="px-4 py-2 rounded-[3px] bg-ink text-paper text-sm font-medium hover:shadow-[3px_3px_0_var(--color-signal)]"
          >
            Browse new tenders
          </Link>
          <Link
            to="/self-check"
            className="px-4 py-2 rounded-[3px] border border-rule-soft hover:border-ink text-sm text-ink-muted hover:text-ink"
          >
            AI self-check tool
          </Link>
        </div>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatTile label="Applications" value={data.total_applications} />
        <StatTile
          label="Screened"
          value={data.screened}
          tone={data.screened > 0 ? "info" : "default"}
        />
        <StatTile
          label="Shortlisted"
          value={data.shortlisted}
          tone={data.shortlisted > 0 ? "success" : "default"}
        />
        <StatTile
          label="Rejected"
          value={data.rejected}
          tone={data.rejected > 0 ? "danger" : "default"}
        />
        <StatTile
          label="Avg AI score"
          value={data.average_ai_score === null ? "—" : data.average_ai_score}
          hint="Across screened applications"
          tone={
            data.average_ai_score !== null && data.average_ai_score >= 70
              ? "success"
              : data.average_ai_score !== null && data.average_ai_score >= 40
                ? "warning"
                : "default"
          }
        />
      </section>

      <Card className="p-6">
        <h2 className="font-display text-xl mb-4">Application status mix</h2>
        <div className="space-y-3">
          <BarRow label="Submitted" value={data.submitted} max={max} tone="ink" />
          <BarRow label="Screened" value={data.screened} max={max} tone="warning" />
          <BarRow label="Shortlisted" value={data.shortlisted} max={max} tone="success" />
          <BarRow label="Rejected" value={data.rejected} max={max} tone="signal" />
        </div>
      </Card>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display text-2xl">All applications</h2>
        </div>
        {list.length === 0 ? (
          <EmptyState
            title="No applications yet"
            body="Browse the marketplace and apply to a project. The AI screener will give you an instant fit score."
            cta={
              <Link
                to="/projects"
                className="px-4 py-2 rounded-[3px] bg-ink text-paper text-sm font-medium"
              >
                Browse projects
              </Link>
            }
          />
        ) : (
          <div className="border border-rule-soft rounded-[3px] overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-paper text-left text-xs uppercase tracking-widest text-ink-muted">
                <tr>
                  <th className="px-4 py-3">Project</th>
                  <th className="px-4 py-3">Submitted</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">AI score</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((app) => (
                  <tr key={app.id} className="border-t border-rule-soft">
                    <td className="px-4 py-3 font-medium">
                      <Link
                        to={`/projects/${app.project_id}`}
                        className="hover:underline"
                      >
                        View project →
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">
                      {new Date(app.submitted_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-block px-2 py-0.5 text-xs border border-rule-soft rounded-sm uppercase tracking-widest">
                        {app.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {app.ai_score ?? "—"}
                      <span className="text-ink-muted">/100</span>
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-ink-muted line-clamp-1 max-w-xs">
                      {app.ai_summary}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
