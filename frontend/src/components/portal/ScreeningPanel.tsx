import { GlassCard, Pill, PortalSpinner } from "./kit";
import { humanise } from "../../lib/format";

/**
 * The screening result.
 *
 * Three rules drive every wording choice here, all from `CLAUDE.md`:
 *
 * 1. A missing document is reported as "we did not find it in what you uploaded", never as
 *    "you do not have it". Absence in a submission is not proof of non-existence.
 * 2. Nothing is shown as a finding without the evidence behind it. A matched requirement
 *    always names the page and quotes the text it was matched on, so a reader can check the
 *    machine rather than take its word.
 * 3. A verdict describes what *we* could establish, not what the vendor possesses. That is why
 *    `present_unverified` has its own group rather than sharing one with `missing`: the file
 *    arrived and was read, and only the credential it asserts is unconfirmed. Folding the two
 *    together would tell a vendor to upload a document they have already uploaded.
 */

export interface ScreeningFinding {
  document_type: string;
  label?: string | null;
  verdict: string;
  is_mandatory: boolean;
  weight?: number;
  source_page?: number | null;
  evidence_quote?: string | null;
  note?: string | null;
  confidence?: string | number | null;
}

export interface ScreeningResult {
  status: string;
  overall_score?: number | null;
  mandatory_met: number;
  mandatory_total: number;
  optional_met: number;
  optional_total: number;
  has_blocking_gap?: boolean;
  pages_needing_ocr?: number;
  summary?: string | null;
  scoring_version?: string;
  completed_at?: string | null;
  error_code?: string | null;
  findings: ScreeningFinding[];
}

const VERDICT_META: Record<
  string,
  { label: string; tone: "positive" | "warning" | "danger" | "neutral"; blurb: string }
> = {
  present: { label: "Supplied", tone: "positive", blurb: "Found in your documents." },
  present_expired: {
    label: "Expired",
    tone: "warning",
    blurb: "Supplied, but the document appears to have lapsed. Upload a current copy.",
  },
  present_unreadable: {
    label: "Unreadable",
    tone: "warning",
    blurb: "A file was supplied but no text could be read from it. Re-upload a clearer scan.",
  },
  present_unverified: {
    label: "Not verified",
    tone: "warning",
    blurb:
      "Supplied and read. The credential it asserts could not be confirmed against the register.",
  },
  missing: {
    label: "Not found",
    tone: "danger",
    blurb: "Not found in the documents you uploaded.",
  },
  not_applicable: {
    label: "Not applicable",
    tone: "neutral",
    blurb: "Not required for this tender.",
  },
};

/**
 * The blocking-gap banner names the actual problem.
 *
 * `has_blocking_gap` is a single boolean, but the thing behind it is not: an unmet mandatory
 * requirement can be a document nobody sent or a certificate that could not be confirmed. One
 * fixed sentence would send a vendor to re-upload a file that is already sitting on the
 * application, which is the exact mistake the separate verdict exists to prevent.
 */
function describeBlockingGap(
  missing: ScreeningFinding[],
  unverified: ScreeningFinding[],
): { title: string; body: string } {
  const anyMissing = missing.some((f) => f.is_mandatory);
  const anyUnverified = unverified.some((f) => f.is_mandatory);

  if (anyUnverified && !anyMissing) {
    return {
      title: "A mandatory credential could not be verified",
      body:
        "The file is there; the confirmation is not. Until the number on it can be matched in " +
        "the register it earns no credit, so it counts against you exactly as an absent " +
        "document would. Check the number against the certificate, or raise a clarification " +
        "with the buyer.",
    };
  }

  if (anyUnverified) {
    return {
      title: "Mandatory requirements are not met",
      body:
        "Some were not found in your upload and at least one was supplied but could not be " +
        "confirmed against the register. The two need different fixes — each group below says " +
        "which is which.",
    };
  }

  return {
    title: anyMissing ? "A mandatory document is missing" : "A mandatory requirement is not met",
    body:
      "The buyer can still see your submission, but mandatory gaps are usually decisive. " +
      "Everything flagged below is worth fixing before the deadline.",
  };
}

