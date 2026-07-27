import { Card } from "../components/ui";

export function EngineeringNotesPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-3xl border-b-2 border-rule pb-3 mb-6">Engineering Notes</h1>
      <div className="space-y-4">
        <Card className="p-5">
          <h2 className="font-display text-xl mb-2">How the analysis works</h2>
          <p className="text-sm text-ink-muted">
            A tender PDF is validated by content, extracted page-by-page, then processed by a
            background worker through explicit stages: metadata and requirement extraction with
            strict schemas, citation verification against the source pages, deterministic evidence
            matching, cited risk extraction, and a readiness score.
          </p>
        </Card>
        <Card className="p-5">
          <h2 className="font-display text-xl mb-2">Why you can trust the score</h2>
          <ul className="text-sm text-ink-muted space-y-1 list-disc pl-4">
            <li>The model extracts and explains; Python calculates the score with explicit weights.</li>
            <li>No material finding is canonical without a verified source citation.</li>
            <li>&ldquo;Not found&rdquo; means not found &mdash; never proof of absence.</li>
            <li>Human overrides require a reason and preserve the original machine result.</li>
            <li>Uploaded documents are treated as untrusted evidence, never as instructions.</li>
          </ul>
        </Card>
        <Card className="p-5">
          <h2 className="font-display text-xl mb-2">Stack</h2>
          <p className="text-sm text-ink-muted font-mono">
            FastAPI · PostgreSQL · Redis · Dramatiq · PyMuPDF · OpenAI (structured outputs) ·
            React 19 · TypeScript · Vite · Tailwind v4
          </p>
        </Card>
      </div>
    </div>
  );
}
