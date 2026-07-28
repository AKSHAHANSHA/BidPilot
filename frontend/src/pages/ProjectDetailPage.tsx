import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  fetchPublicProject,
  submitApplication,
  formatBudget,
  deadlineLabel,
  type ProjectDetailDto,
  type ApplicationDetailDto,
} from "../lib/marketplace";
import { useAuth } from "../lib/auth";
import { PublicFooter, PublicHeader } from "./LandingPage";

/**
 * Public project detail. If the visitor is signed in as a vendor, they can apply from here;
 * anyone else sees a "sign in to apply" CTA.
 */
export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetailDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ApplicationDetailDto | null>(null);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await fetchPublicProject(projectId);
        if (!cancelled) setProject(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load project");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function apply(event: FormEvent) {
    event.preventDefault();
    if (!project) return;
    setSubmitting(true);
    setError(null);
    try {
      const application = await submitApplication(project.id, coverLetter);
      setResult(application);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit your application");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-[#08090f] text-white min-h-screen">
        <PublicHeader />
        <div className="max-w-4xl mx-auto p-10 text-white/60">Loading project…</div>
      </div>
    );
  }
  if (!project) {
    return (
      <div className="bg-[#08090f] text-white min-h-screen">
        <PublicHeader />
        <div className="max-w-4xl mx-auto p-10">
          <p className="text-white/70">{error ?? "Project not found."}</p>
          <Link to="/projects" className="mt-4 inline-block underline">
            ← Back to projects
          </Link>
        </div>
      </div>
    );
  }

  const canApply = user?.account_type === "vendor";

  return (
    <div className="bg-[#08090f] text-white min-h-screen flex flex-col">
      <PublicHeader />
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-10 grid gap-8 lg:grid-cols-[1fr_320px]">
        {/* --- Left: project detail ---------------------------------------- */}
        <article className="space-y-6">
          <Link to="/projects" className="text-xs text-white/50 hover:text-white">
            ← All projects
          </Link>
          <div
            className="aspect-[16/6] w-full rounded-xl overflow-hidden relative"
            style={{
              background: project.cover_image_url
                ? `center / cover no-repeat url("${project.cover_image_url}"), linear-gradient(135deg, #232433, #0a0b12)`
                : "linear-gradient(135deg, #232433, #0a0b12)",
            }}
          >
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
            <div className="absolute bottom-4 left-6">
              <div className="text-xs uppercase tracking-widest text-white/70">
                {project.company_display_name}
              </div>
              <h1 className="font-display text-3xl sm:text-4xl leading-tight">
                {project.title}
              </h1>
            </div>
          </div>

          <div className="flex flex-wrap gap-3 text-sm">
            <Badge>{project.category.replaceAll("_", " ")}</Badge>
            <Badge>{project.location ?? "UAE"}</Badge>
            <Badge tone="signal">{formatBudget(project.budget_aed)}</Badge>
            <Badge tone="warning">{deadlineLabel(project.submission_deadline)}</Badge>
          </div>

          <section>
            <h2 className="font-display text-2xl mb-3">Scope</h2>
            <p className="text-white/80 whitespace-pre-line leading-relaxed">
              {project.description}
            </p>
          </section>

          {project.requirements_summary ? (
            <section>
              <h2 className="font-display text-2xl mb-3">Requirements</h2>
              <pre className="text-white/80 whitespace-pre-wrap font-sans leading-relaxed">
                {project.requirements_summary}
              </pre>
            </section>
          ) : null}
        </article>

        {/* --- Right: apply / sign-in CTA --------------------------------- */}
        <aside className="lg:sticky lg:top-24 lg:self-start rounded-xl border border-white/10 bg-white/[0.03] p-5 space-y-4">
          <div className="text-xs uppercase tracking-widest text-white/40">Apply</div>
          {result ? (
            <ApplicationResult application={result} />
          ) : !user ? (
            <div>
              <p className="text-sm text-white/70">
                Sign in as a vendor to apply. The AI screener will score your submission
                instantly.
              </p>
              <div className="mt-4 flex flex-col gap-2">
                <Link
                  to="/auth?mode=register&role=vendor"
                  className="block text-center px-4 py-2 rounded-lg bg-white text-black font-semibold hover:bg-white/90"
                >
                  Create vendor account
                </Link>
                <Link
                  to="/auth?mode=login"
                  className="block text-center px-4 py-2 rounded-lg border border-white/30 hover:border-white/60"
                >
                  Sign in
                </Link>
              </div>
            </div>
          ) : !canApply ? (
            <div>
              <p className="text-sm text-white/70">
                Your account is registered as a company; only vendor accounts can apply.
              </p>
              <button
                onClick={() => navigate("/company")}
                className="mt-3 text-sm underline"
              >
                Go to your dashboard →
              </button>
            </div>
          ) : (
            <form onSubmit={apply} className="space-y-3">
              <label className="block">
                <span className="block text-xs text-white/60 mb-1">Cover letter</span>
                <textarea
                  value={coverLetter}
                  onChange={(e) => setCoverLetter(e.target.value)}
                  rows={6}
                  placeholder="Describe your capabilities, past work, and relevant certifications."
                  className="w-full rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-3 py-2 text-sm"
                />
              </label>
              {error ? (
                <div className="text-xs text-red-300 border border-red-400/40 bg-red-500/10 px-2 py-1 rounded">
                  {error}
                </div>
              ) : null}
              <button
                type="submit"
                disabled={submitting}
                className="w-full px-4 py-2 rounded-lg bg-white text-black font-semibold hover:bg-white/90 disabled:opacity-50"
              >
                {submitting ? "Screening…" : "Submit application"}
              </button>
              <p className="text-[11px] text-white/40">
                Your submission is scored deterministically. Missing certifications or category
                mismatches lower the score.
              </p>
            </form>
          )}
        </aside>
      </main>
      <PublicFooter />
    </div>
  );
}

function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "signal" | "warning";
}) {
  const cls = {
    default: "bg-white/10 text-white/80 border-white/15",
    signal: "bg-fuchsia-500/20 text-fuchsia-100 border-fuchsia-400/40",
    warning: "bg-amber-500/20 text-amber-100 border-amber-400/40",
  }[tone];
  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full border text-xs uppercase tracking-widest ${cls}`}
    >
      {children}
    </span>
  );
}

function ApplicationResult({ application }: { application: ApplicationDetailDto }) {
  const score = application.ai_score ?? 0;
  const tone =
    score >= 80 ? "text-emerald-300" : score >= 60 ? "text-amber-300" : "text-red-300";
  return (
    <div className="space-y-3">
      <div className="text-xs uppercase tracking-widest text-white/40">AI screening</div>
      <div className={`font-display text-5xl ${tone}`}>{score}<span className="text-lg text-white/50">/100</span></div>
      <div className="text-sm text-white/80 leading-relaxed">{application.ai_summary}</div>
      {application.ai_assessment?.reasons ? (
        <ul className="space-y-1 text-xs text-white/70 list-disc pl-4">
          {application.ai_assessment.reasons.slice(0, 6).map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      ) : null}
      <div className="text-[11px] text-white/40 pt-2 border-t border-white/10">
        Deterministic scoring, algorithm version{" "}
        {(application.ai_assessment as { algorithm_version?: string })?.algorithm_version ?? "1.0.0"}.
        Your application status is now:{" "}
        <span className="text-white uppercase">{application.status.replace(/_/g, " ")}</span>.
      </div>
    </div>
  );
}
