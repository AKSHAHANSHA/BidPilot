import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";
import { Button, Card, Meter, Spinner, StatusBadge } from "../components/ui";
import { ConfirmDialog } from "../components/Modal";
import { EvidenceForm, type EvidenceValues } from "../components/EvidenceForm";
import { ProjectForm, type ProjectValues } from "../components/ProjectForm";
import { ProfileForm, type ProfileValues } from "../components/ProfileForm";

interface Profile {
  legal_name: string;
  trading_name: string | null;
  description: string;
  industry: string;
  emirate: string;
  country: string;
  year_established: number;
  employee_count: number;
  years_of_experience: number;
  trade_licence_number: string;
  trade_licence_expiry: string;
  licence_activities: string[];
  website: string | null;
  contact_email: string;
  contact_phone: string | null;
  annual_revenue_range: string | null;
  preferred_contract_value_min: string | null;
  preferred_contract_value_max: string | null;
  service_categories: string[];
  geographic_coverage: string[];
  profile_completion_percentage: number;
  completion: { missing: { key: string; label: string; hint: string }[] };
}
interface Evidence {
  id: string;
  title: string;
  category: string;
  issuing_organisation: string | null;
  reference_number: string | null;
  description: string;
  issue_date: string | null;
  expiry_date: string | null;
  verification_status: string;
  tags: string[];
  expiry: { state: string; days_until_expiry: number | null };
}
interface Project {
  id: string;
  client_name: string;
  project_title: string;
  industry: string;
  description: string;
  contract_value: string | null;
  currency: string;
  start_date: string;
  end_date: string | null;
  status: string;
  location: string;
  services_delivered: string[];
  outcome: string | null;
  client_reference_available: boolean;
  is_confidential: boolean;
  duration_months: number | null;
}

