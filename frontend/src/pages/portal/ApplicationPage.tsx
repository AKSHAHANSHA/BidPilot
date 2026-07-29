import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PortalShell } from "../../components/portal/PortalShell";
import {
  EmptyState,
  GlassCard,
  Pill,
  PortalAlert,
  PortalButton,
  PortalField,
  PortalLinkButton,
  PortalSpinner,
  PortalTextArea,
  Skeleton,
} from "../../components/portal/kit";
import { ScreeningPanel } from "../../components/portal/ScreeningPanel";
import { ApplicationStatusPill } from "./MyApplicationsPage";
import { describeDeadline, formatDate, formatMoney, humanise } from "../../lib/format";
import {
  portal,
  type ApplicationDetail,
  type ApplicationDocument,
  type DocumentRequirement,
  type ListingDetail,
} from "../../api/portal";
import { useAuth } from "../../lib/auth";

/** How often to ask whether screening has finished. Long enough not to hammer the API, short
 *  enough that a vendor watching the page sees the result rather than a stale spinner. */
const SCREENING_POLL_MS = 4000;

/**
 * One application, from draft to decision.
 *
 * The page has three lives and shows them in sequence rather than as tabs: while it is a draft
 * it is a form, once submitted it is a screening report, and once the buyer has answered it is
 * a record of that answer. Editing stops at submission because the buyer is by then reading
 * what was sent, and a bid that changed under them would make their applicant list a
 * description of something that no longer exists.
 */
