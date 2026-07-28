import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, authedFetch, problemMessage } from "../api/client";
import { Button, Card, Field, ProblemAlert } from "../components/ui";

export function NewTenderPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [buyer, setBuyer] = useState("");
  const [reference, setReference] = useState("");
  const [deadline, setDeadline] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const deadlineIso = deadline ? new Date(deadline).toISOString() : null;
      const { data, error } = await api.POST("/api/v1/tenders", {
        body: {
          title,
          buyer: buyer || null,
          reference: reference || null,
          submission_deadline: deadlineIso,
        },
      });
      if (error || !data) throw new Error(problemMessage(error));
      const tenderId = (data as { id: string }).id;

      if (file) {
        const form = new FormData();
        form.append("file", file);
        const res = await authedFetch(`/api/v1/tenders/${tenderId}/documents`, {
          method: "POST",
          body: form,
        });
        if (!res.ok) {
          const problem = await res.json().catch(() => ({}));
          throw new Error(problemMessage(problem));
        }
      }
      navigate(`/self-check/${tenderId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the tender.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="font-display text-3xl mb-1 border-b-2 border-rule pb-3">New Tender</h1>
      <p className="text-sm text-ink-muted my-4">
        Create the tender and attach its PDF. Analysis runs in the background; you will see real
        processing stages. AI output is advisory.
      </p>
      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          {error ? <ProblemAlert message={error} /> : null}
          <Field label="Tender title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Buyer (optional)" value={buyer} onChange={(e) => setBuyer(e.target.value)} />
            <Field
              label="Reference (optional)"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>
          <Field
            label="Submission deadline (optional)"
            type="datetime-local"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wide text-ink-muted mb-1">
              Tender PDF
            </span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm border border-dashed border-rule-soft rounded-[3px] p-4 bg-paper"
            />
            <span className="block text-xs text-ink-muted mt-1">
              PDF only. The file is validated by its content, not just its name.
            </span>
          </label>
          <Button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create tender"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
