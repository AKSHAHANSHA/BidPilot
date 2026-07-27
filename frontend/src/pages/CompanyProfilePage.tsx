import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card, Meter, Spinner, StatusBadge } from "../components/ui";

interface Profile {
  legal_name: string;
  industry: string;
  emirate: string;
  employee_count: number;
  years_of_experience: number;
  service_categories: string[];
  geographic_coverage: string[];
  profile_completion_percentage: number;
  completion: { missing: { label: string; hint: string }[] };
}
interface Evidence {
  id: string;
  title: string;
  category: string;
  verification_status: string;
  expiry: { state: string; days_until_expiry: number | null };
}

export function CompanyProfilePage() {
  const profile = useQuery({
    queryKey: ["company"],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/api/v1/company");
      if (response.status === 404) return null;
      if (error) throw error;
      return data as unknown as Profile;
    },
  });
  const evidence = useQuery({
    queryKey: ["evidence"],
    enabled: !!profile.data,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/company/evidence", {
        params: { query: { limit: 100 } },
      });
      if (error) throw error;
      return (data?.items ?? []) as unknown as Evidence[];
    },
  });

  if (profile.isLoading) return <Spinner label="Loading profile…" />;

  if (!profile.data) {
    return (
      <Card className="p-10 text-center max-w-lg">
        <p className="font-display text-xl mb-2">No company profile yet</p>
        <p className="text-sm text-ink-muted">
          A company profile is the knowledge base your tenders are scored against. Seed one with{" "}
          <code className="font-mono text-xs">python scripts/seed_demo.py</code> or create it via the
          API. A profile form is part of the roadmap&rsquo;s remaining UI work.
        </p>
      </Card>
    );
  }

  const p = profile.data;

  return (
    <div>
      <header className="border-b-2 border-rule pb-3 mb-6">
        <h1 className="font-display text-3xl">{p.legal_name}</h1>
        <p className="text-sm text-ink-muted">
          {p.industry} · {p.emirate.replace(/_/g, " ")} · {p.employee_count} staff ·{" "}
          {p.years_of_experience} yrs
        </p>
      </header>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-4 space-y-6">
          <Card className="p-5">
            <div className="text-xs uppercase tracking-wide text-ink-muted">Profile completion</div>
            <div className="font-display text-4xl mb-2">{p.profile_completion_percentage}%</div>
            <Meter value={p.profile_completion_percentage} />
            {p.completion.missing.length ? (
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase text-ink-muted mb-1">
                  To improve
                </div>
                <ul className="text-xs text-ink-muted space-y-1 list-disc pl-4">
                  {p.completion.missing.slice(0, 5).map((m) => (
                    <li key={m.label}>{m.label}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>
          <Card className="p-5">
            <div className="text-xs uppercase tracking-wide text-ink-muted mb-2">Services</div>
            <div className="flex flex-wrap gap-1">
              {p.service_categories.map((s) => (
                <span key={s} className="text-xs border border-rule-soft rounded-[2px] px-2 py-0.5">
                  {s}
                </span>
              ))}
            </div>
            <div className="text-xs uppercase tracking-wide text-ink-muted mb-2 mt-4">Coverage</div>
            <div className="flex flex-wrap gap-1">
              {p.geographic_coverage.map((g) => (
                <span key={g} className="text-xs border border-rule-soft rounded-[2px] px-2 py-0.5">
                  {g}
                </span>
              ))}
            </div>
          </Card>
        </div>

        <div className="col-span-12 lg:col-span-8">
          <Card>
            <h2 className="font-display text-xl px-4 py-3 border-b border-rule">Evidence</h2>
            {evidence.isLoading ? (
              <div className="p-4">
                <Spinner label="Loading evidence…" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-muted">
                      <th className="px-3 py-2 font-semibold">Title</th>
                      <th className="px-3 py-2 font-semibold">Category</th>
                      <th className="px-3 py-2 font-semibold">Verification</th>
                      <th className="px-3 py-2 font-semibold">Expiry</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(evidence.data ?? []).map((e) => (
                      <tr key={e.id} className="border-b border-rule-soft">
                        <td className="px-3 py-2">{e.title}</td>
                        <td className="px-3 py-2 text-xs text-ink-muted capitalize">
                          {e.category.replace(/_/g, " ")}
                        </td>
                        <td className="px-3 py-2">
                          <StatusBadge status={e.verification_status} />
                        </td>
                        <td className="px-3 py-2 text-xs">
                          <ExpiryTag state={e.expiry.state} days={e.expiry.days_until_expiry} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <p className="text-xs text-ink-muted mt-3">
            Only evidence you have marked verified is used when scoring a tender.{" "}
            <Link to="/" className="text-signal underline">
              Back to tenders
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

function ExpiryTag({ state, days }: { state: string; days: number | null }) {
  const tone: Record<string, string> = {
    active: "text-success",
    expiring_soon: "text-warning",
    expired: "text-signal",
    no_expiry: "text-ink-muted",
    unverified: "text-ink-muted",
  };
  return (
    <span className={tone[state] ?? "text-ink-muted"}>
      {state.replace(/_/g, " ")}
      {days !== null && state === "expiring_soon" ? ` (${days}d)` : ""}
    </span>
  );
}
