import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";
import {
  Button,
  Card,
  DecisionStamp,
  Meter,
  ProblemAlert,
  Spinner,
  StatusBadge,
} from "../components/ui";

const TERMINAL = new Set(["completed", "failed"]);

interface Dimension {
  key: string;
  label: string;
  raw_score: number;
  weight: number;
  weighted_score: number;
  explanation: string;
}
interface Readiness {
  overall_score: number;
  decision_label: string;
  dimensions: Dimension[];
  hard_blockers: { code: string; message: string }[];
  assumptions: string[];
  human_override: { label: string; reason: string } | null;
}
interface Citation {
  document_id: string;
  page_number: number;
  source_quote: string;
  verified: boolean;
  match_method: string;
}
interface Requirement {
  id: string;
  category: string;
  obligation: string;
  normalized_text: string;
  confidence: number;
  citation_verified: boolean;
  machine_status: string;
  reviewed_status: string;
  citations: Citation[];
}
interface Risk {
  id: string;
  risk_type: string;
  severity: string;
  summary: string;
  why_it_matters: string;
  suggested_action: string;
  citation_verified: boolean;
  citations: Citation[];
}
type CitationTarget = { documentId: string; page: number; quote: string };

export function TenderPage() {
  const { tenderId } = useParams<{ tenderId: string }>();
  const queryClient = useQueryClient();
  const [cite, setCite] = useState<CitationTarget | null>(null);

  const tender = useQuery({
    queryKey: ["tender", tenderId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/tenders/{tender_id}", {
        params: { path: { tender_id: tenderId! } },
      });
      if (error) throw error;
      return data;
    },
  });

  const analyses = useQuery({
    queryKey: ["analyses", tenderId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/tenders/{tender_id}/analyses", {
        params: { path: { tender_id: tenderId! } },
      });
      if (error) throw error;
      return data;
    },
    // Poll while the latest run is in progress. Real stages, never a fabricated percentage.
    refetchInterval: (q) => {
      const list = (q.state.data ?? []) as { status: string }[];
      return list.length && !TERMINAL.has(list[0].status) ? 2000 : false;
    },
  });

  const latest = (analyses.data ?? [])[0] as
    | {
        id: string;
        status: string;
        current_stage: string;
        stage_message: string | null;
        can_retry: boolean;
      }
    | undefined;

  const runAnalysis = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/tenders/{tender_id}/analyses", {
        params: { path: { tender_id: tenderId! } },
      });
      if (error) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["analyses", tenderId] }),
  });

  if (tender.isLoading) return <Spinner label="Loading tender…" />;
  if (tender.error) return <ProblemAlert message={problemMessage(tender.error)} />;

  const t = tender.data as { title: string; buyer: string | null; reference: string | null };

  return (
    <div>
      <header className="border-b-2 border-rule pb-4 mb-6">
        <h1 className="font-display text-3xl">{t.title}</h1>
        <div className="flex gap-6 mt-1 text-sm text-ink-muted">
          {t.buyer ? <span>Buyer: {t.buyer}</span> : null}
          {t.reference ? <span className="font-mono">{t.reference}</span> : null}
        </div>
      </header>

      {!latest ? (
        <Card className="p-8 text-center">
          <p className="font-display text-xl mb-2">No analysis yet</p>
          <p className="text-sm text-ink-muted mb-4">
            Run an analysis to extract cited requirements, risks, and a readiness score.
          </p>
          <Button onClick={() => runAnalysis.mutate()} disabled={runAnalysis.isPending}>
            {runAnalysis.isPending ? "Queuing…" : "Run analysis"}
          </Button>
          {runAnalysis.error ? (
            <div className="mt-3">
              <ProblemAlert message={(runAnalysis.error as Error).message} />
            </div>
          ) : null}
        </Card>
      ) : latest.status !== "completed" ? (
        <ProcessingRoom
          stage={latest.current_stage}
          message={latest.stage_message}
          status={latest.status}
          canRetry={latest.can_retry}
          analysisId={latest.id}
          onRetry={() => queryClient.invalidateQueries({ queryKey: ["analyses", tenderId] })}
        />
      ) : (
        <CompletedAnalysis analysisId={latest.id} onCite={setCite} />
      )}

      {cite ? <SourceDrawer citation={cite} onClose={() => setCite(null)} /> : null}
    </div>
  );
}