export function ScreeningPanel({ screening }: { screening: ScreeningResult }) {
  if (screening.status === "pending" || screening.status === "processing") {
    return (
      <GlassCard className="p-6">
        <div className="flex items-center gap-3">
          <PortalSpinner />
          <div>
            <p className="text-sm font-semibold">
              {screening.status === "pending" ? "Queued for screening" : "Screening your documents"}
            </p>
            {/* Real stage, never a fabricated percentage. */}
            <p className="mt-0.5 text-xs text-portal-muted">
              Reading each page, then matching it against the buyer&rsquo;s checklist. This page
              updates itself.
            </p>
          </div>
        </div>
      </GlassCard>
    );
  }

  if (screening.status === "failed") {
    return (
      <GlassCard className="p-6">
        <p className="text-sm font-semibold text-portal-rose">Screening could not finish</p>
        <p className="mt-1.5 text-sm text-portal-muted">
          {screening.error_code === "failed_extraction"
            ? "No readable text could be extracted from the files you uploaded. If they are scans, re-upload a clearer copy."
            : "Something went wrong while screening this submission. You can try again."}
        </p>
      </GlassCard>
    );
  }

  const score = screening.overall_score;
  const scoreTone =
    score === null || score === undefined
      ? "neutral"
      : score >= 80
        ? "positive"
        : score >= 55
          ? "warning"
          : "danger";

  const grouped = {
    missing: screening.findings.filter((f) => f.verdict === "missing"),
    unverified: screening.findings.filter((f) => f.verdict === "present_unverified"),
    attention: screening.findings.filter(
      (f) => f.verdict === "present_expired" || f.verdict === "present_unreadable",
    ),
    supplied: screening.findings.filter((f) => f.verdict === "present"),
    na: screening.findings.filter((f) => f.verdict === "not_applicable"),
  };

  const blocking = describeBlockingGap(grouped.missing, grouped.unverified);

  return (
    <div className="space-y-5">
      <GlassCard className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-xs uppercase tracking-wide text-portal-faint">
              Document readiness
            </p>
            <p className="mt-1 flex items-baseline gap-2">
              <span className="text-5xl font-semibold leading-none">
                {score === null || score === undefined ? "—" : score}
              </span>
              {score !== null && score !== undefined ? (
                <span className="text-lg text-portal-faint">/ 100</span>
              ) : null}
            </p>
            <p className="mt-2 text-xs text-portal-muted">
              Calculated in code from the checklist below
              {screening.scoring_version ? ` · scoring v${screening.scoring_version}` : ""}.
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
            <dt className="text-portal-muted">Mandatory</dt>
            <dd className="text-right font-semibold tabular-nums">
              {screening.mandatory_met}/{screening.mandatory_total}
            </dd>
            <dt className="text-portal-muted">Optional</dt>
            <dd className="text-right font-semibold tabular-nums">
              {screening.optional_met}/{screening.optional_total}
            </dd>
          </dl>
        </div>

        {screening.has_blocking_gap ? (
          <div className="mt-5 rounded-xl border border-portal-rose/40 bg-portal-rose/10 px-4 py-3">
            <p className="text-sm font-semibold text-portal-rose">{blocking.title}</p>
            <p className="mt-1 text-xs text-portal-muted">{blocking.body}</p>
          </div>
        ) : (
          <div className="mt-5 flex items-center gap-2">
            <Pill tone={scoreTone === "neutral" ? "neutral" : scoreTone}>
              {scoreTone === "positive"
                ? "Every mandatory document supplied"
                : "No mandatory gaps"}
            </Pill>
          </div>
        )}

        {screening.pages_needing_ocr ? (
          <p className="mt-4 text-xs text-portal-amber">
            {screening.pages_needing_ocr} page
            {screening.pages_needing_ocr === 1 ? "" : "s"} could not be read as text. Anything on
            those pages was not assessed — that is a limit of what we could read, not a judgement
            about your documents.
          </p>
        ) : null}

        {screening.summary ? (
          <p className="mt-4 border-t border-portal-line pt-4 text-sm leading-relaxed text-portal-muted">
            {screening.summary}
          </p>
        ) : null}
      </GlassCard>

      {grouped.missing.length > 0 ? (
        <FindingGroup
          title="Not found in your documents"
          description="Searched every page we could read and did not find these. If you did upload one, check it is the right file and that the scan is legible."
          findings={grouped.missing}
        />
      ) : null}

      {grouped.unverified.length > 0 ? (
        <FindingGroup
          title="Could not be verified"
          description="You supplied these and they were read. What is unconfirmed is the credential itself — the number printed on the document was looked up in the register this portal holds and did not come back valid. That is not the same as a missing document, and the note on each one says exactly what was checked."
          findings={grouped.unverified}
        />
      ) : null}

      {grouped.attention.length > 0 ? (
        <FindingGroup
          title="Needs attention"
          description="Supplied, but not in a state the buyer is likely to accept."
          findings={grouped.attention}
        />
      ) : null}

      {grouped.supplied.length > 0 ? (
        <FindingGroup
          title="Supplied"
          description="Matched to a page in your upload. The quote is the text the match was made on."
          findings={grouped.supplied}
        />
      ) : null}

      {grouped.na.length > 0 ? (
        <FindingGroup title="Not applicable" findings={grouped.na} />
      ) : null}
    </div>
  );
}

function FindingGroup({
  title,
  description,
  findings,
}: {
  title: string;
  description?: string;
  findings: ScreeningFinding[];
}) {
  return (
    <GlassCard className="p-6">
      <header>
        <h3 className="text-sm font-semibold">{title}</h3>
        {description ? <p className="mt-1 text-xs text-portal-muted">{description}</p> : null}
      </header>

      <ul className="mt-4 space-y-3">
        {findings.map((finding) => {
          const meta = VERDICT_META[finding.verdict] ?? {
            label: humanise(finding.verdict),
            tone: "neutral" as const,
            blurb: "",
          };
          return (
            <li
              key={finding.document_type}
              className="rounded-xl border border-portal-line bg-portal-void/40 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">
                  {finding.label ?? humanise(finding.document_type)}
                </p>
                <div className="flex items-center gap-2">
                  {finding.is_mandatory ? <Pill tone="neutral">Mandatory</Pill> : null}
                  <Pill tone={meta.tone}>{meta.label}</Pill>
                </div>
              </div>

              <p className="mt-1.5 text-xs text-portal-muted">{finding.note ?? meta.blurb}</p>

              {finding.evidence_quote ? (
                <figure className="mt-3 border-l-2 border-portal-violet/60 pl-3">
                  <blockquote className="text-xs italic leading-relaxed text-portal-muted">
                    &ldquo;{finding.evidence_quote}&rdquo;
                  </blockquote>
                  {finding.source_page ? (
                    <figcaption className="mt-1 text-[11px] text-portal-faint">
                      Page {finding.source_page} of your upload
                    </figcaption>
                  ) : null}
                </figure>
              ) : null}
            </li>
          );
        })}
      </ul>
    </GlassCard>
  );
}