export function ApplicationPage() {
  const { applicationId = "" } = useParams<{ applicationId: string }>();
  const { user } = useAuth();

  const application = useQuery({
    queryKey: ["portal", "application", applicationId],
    queryFn: () => portal.application(applicationId),
    enabled: applicationId !== "" && user?.account_type === "vendor",
  });

  const data = application.data;
  const isDraft = data?.status === "draft";

  // The public listing carries the checklist. It is the buyer's requirement list, so it is
  // fetched from the same endpoint a vendor read before applying — the two must not disagree.
  const listing = useQuery({
    queryKey: ["portal", "listing", data?.listing_id ?? ""],
    queryFn: () => portal.listing(data?.listing_id ?? ""),
    enabled: Boolean(data?.listing_id),
  });

  const screening = useQuery({
    queryKey: ["portal", "application", applicationId, "screening"],
    queryFn: () => portal.screening(applicationId),
    // 404s until the application has been submitted, and a 404 is an answer, not a fault.
    enabled: data !== undefined && !isDraft,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Terminal means terminal: the timer is torn down rather than left running against a
      // result that can no longer change. A poll with no stop condition is a battery bug.
      return status === "pending" || status === "processing" ? SCREENING_POLL_MS : false;
    },
  });

  if (user && user.account_type !== "vendor") {
    return (
      <PortalShell>
        <div className="mx-auto max-w-3xl px-5 py-16">
          <EmptyState
            title="This page belongs to vendor accounts"
            description="Applications are made and edited by the vendor who owns them. As a buying organisation you see the applicants on your own listings instead."
            action={<PortalLinkButton to="/dashboard">Go to your dashboard</PortalLinkButton>}
          />
        </div>
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <div className="mx-auto max-w-5xl px-5 py-10 sm:py-12">
        <Link
          to="/applications"
          className="text-sm text-portal-muted transition-colors hover:text-portal-ink"
        >
          ← Your applications
        </Link>

        {application.isPending ? (
          <div className="mt-6 space-y-4">
            <Skeleton className="h-10 w-full max-w-lg" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : null}

        {application.isError ? (
          <div className="mt-6">
            <PortalAlert message={(application.error as Error).message} />
          </div>
        ) : null}

        {data ? (
          <div className="mt-6 space-y-6">
            <Header application={data} />

            {data.decided_at ? <DecisionCard application={data} /> : null}

            {isDraft ? (
              <>
                <BidForm key={data.id} application={data} />
                <DocumentSection
                  application={data}
                  requirements={listing.data?.document_requirements ?? []}
                  listingLoading={listing.isPending}
                />
                <SubmitCard application={data} listing={listing.data} />
              </>
            ) : (
              <>
                <SubmittedSummary application={data} />

                {screening.isError ? (
                  <GlassCard className="p-6">
                    <p className="text-sm font-semibold">No screening result yet</p>
                    <p className="mt-1.5 text-sm text-portal-muted">
                      {(screening.error as Error).message}
                    </p>
                  </GlassCard>
                ) : null}

                {screening.isPending && !screening.isError ? (
                  <GlassCard className="p-6">
                    <PortalSpinner label="Loading the screening result…" />
                  </GlassCard>
                ) : null}

                {screening.data ? <ScreeningPanel screening={screening.data} /> : null}
              </>
            )}
          </div>
        ) : null}
      </div>
    </PortalShell>
  );
}

/* ------------------------------------------------------------------ parts -- */

function Header({ application }: { application: ApplicationDetail }) {
  const deadline = describeDeadline(
    application.listing.submission_deadline,
    application.listing.days_remaining,
  );

  return (
    <header>
      <div className="flex flex-wrap items-center gap-2">
        <ApplicationStatusPill status={application.status} />
        <Pill tone={deadline.tone}>{deadline.label}</Pill>
      </div>

      <h1 className="mt-3 text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
        <Link
          to={`/tenders/${application.listing_id}`}
          className="transition-colors hover:text-portal-cyan"
        >
          {application.listing.title}
        </Link>
      </h1>
      <p className="mt-1.5 text-sm text-portal-muted">
        {application.listing.organisation?.name ?? "Buying organisation"} ·{" "}
        {humanise(application.listing.emirate)}
        {application.submitted_at ? ` · submitted ${formatDate(application.submitted_at)}` : ""}
      </p>
    </header>
  );
}

/**
 * The buyer's answer, shown verbatim.
 *
 * Their note is their reasoning in their own words. It is not summarised, shortened, or
 * softened here — a vendor who lost is entitled to read exactly what they were told.
 */
function DecisionCard({ application }: { application: ApplicationDetail }) {
  const won = application.status === "approved";
  return (
    <GlassCard
      className={`p-6 ${won ? "border-portal-emerald/40" : "border-portal-line-bright"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold">The buyer has decided</p>
        <ApplicationStatusPill status={application.status} />
        <span className="text-xs text-portal-faint">{formatDate(application.decided_at)}</span>
      </div>
      {application.decision_note ? (
        <blockquote className="mt-3 border-l-2 border-portal-violet/60 pl-3 text-sm leading-relaxed text-portal-muted">
          {application.decision_note}
        </blockquote>
      ) : (
        <p className="mt-2 text-sm text-portal-muted">They did not leave a note.</p>
      )}
    </GlassCard>
  );
}

/**
 * The draft form.
 *
 * State is seeded from the loaded application once, at mount — the parent keys this component
 * by application id, so the seed can never be stale, and a save landing mid-edit cannot yank
 * a field out from under the cursor.
 */
function BidForm({ application }: { application: ApplicationDetail }) {
  const queryClient = useQueryClient();
  const [bidAmount, setBidAmount] = useState(application.bid_amount ?? "");
  const [estimatedCost, setEstimatedCost] = useState(application.estimated_cost ?? "");
  const [duration, setDuration] = useState(
    application.proposed_duration_months ? String(application.proposed_duration_months) : "",
  );
  const [coverLetter, setCoverLetter] = useState(application.cover_letter ?? "");

  const save = useMutation({
    mutationFn: () =>
      portal.updateApplication(application.id, {
        // An empty field is an explicit null, which clears the column. Sending "" would be a
        // number the backend has to reject, and omitting the key would silently keep the old
        // value after the vendor deleted it.
        bid_amount: bidAmount.trim() || null,
        estimated_cost: estimatedCost.trim() || null,
        proposed_duration_months: duration.trim() ? Number(duration) : null,
        cover_letter: coverLetter.trim() || null,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal", "application", application.id] }),
  });

  const margin =
    bidAmount.trim() && estimatedCost.trim()
      ? Number(bidAmount) - Number(estimatedCost)
      : null;

  return (
    <GlassCard className="p-6">
      <h2 className="text-lg font-semibold">Your bid</h2>
      <p className="mt-1.5 text-sm text-portal-muted">
        Editable until you submit. Nothing here reaches the buyer before then.
      </p>

      <form
        className="mt-5 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <PortalField
            label="Bid amount (AED)"
            inputMode="decimal"
            value={bidAmount}
            onChange={(event) => setBidAmount(event.target.value)}
            hint="What you are charging. The buyer sees this."
            placeholder="750000.00"
          />
          <PortalField
            label="Expected cost (AED)"
            inputMode="decimal"
            value={estimatedCost}
            onChange={(event) => setEstimatedCost(event.target.value)}
            hint="Private to you. Never sent to the buyer — it exists only so your own dashboard can show a margin."
            placeholder="600000.00"
          />
        </div>

        {margin !== null && Number.isFinite(margin) ? (
          <p className="text-xs text-portal-muted">
            Your margin on this bid would be{" "}
            <span className={margin < 0 ? "text-portal-rose" : "text-portal-emerald"}>
              {formatMoney(margin) ?? "—"}
            </span>
            . Shown to you only.
          </p>
        ) : null}

        <PortalField
          label="Proposed duration (months)"
          inputMode="numeric"
          value={duration}
          onChange={(event) => setDuration(event.target.value)}
          placeholder="12"
        />

        <PortalTextArea
          label="Cover letter"
          rows={8}
          value={coverLetter}
          onChange={(event) => setCoverLetter(event.target.value)}
          hint="Your pitch, in your words. The buyer reads it alongside your documents."
        />

        <div className="flex flex-wrap items-center gap-3">
          <PortalButton type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save draft"}
          </PortalButton>
          {save.isSuccess && !save.isPending ? (
            <span className="text-xs text-portal-emerald">Saved.</span>
          ) : null}
        </div>

        {save.isError ? <PortalAlert message={(save.error as Error).message} /> : null}
      </form>
    </GlassCard>
  );
}

/**
 * Uploads, laid out against the buyer's checklist rather than as a bare file list.
 *
 * A vendor's question is never "what have I uploaded" — it is "what is still missing", and the
 * only way to answer that on this page is to show the requirement and the file side by side.
 * The declared type is a hint the vendor gives screening, not a verdict: the pipeline still
 * reads the file and decides what it actually is.
 */
function DocumentSection({
  application,
  requirements,
  listingLoading,
}: {
  application: ApplicationDetail;
  requirements: DocumentRequirement[];
  listingLoading: boolean;
}) {
  const queryClient = useQueryClient();
  const [pendingType, setPendingType] = useState<string | null>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["portal", "application", application.id] });

  const upload = useMutation({
    mutationFn: ({ file, declaredType }: { file: File; declaredType?: string }) =>
      portal.uploadApplicationDocument(application.id, file, declaredType),
    onSettled: () => setPendingType(null),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (documentId: string) =>
      portal.deleteApplicationDocument(application.id, documentId),
    onSuccess: invalidate,
  });

  const ordered = [...requirements].sort((a, b) => a.display_order - b.display_order);
  const byRequirement = new Map<string, ApplicationDocument[]>();
  for (const document of application.documents) {
    const key = document.declared_document_type ?? "";
    byRequirement.set(key, [...(byRequirement.get(key) ?? []), document]);
  }
  const declaredTypes = new Set(ordered.map((item) => item.document_type));
  const unmatched = application.documents.filter(
    (document) =>
      document.declared_document_type === null ||
      document.declared_document_type === undefined ||
      !declaredTypes.has(document.declared_document_type),
  );

  const onPick = (file: File | undefined, declaredType?: string) => {
    if (!file) return;
    setPendingType(declaredType ?? "");
    upload.mutate({ file, declaredType });
  };

  return (
    <GlassCard className="p-6">
      <h2 className="text-lg font-semibold">Your documents</h2>
      <p className="mt-1.5 text-sm text-portal-muted">
        PDFs only. Attach one against each requirement so screening knows what you meant it to
        satisfy — it still reads every file and decides for itself, so a wrong label costs you
        nothing but a right one helps.
      </p>

      {listingLoading ? (
        <div className="mt-5">
          <PortalSpinner label="Loading the buyer's checklist…" />
        </div>
      ) : null}

      {upload.isError ? (
        <div className="mt-4">
          <PortalAlert message={(upload.error as Error).message} />
        </div>
      ) : null}
      {remove.isError ? (
        <div className="mt-4">
          <PortalAlert message={(remove.error as Error).message} />
        </div>
      ) : null}

      <ul className="mt-5 space-y-3">
        {ordered.map((requirement) => (
          <li
            key={requirement.id}
            className="rounded-xl border border-portal-line bg-portal-void/40 p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {requirement.label ?? humanise(requirement.document_type)}
                </p>
                {requirement.notes ? (
                  <p className="mt-1 text-xs leading-relaxed text-portal-muted">
                    {requirement.notes}
                  </p>
                ) : null}
              </div>
              <Pill tone={requirement.is_mandatory ? "danger" : "neutral"}>
                {requirement.is_mandatory ? "Mandatory" : "Optional"}
              </Pill>
            </div>

            <ul className="mt-3 space-y-2">
              {(byRequirement.get(requirement.document_type) ?? []).map((document) => (
                <AttachedFile
                  key={document.id}
                  document={document}
                  onRemove={() => remove.mutate(document.id)}
                  removing={remove.isPending && remove.variables === document.id}
                />
              ))}
            </ul>

            <div className="mt-3">
              <FilePicker
                label="Attach a PDF"
                busy={upload.isPending && pendingType === requirement.document_type}
                onPick={(file) => onPick(file, requirement.document_type)}
              />
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-6 border-t border-portal-line pt-5">
        <h3 className="text-sm font-semibold">Anything else</h3>
        <p className="mt-1 text-xs text-portal-muted">
          Files that do not answer a checklist item. They are still read and still count towards
          what screening can find.
        </p>

        <ul className="mt-3 space-y-2">
          {unmatched.map((document) => (
            <AttachedFile
              key={document.id}
              document={document}
              onRemove={() => remove.mutate(document.id)}
              removing={remove.isPending && remove.variables === document.id}
            />
          ))}
        </ul>

        <div className="mt-3">
          <FilePicker
            label="Attach another PDF"
            busy={upload.isPending && pendingType === ""}
            onPick={(file) => onPick(file)}
          />
        </div>
      </div>
    </GlassCard>
  );
}

function AttachedFile({
  document,
  onRemove,
  removing,
}: {
  document: ApplicationDocument;
  onRemove: () => void;
  removing: boolean;
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border border-portal-line bg-portal-deep/60 px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{document.original_filename}</p>
        <p className="text-xs text-portal-faint">
          {document.page_count ? `${document.page_count} pages · ` : ""}
          {Math.max(1, Math.round(document.size_bytes / 1024))} KB
        </p>
      </div>
      <PortalButton variant="quiet" onClick={onRemove} disabled={removing}>
        {removing ? "Removing…" : "Remove"}
      </PortalButton>
    </li>
  );
}

/**
 * A file input dressed as a button.
 *
 * The native control is kept in the accessibility tree and keyboard-reachable — it is only
 * visually replaced — because a div pretending to be a file picker is unusable with a screen
 * reader. The value is cleared after each pick so choosing the same file twice still fires.
 */
function FilePicker({
  label,
  busy,
  onPick,
}: {
  label: string;
  busy: boolean;
  onPick: (file: File | undefined) => void;
}) {
  return (
    <label
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-portal-line bg-portal-deep/60 px-5 text-sm font-semibold text-portal-ink transition-colors hover:border-portal-line-bright ${
        busy ? "cursor-not-allowed opacity-50" : ""
      }`}
    >
      <input
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        disabled={busy}
        onChange={(event) => {
          onPick(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      {busy ? "Uploading…" : label}
    </label>
  );
}

/**
 * Submit, and the reason it is not available yet.
 *
 * A disabled button with no explanation is a dead end. The blocking condition is stated as
 * text next to the control, because the vendor cannot fix what they are not told.
 */
function SubmitCard({
  application,
  listing,
}: {
  application: ApplicationDetail;
  listing: ListingDetail | undefined;
}) {
  const queryClient = useQueryClient();
  const submit = useMutation({
    mutationFn: () => portal.submitApplication(application.id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal", "application", application.id] }),
  });

  const closed =
    application.listing.days_remaining !== null &&
    application.listing.days_remaining !== undefined &&
    application.listing.days_remaining < 0;
  const noDocuments = application.documents.length === 0;

  const blockedBecause = closed
    ? "The submission deadline for this tender has passed, so it can no longer be sent."
    : noDocuments
      ? "Attach at least one document first. Screening has nothing to read otherwise, and a submission with no documents scores nothing."
      : null;

  const outstanding = (listing?.document_requirements ?? []).filter(
    (requirement) =>
      requirement.is_mandatory &&
      !application.documents.some(
        (document) => document.declared_document_type === requirement.document_type,
      ),
  );

  return (
    <GlassCard className="p-6">
      <h2 className="text-lg font-semibold">Submit to the buyer</h2>
      <p className="mt-1.5 text-sm text-portal-muted">
        Submitting locks the bid and queues screening. Your documents are read page by page and
        matched against the checklist, and both you and the buyer see the result.
      </p>

      {outstanding.length > 0 && !noDocuments ? (
        <p className="mt-4 rounded-xl border border-portal-amber/40 bg-portal-amber/10 px-4 py-3 text-xs text-portal-amber">
          You have not labelled a file for {outstanding.length} mandatory requirement
          {outstanding.length === 1 ? "" : "s"}:{" "}
          {outstanding.map((item) => item.label ?? humanise(item.document_type)).join(", ")}. You
          can still submit — screening reads every file regardless of how it is labelled — but if
          one of those documents genuinely is not attached, it will be reported as not found.
        </p>
      ) : null}

      {blockedBecause ? (
        <p className="mt-4 text-sm text-portal-amber">{blockedBecause}</p>
      ) : null}

      <div className="mt-4">
        <PortalButton
          onClick={() => submit.mutate()}
          disabled={submit.isPending || blockedBecause !== null}
        >
          {submit.isPending ? "Submitting…" : "Submit application"}
        </PortalButton>
      </div>

      {submit.isError ? (
        <div className="mt-3">
          <PortalAlert message={(submit.error as Error).message} />
        </div>
      ) : null}
    </GlassCard>
  );
}

/** What was sent, once it can no longer be changed. */
function SubmittedSummary({ application }: { application: ApplicationDetail }) {
  return (
    <GlassCard className="p-6">
      <h2 className="text-lg font-semibold">What you submitted</h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-portal-faint">Your bid</dt>
          <dd className="mt-0.5 text-sm font-medium">
            {formatMoney(application.bid_amount) ?? "Not entered"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-portal-faint">Your margin</dt>
          <dd className="mt-0.5 text-sm font-medium">
            {formatMoney(application.margin_amount) ?? "—"}
            <span className="block text-xs font-normal text-portal-faint">
              Private to you
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-portal-faint">Proposed duration</dt>
          <dd className="mt-0.5 text-sm font-medium">
            {application.proposed_duration_months
              ? `${application.proposed_duration_months} months`
              : "Not stated"}
          </dd>
        </div>
      </dl>

      {application.cover_letter ? (
        <p className="mt-5 whitespace-pre-line border-t border-portal-line pt-4 text-sm leading-relaxed text-portal-muted">
          {application.cover_letter}
        </p>
      ) : null}

      <ul className="mt-5 space-y-2 border-t border-portal-line pt-4">
        {application.documents.map((document) => (
          <li key={document.id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="truncate text-portal-ink">{document.original_filename}</span>
            {document.declared_document_type_label ? (
              <Pill tone="neutral">{document.declared_document_type_label}</Pill>
            ) : null}
          </li>
        ))}
      </ul>
    </GlassCard>
  );
}