const STAGES = [
  "validating",
  "extracting_text",
  "assessing_quality",
  "extracting_metadata",
  "extracting_requirements",
  "verifying_citations",
  "matching_evidence",
  "analysing_risks",
  "scoring",
  "generating_report",
];

function ProcessingRoom({
  stage,
  message,
  status,
  canRetry,
  analysisId,
  onRetry,
}: {
  stage: string;
  message: string | null;
  status: string;
  canRetry: boolean;
  analysisId: string;
  onRetry: () => void;
}) {
  const currentIndex = STAGES.indexOf(stage);
  const retry = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/v1/analyses/{analysis_id}/retry", {
        params: { path: { analysis_id: analysisId } },
      });
      if (error) throw new Error(problemMessage(error));
    },
    onSuccess: onRetry,
  });

  return (
    <Card className="p-6 max-w-2xl">
      <h2 className="font-display text-xl mb-4">
        {status === "failed" ? "Analysis failed" : "Processing"}
      </h2>
      {status === "failed" ? (
        <>
          <ProblemAlert message={message ?? "The analysis could not be completed."} />
          {canRetry ? (
            <Button className="mt-4" onClick={() => retry.mutate()} disabled={retry.isPending}>
              {retry.isPending ? "Retrying…" : "Retry analysis"}
            </Button>
          ) : null}
        </>
      ) : (
        <ol className="space-y-1">
          {STAGES.map((s, i) => {
            const done = currentIndex > i;
            const active = currentIndex === i;
            return (
              <li
                key={s}
                className={`flex items-center gap-3 py-1.5 text-sm ${
                  active ? "text-ink font-semibold" : done ? "text-ink-muted" : "text-rule-soft"
                }`}
              >
                <span className="font-mono text-xs w-6">{String(i + 1).padStart(2, "0")}</span>
                <span className="w-4">{done ? "✓" : active ? "▸" : "·"}</span>
                <span className="capitalize">{s.replace(/_/g, " ")}</span>
                {active ? (
                  <span className="inline-block w-2 h-2 bg-signal rounded-full animate-pulse" />
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
      {status !== "failed" && message ? (
        <p className="text-xs text-ink-muted mt-4">{message}</p>
      ) : null}
    </Card>
  );
}

function CompletedAnalysis({
  analysisId,
  onCite,
}: {
  analysisId: string;
  onCite: (c: CitationTarget) => void;
}) {
  const readiness = useQuery({
    queryKey: ["readiness", analysisId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/analyses/{analysis_id}/readiness", {
        params: { path: { analysis_id: analysisId } },
      });
      if (error) throw error;
      return data as unknown as Readiness;
    },
  });
  const requirements = useQuery({
    queryKey: ["requirements", analysisId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/analyses/{analysis_id}/requirements", {
        params: { path: { analysis_id: analysisId }, query: { limit: 100 } },
      });
      if (error) throw error;
      return (data?.items ?? []) as unknown as Requirement[];
    },
  });
  const risks = useQuery({
    queryKey: ["risks", analysisId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/analyses/{analysis_id}/risks", {
        params: { path: { analysis_id: analysisId } },
      });
      if (error) throw error;
      return (data ?? []) as unknown as Risk[];
    },
  });

  const r = readiness.data;

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 lg:col-span-8 space-y-6">
        {r ? (
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-ink-muted">Bid readiness</div>
                <div className="font-display text-5xl">
                  {Number(r.overall_score).toFixed(0)}
                  <span className="text-2xl text-ink-muted">/100</span>
                </div>
              </div>
              <DecisionStamp label={r.human_override?.label ?? r.decision_label} />
            </div>
            <Meter value={Number(r.overall_score)} />
            {r.hard_blockers.length ? (
              <div className="mt-4 space-y-2">
                {r.hard_blockers.map((b) => (
                  <div
                    key={b.code}
                    className="border-l-2 border-signal bg-signal-soft px-3 py-2 text-sm text-signal"
                  >
                    <strong>Hard blocker:</strong> {b.message}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-5 space-y-2">
              {r.dimensions.map((d) => (
                <div
                  key={d.key}
                  className="grid grid-cols-[1fr_auto] gap-2 items-center border-b border-rule-soft pb-2"
                >
                  <div>
                    <div className="text-sm font-medium">{d.label}</div>
                    <div className="text-xs text-ink-muted">{d.explanation}</div>
                  </div>
                  <div className="text-right font-mono text-sm">
                    {d.raw_score.toFixed(0)}
                    <span className="text-ink-muted text-xs"> ×{d.weight}%</span>
                  </div>
                </div>
              ))}
            </div>
            <ReadinessOverride analysisId={analysisId} current={r} />
          </Card>
        ) : (
          <Spinner label="Loading readiness…" />
        )}

        <Card>
          <h2 className="font-display text-xl px-4 py-3 border-b border-rule">Compliance Matrix</h2>
          {requirements.isLoading ? (
            <div className="p-4">
              <Spinner label="Loading requirements…" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-muted">
                    <th className="px-3 py-2 font-semibold">Requirement</th>
                    <th className="px-3 py-2 font-semibold">Category</th>
                    <th className="px-3 py-2 font-semibold">Status</th>
                    <th className="px-3 py-2 font-semibold">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {(requirements.data ?? []).map((req) => (
                    <tr key={req.id} className="border-b border-rule-soft align-top">
                      <td className="px-3 py-2 max-w-md">
                        {req.normalized_text}
                        {req.obligation === "mandatory" ? (
                          <span className="ml-2 text-xs text-signal font-semibold">MANDATORY</span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 text-xs text-ink-muted capitalize">
                        {req.category.replace(/_/g, " ")}
                      </td>
                      <td className="px-3 py-2">
                        <StatusBadge
                          status={
                            req.reviewed_status !== "unreviewed"
                              ? req.reviewed_status
                              : req.machine_status
                          }
                        />
                      </td>
                      <td className="px-3 py-2">
                        {req.citations[0] ? (
                          <button
                            className="text-signal underline text-xs"
                            onClick={() =>
                              onCite({
                                documentId: req.citations[0].document_id,
                                page: req.citations[0].page_number,
                                quote: req.citations[0].source_quote,
                              })
                            }
                          >
                            p.{req.citations[0].page_number} {req.citations[0].verified ? "✓" : "⚠"}
                          </button>
                        ) : (
                          <span className="text-xs text-ink-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card>
          <h2 className="font-display text-xl px-4 py-3 border-b border-rule">Risk Register</h2>
          <div className="divide-y divide-rule-soft">
            {(risks.data ?? []).length === 0 ? (
              <p className="p-4 text-sm text-ink-muted">No material risks identified.</p>
            ) : (
              (risks.data ?? []).map((risk) => (
                <div key={risk.id} className="p-4">
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-xs font-bold uppercase px-2 py-0.5 rounded-[2px] ${
                        risk.severity === "critical" || risk.severity === "high"
                          ? "bg-signal text-white"
                          : "bg-warning/15 text-warning"
                      }`}
                    >
                      {risk.severity}
                    </span>
                    <span className="text-sm font-medium capitalize">
                      {risk.risk_type.replace(/_/g, " ")}
                    </span>
                    {risk.citations[0] ? (
                      <button
                        className="text-signal underline text-xs ml-auto"
                        onClick={() =>
                          onCite({
                            documentId: risk.citations[0].document_id,
                            page: risk.citations[0].page_number,
                            quote: risk.citations[0].source_quote,
                          })
                        }
                      >
                        p.{risk.citations[0].page_number} {risk.citations[0].verified ? "✓" : "⚠"}
                      </button>
                    ) : null}
                  </div>
                  <p className="text-sm mt-2">{risk.summary}</p>
                  <p className="text-xs text-ink-muted mt-1">{risk.why_it_matters}</p>
                  <p className="text-xs mt-1">
                    <strong>Suggested:</strong> {risk.suggested_action}
                  </p>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <div className="col-span-12 lg:col-span-4 space-y-6">
        <Card className="p-4">
          <h3 className="font-display text-lg mb-2">Assumptions</h3>
          <ul className="text-xs text-ink-muted space-y-1 list-disc pl-4">
            {(r?.assumptions ?? []).map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Card>
        <Card className="p-4 text-xs text-ink-muted">
          <p>
            &ldquo;Not found&rdquo; means the application did not find evidence &mdash; it does not
            prove absence. The readiness score is calculated by deterministic Python rules, not by a
            model.
          </p>
        </Card>
      </div>
    </div>
  );
}

function ReadinessOverride({ analysisId, current }: { analysisId: string; current: Readiness }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(current.decision_label);
  const [reason, setReason] = useState("");
  const override = useMutation({
    mutationFn: async () => {
      const { error } = await api.PATCH("/api/v1/analyses/{analysis_id}/readiness/override", {
        params: { path: { analysis_id: analysisId } },
        body: { decision_label: label as never, reason },
      });
      if (error) throw new Error(problemMessage(error));
    },
    onSuccess: () => {
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["readiness", analysisId] });
    },
  });

  if (!open) {
    return (
      <button className="mt-4 text-xs text-signal underline" onClick={() => setOpen(true)}>
        Override decision…
      </button>
    );
  }
  return (
    <div className="mt-4 border-t border-rule-soft pt-4 space-y-2">
      <select
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        className="border border-rule-soft px-2 py-1 text-sm rounded-[3px]"
      >
        {["strong_bid", "conditional_bid", "weak_bid", "do_not_bid", "insufficient_information"].map(
          (l) => (
            <option key={l} value={l}>
              {l.replace(/_/g, " ")}
            </option>
          ),
        )}
      </select>
      <textarea
        placeholder="Reason (required)…"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="w-full border border-rule-soft px-2 py-1 text-sm rounded-[3px]"
        rows={2}
      />
      {override.error ? <ProblemAlert message={(override.error as Error).message} /> : null}
      <div className="flex gap-2">
        <Button onClick={() => override.mutate()} disabled={override.isPending || reason.length < 3}>
          Save override
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function SourceDrawer({ citation, onClose }: { citation: CitationTarget; onClose: () => void }) {
  const page = useQuery({
    queryKey: ["page", citation.documentId, citation.page],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/documents/{document_id}/pages/{page_number}",
        { params: { path: { document_id: citation.documentId, page_number: citation.page } } },
      );
      if (error) throw error;
      return data as { text: string; page_number: number };
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-ink/30" />
      <aside
        className="relative bg-surface w-full max-w-xl h-full overflow-auto border-l-2 border-rule p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-rule pb-3 mb-4">
          <h3 className="font-display text-xl">Source &mdash; page {citation.page}</h3>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="mb-4 border-l-2 border-signal bg-signal-soft px-3 py-2 text-sm">
          <div className="text-xs uppercase tracking-wide text-ink-muted mb-1">Cited quote</div>
          {citation.quote}
        </div>
        {page.isLoading ? (
          <Spinner label="Loading page…" />
        ) : page.error ? (
          <ProblemAlert message={problemMessage(page.error)} />
        ) : (
          <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-ink">
            {highlight(page.data?.text ?? "", citation.quote)}
          </pre>
        )}
      </aside>
    </div>
  );
}

function highlight(text: string, quote: string) {
  const idx = text.toLowerCase().indexOf(quote.toLowerCase().slice(0, 40));
  if (idx < 0) return text;
  const end = idx + quote.length;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-signal/20">{text.slice(idx, end)}</mark>
      {text.slice(end)}
    </>
  );
}