export function CompanyProfilePage() {
  const queryClient = useQueryClient();
  const [editProfile, setEditProfile] = useState(false);
  const [evidenceForm, setEvidenceForm] = useState<Partial<EvidenceValues> | null>(null);
  const [projectForm, setProjectForm] = useState<Partial<ProjectValues> | null>(null);
  const [deleteEvidence, setDeleteEvidence] = useState<Evidence | null>(null);
  const [deleteProject, setDeleteProject] = useState<Project | null>(null);

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
  const projects = useQuery({
    queryKey: ["projects"],
    enabled: !!profile.data,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/company/projects", {
        params: { query: { limit: 100 } },
      });
      if (error) throw error;
      return (data?.items ?? []) as unknown as Project[];
    },
  });

  const removeEvidence = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/v1/company/evidence/{evidence_id}", {
        params: { path: { evidence_id: id } },
      });
      if (error) throw new Error(problemMessage(error));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence"] });
      setDeleteEvidence(null);
    },
  });
  const removeProject = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/v1/company/projects/{project_id}", {
        params: { path: { project_id: id } },
      });
      if (error) throw new Error(problemMessage(error));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setDeleteProject(null);
    },
  });

  if (profile.isLoading) return <Spinner label="Loading profile…" />;

  if (!profile.data) {
    return (
      <>
        <Card className="p-10 text-center max-w-lg">
          <p className="font-display text-xl mb-2">No company profile yet</p>
          <p className="text-sm text-ink-muted mb-4">
            A company profile is the knowledge base your tenders are scored against. Create one to
            get started, or seed the demo company with{" "}
            <code className="font-mono text-xs">python scripts/seed_demo.py</code>.
          </p>
          <Button onClick={() => setEditProfile(true)}>Create company profile</Button>
        </Card>
        {editProfile ? (
          <ProfileForm initial={{}} mode="create" onClose={() => setEditProfile(false)} />
        ) : null}
      </>
    );
  }

  const p = profile.data;

  return (
    <div>
      <header className="border-b-2 border-rule pb-3 mb-6 flex items-start justify-between">
        <div>
          <h1 className="font-display text-3xl">{p.legal_name}</h1>
          <p className="text-sm text-ink-muted">
            {p.industry} · {p.emirate.replace(/_/g, " ")} · {p.employee_count} staff ·{" "}
            {p.years_of_experience} yrs
          </p>
        </div>
        <Button variant="ghost" onClick={() => setEditProfile(true)}>
          Edit profile
        </Button>
      </header>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-4 space-y-6">
          <Card className="p-5">
            <div className="text-xs uppercase tracking-wide text-ink-muted">Profile completion</div>
            <div className="font-display text-4xl mb-2">{p.profile_completion_percentage}%</div>
            <Meter value={p.profile_completion_percentage} />
            {p.completion.missing.length ? (
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase text-ink-muted mb-1">To improve</div>
                <ul className="text-xs text-ink-muted space-y-1 list-disc pl-4">
                  {p.completion.missing.slice(0, 5).map((m) => (
                    <li key={m.key}>{m.label}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-success mt-3">Profile complete.</p>
            )}
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

        <div className="col-span-12 lg:col-span-8 space-y-6">
          <Card>
            <div className="flex items-center justify-between px-4 py-3 border-b border-rule">
              <h2 className="font-display text-xl">Evidence</h2>
              <Button onClick={() => setEvidenceForm({})}>+ Add evidence</Button>
            </div>
            {evidence.isLoading ? (
              <div className="p-4"><Spinner label="Loading evidence…" /></div>
            ) : (evidence.data ?? []).length === 0 ? (
              <p className="p-4 text-sm text-ink-muted">
                No evidence yet. Add certifications, insurance, and licences your bids rely on.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-muted">
                      <th className="px-3 py-2 font-semibold">Title</th>
                      <th className="px-3 py-2 font-semibold">Category</th>
                      <th className="px-3 py-2 font-semibold">Verification</th>
                      <th className="px-3 py-2 font-semibold">Expiry</th>
                      <th className="px-3 py-2 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(evidence.data ?? []).map((e) => (
                      <tr key={e.id} className="border-b border-rule-soft">
                        <td className="px-3 py-2">{e.title}</td>
                        <td className="px-3 py-2 text-xs text-ink-muted capitalize">
                          {e.category.replace(/_/g, " ")}
                        </td>
                        <td className="px-3 py-2"><StatusBadge status={e.verification_status} /></td>
                        <td className="px-3 py-2 text-xs">
                          <ExpiryTag state={e.expiry.state} days={e.expiry.days_until_expiry} />
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          <button
                            className="text-signal underline text-xs mr-3"
                            onClick={() =>
                              setEvidenceForm({
                                id: e.id,
                                title: e.title,
                                category: e.category,
                                issuing_organisation: e.issuing_organisation ?? "",
                                reference_number: e.reference_number ?? "",
                                description: e.description,
                                issue_date: e.issue_date ?? "",
                                expiry_date: e.expiry_date ?? "",
                                verification_status: e.verification_status,
                                tags: e.tags.join(", "),
                              })
                            }
                          >
                            Edit
                          </button>
                          <button
                            className="text-ink-muted underline text-xs hover:text-signal"
                            onClick={() => setDeleteEvidence(e)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between px-4 py-3 border-b border-rule">
              <h2 className="font-display text-xl">Projects</h2>
              <Button onClick={() => setProjectForm({})}>+ Add project</Button>
            </div>
            {projects.isLoading ? (
              <div className="p-4"><Spinner label="Loading projects…" /></div>
            ) : (projects.data ?? []).length === 0 ? (
              <p className="p-4 text-sm text-ink-muted">
                No projects yet. Add completed work to demonstrate experience.
              </p>
            ) : (
              <div className="divide-y divide-rule-soft">
                {(projects.data ?? []).map((pr) => (
                  <div key={pr.id} className="p-4 flex items-start justify-between gap-4">
                    <div>
                      <div className="font-medium">{pr.project_title}</div>
                      <div className="text-xs text-ink-muted">
                        {pr.client_name} · {pr.location} · {pr.status}
                        {pr.duration_months !== null ? ` · ${pr.duration_months} mo` : ""}
                        {pr.contract_value ? ` · ${pr.currency} ${pr.contract_value}` : ""}
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {pr.services_delivered.map((s) => (
                          <span key={s} className="text-xs border border-rule-soft rounded-[2px] px-1.5">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="whitespace-nowrap">
                      <button
                        className="text-signal underline text-xs mr-3"
                        onClick={() =>
                          setProjectForm({
                            id: pr.id,
                            client_name: pr.client_name,
                            project_title: pr.project_title,
                            industry: pr.industry,
                            description: pr.description,
                            contract_value: pr.contract_value ?? "",
                            currency: pr.currency,
                            start_date: pr.start_date,
                            end_date: pr.end_date ?? "",
                            status: pr.status,
                            location: pr.location,
                            services_delivered: pr.services_delivered.join(", "),
                            outcome: pr.outcome ?? "",
                            client_reference_available: pr.client_reference_available,
                            is_confidential: pr.is_confidential,
                          })
                        }
                      >
                        Edit
                      </button>
                      <button
                        className="text-ink-muted underline text-xs hover:text-signal"
                        onClick={() => setDeleteProject(pr)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <p className="text-xs text-ink-muted">
            Only evidence you have marked verified is used when scoring a tender.
          </p>
        </div>
      </div>

      {editProfile ? (
        <ProfileForm
          mode="edit"
          initial={{
            legal_name: p.legal_name,
            trading_name: p.trading_name ?? "",
            description: p.description,
            industry: p.industry,
            emirate: p.emirate,
            country: p.country,
            year_established: String(p.year_established),
            employee_count: String(p.employee_count),
            years_of_experience: String(p.years_of_experience),
            trade_licence_number: p.trade_licence_number,
            trade_licence_expiry: p.trade_licence_expiry,
            licence_activities: p.licence_activities.join(", "),
            website: p.website ?? "",
            contact_email: p.contact_email,
            contact_phone: p.contact_phone ?? "",
            annual_revenue_range: p.annual_revenue_range ?? "",
            preferred_contract_value_min: p.preferred_contract_value_min ?? "",
            preferred_contract_value_max: p.preferred_contract_value_max ?? "",
            service_categories: p.service_categories.join(", "),
            geographic_coverage: p.geographic_coverage.join(", "),
          } satisfies ProfileValues}
          onClose={() => setEditProfile(false)}
        />
      ) : null}
      {evidenceForm ? (
        <EvidenceForm initial={evidenceForm} onClose={() => setEvidenceForm(null)} />
      ) : null}
      {projectForm ? (
        <ProjectForm initial={projectForm} onClose={() => setProjectForm(null)} />
      ) : null}
      {deleteEvidence ? (
        <ConfirmDialog
          title="Delete evidence"
          message={`Delete "${deleteEvidence.title}"? This cannot be undone.`}
          busy={removeEvidence.isPending}
          onConfirm={() => removeEvidence.mutate(deleteEvidence.id)}
          onClose={() => setDeleteEvidence(null)}
        />
      ) : null}
      {deleteProject ? (
        <ConfirmDialog
          title="Delete project"
          message={`Delete "${deleteProject.project_title}"? This cannot be undone.`}
          busy={removeProject.isPending}
          onConfirm={() => removeProject.mutate(deleteProject.id)}
          onClose={() => setDeleteProject(null)}
        />
      ) : null}
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
