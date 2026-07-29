import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PortalShell } from "../../components/portal/PortalShell";
import {
  GlassCard,
  Pill,
  PortalAlert,
  PortalButton,
  PortalLinkButton,
  Skeleton,
  Tag,
} from "../../components/portal/kit";
import { Reveal } from "../../components/portal/Reveal";
import { describeDeadline, formatDate, formatMoney, humanise } from "../../lib/format";
import { PortalError, portal, type DocumentRequirement } from "../../api/portal";
import { useAuth } from "../../lib/auth";

/**
 * One tender, in full — public.
 *
 * This is where a vendor decides whether they can win, and that decision is mostly the
 * document checklist: a contract worth bidding for is worthless if the buyer wants an audited
 * financial statement you will not have for six weeks. So the checklist is the body of the
 * page rather than a footnote, mandatory items separated from optional ones, and every item
 * carries the buyer's own note where they wrote one.
 *
 * Nothing is hidden from a signed-out visitor. The only thing authentication changes is where
 * the Apply button leads.
 */
export function TenderDetailPage() {
  const { listingId = "" } = useParams<{ listingId: string }>();

  const listing = useQuery({
    queryKey: ["portal", "listing", listingId],
    queryFn: () => portal.listing(listingId),
    enabled: listingId !== "",
  });

  const data = listing.data;
  const deadline = describeDeadline(data?.submission_deadline, data?.days_remaining);
  const requirements = [...(data?.document_requirements ?? [])].sort(
    (a, b) => a.display_order - b.display_order,
  );
  const mandatory = requirements.filter((item) => item.is_mandatory);
  const optional = requirements.filter((item) => !item.is_mandatory);

  return (
    <PortalShell>
      <div className="mx-auto max-w-6xl px-5 py-10 sm:py-12">
        <Link
          to="/tenders"
          className="text-sm text-portal-muted transition-colors hover:text-portal-ink"
        >
          ← All tenders
        </Link>

        {listing.isPending ? <DetailSkeleton /> : null}

        {listing.isError ? (
          <div className="mt-8">
            <PortalAlert message={(listing.error as Error).message} />
          </div>
        ) : null}

        {data ? (
          <>
            <header className="mt-6">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone="accent">{data.category_label ?? humanise(data.category)}</Pill>
                <Pill tone={deadline.tone}>{deadline.label}</Pill>
                {data.organisation?.is_verified ? (
                  <Pill tone="positive">Verified buyer</Pill>
                ) : null}
              </div>

              <h1 className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
                {data.title}
              </h1>

              <p className="mt-3 text-sm text-portal-muted">
                {data.organisation?.name ?? "A buying organisation"} ·{" "}
                {data.city ? `${data.city}, ` : ""}
                {humanise(data.emirate)}
                {data.reference ? ` · ref ${data.reference}` : ""}
              </p>

              <p className="mt-4 max-w-3xl text-base leading-relaxed text-portal-muted">
                {data.summary}
              </p>

              {data.tags?.length ? (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {data.tags.map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </div>
              ) : null}
            </header>

            {/* The apply card is first in the DOM so a phone reader meets it right after the
                title, and moved to the right-hand rail from `lg` up. */}
            <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <aside className="space-y-5 lg:order-2 lg:sticky lg:top-24 lg:self-start">
                <ApplyCard listingId={listingId} closed={isClosed(data.days_remaining)} />

                <GlassCard className="p-5">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-portal-faint">
                    Key terms
                  </h2>
                  <dl className="mt-3 space-y-3 text-sm">
                    <Fact
                      label="Contract value"
                      value={budgetLine(data.budget_min, data.budget_max)}
                    />
                    <Fact
                      label="Submissions close"
                      value={formatDate(data.submission_deadline) ?? "No deadline set"}
                      note={deadline.label}
                    />
                    {data.questions_deadline ? (
                      <Fact
                        label="Questions close"
                        value={formatDate(data.questions_deadline) ?? "—"}
                      />
                    ) : null}
                    <Fact
                      label="Contract duration"
                      value={
                        data.contract_duration_months
                          ? `${data.contract_duration_months} months`
                          : "Not stated"
                      }
                    />
                    <Fact
                      label="Experience required"
                      value={
                        data.min_years_experience
                          ? `${data.min_years_experience}+ years`
                          : "Not stated"
                      }
                    />
                    <Fact
                      label="Bid bond"
                      value={bidBondLine(data.requires_bid_bond, data.bid_bond_percentage)}
                    />
                    <Fact label="Applicants so far" value={String(data.application_count ?? 0)} />
                  </dl>

                  {data.required_certifications?.length ? (
                    <div className="mt-4 border-t border-portal-line pt-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-portal-faint">
                        Certifications named
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {data.required_certifications.map((certification) => (
                          <Tag key={certification}>{certification}</Tag>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </GlassCard>
              </aside>

              <div className="space-y-6 lg:order-1">
                <Reveal>
                  <GlassCard className="p-6">
                    <h2 className="text-lg font-semibold">The brief</h2>
                    {/* The buyer typed this. Their paragraphs are preserved rather than
                        collapsed into one block by HTML whitespace folding. */}
                    <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-portal-muted">
                      {data.description}
                    </p>
                  </GlassCard>
                </Reveal>

                <Reveal delay={80}>
                  <GlassCard className="p-6">
                    <h2 className="text-lg font-semibold">What you have to submit</h2>
                    <p className="mt-1.5 text-sm text-portal-muted">
                      Every application is screened against this list before the buyer reads it.
                      Mandatory items carry four fifths of the readiness score between them, so a
                      gap here is usually decisive.
                    </p>

                    {requirements.length === 0 ? (
                      <p className="mt-5 rounded-xl border border-portal-line bg-portal-void/40 p-4 text-sm text-portal-muted">
                        This buyer has not published a document checklist. You can still apply and
                        attach whatever the brief calls for.
                      </p>
                    ) : (
                      <div className="mt-5 space-y-6">
                        <RequirementList
                          title="Mandatory"
                          description="Missing any one of these is what a buyer usually rejects on."
                          tone="danger"
                          items={mandatory}
                        />
                        <RequirementList
                          title="Optional"
                          description="Not required, but each one supplied lifts your readiness score."
                          tone="neutral"
                          items={optional}
                        />
                      </div>
                    )}
                  </GlassCard>
                </Reveal>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </PortalShell>
  );
}

/** The API's `days_remaining` is the server's arithmetic; a browser clock never decides this. */
const isClosed = (daysRemaining: number | null | undefined) =>
  daysRemaining !== null && daysRemaining !== undefined && daysRemaining < 0;

function budgetLine(min: string | null | undefined, max: string | null | undefined) {
  const low = formatMoney(min);
  const high = formatMoney(max);
  if (low && high) return low === high ? low : `${low} – ${high}`;
  if (low) return `From ${low}`;
  if (high) return `Up to ${high}`;
  return "Undisclosed";
}

function bidBondLine(required: boolean, percentage: string | null | undefined) {
  if (!required) return "Not required";
  return percentage ? `Required · ${percentage}% of the bid` : "Required";
}

function Fact({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-portal-muted">{label}</dt>
      <dd className="text-right font-medium">
        {value}
        {note ? <span className="block text-xs font-normal text-portal-faint">{note}</span> : null}
      </dd>
    </div>
  );
}

function RequirementList({
  title,
  description,
  tone,
  items,
}: {
  title: string;
  description: string;
  tone: "danger" | "neutral";
  items: DocumentRequirement[];
}) {
  if (items.length === 0) return null;

  return (
    <section>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={tone}>
          {title} · {items.length}
        </Pill>
        <p className="text-xs text-portal-muted">{description}</p>
      </div>

      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li
            key={item.id}
            className="rounded-xl border border-portal-line bg-portal-void/40 p-4"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-medium">{item.label ?? humanise(item.document_type)}</p>
              <span className="text-xs text-portal-faint">
                weight {item.weight}
              </span>
            </div>
            {item.notes ? (
              <p className="mt-1.5 text-xs leading-relaxed text-portal-muted">{item.notes}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * The Apply control, which is four different things depending on who is looking.
 *
 * A signed-out visitor is sent to registration rather than shown a disabled button — the point
 * of a public catalogue is to convert. A buying account is told plainly why it cannot apply,
 * because `account_type` is fixed at registration and pretending otherwise wastes their time.
 */
function ApplyCard({ listingId, closed }: { listingId: string; closed: boolean }) {
  const { user } = useAuth();
  const navigate = useNavigate();

  const apply = useMutation({
    mutationFn: () => startApplication(listingId),
    onSuccess: (applicationId) => navigate(`/applications/${applicationId}`),
  });

  if (closed) {
    return (
      <GlassCard className="p-5">
        <p className="text-sm font-semibold">Applications have closed</p>
        <p className="mt-1.5 text-sm text-portal-muted">
          The submission deadline for this tender has passed, so no new application can be
          started. The listing stays visible as a record of what was asked for.
        </p>
      </GlassCard>
    );
  }

  if (!user) {
    return (
      <GlassCard className="p-5">
        <p className="text-sm font-semibold">Apply for this tender</p>
        <p className="mt-1.5 text-sm text-portal-muted">
          Applying needs a vendor account: your organisation details go on the bid, and your
          documents have to belong to someone.
        </p>
        <div className="mt-4 flex flex-col gap-2">
          <PortalLinkButton to="/signup?type=vendor">Register as a vendor</PortalLinkButton>
          <PortalLinkButton to="/signin" variant="ghost">
            Sign in
          </PortalLinkButton>
        </div>
      </GlassCard>
    );
  }

  if (user.account_type === "company") {
    return (
      <GlassCard className="p-5">
        <p className="text-sm font-semibold">Buying accounts cannot apply</p>
        <p className="mt-1.5 text-sm text-portal-muted">
          You are signed in as {user.organisation?.name ?? "a buying organisation"}. Buying
          accounts publish tenders and review applicants; bidding is done from a vendor account,
          and the account type is fixed when the account is created.
        </p>
        <div className="mt-4">
          <PortalLinkButton to="/dashboard" variant="ghost">
            Go to your dashboard
          </PortalLinkButton>
        </div>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="p-5">
      <p className="text-sm font-semibold">Apply for this tender</p>
      <p className="mt-1.5 text-sm text-portal-muted">
        This starts a draft. Nothing reaches the buyer until you attach your documents and press
        submit, and you can edit everything until then.
      </p>
      <div className="mt-4">
        <PortalButton
          onClick={() => apply.mutate()}
          disabled={apply.isPending}
          className="w-full"
        >
          {apply.isPending ? "Opening…" : "Apply for this tender"}
        </PortalButton>
      </div>
      {apply.isError ? (
        <div className="mt-3">
          <PortalAlert message={(apply.error as Error).message} />
        </div>
      ) : null}
    </GlassCard>
  );
}

/**
 * Start an application, or open the one that already exists.
 *
 * The backend answers 409 to a second application on the same listing, which is correct but is
 * not an error from the vendor's point of view — they asked to bid on this tender and they
 * already are. The problem detail carries only a message, not the id, so the existing
 * application is found by scanning the vendor's own list.
 */
async function startApplication(listingId: string): Promise<string> {
  try {
    const created = await portal.createApplication({ listing_id: listingId });
    return created.id;
  } catch (error) {
    if (!(error instanceof PortalError) || error.status !== 409) throw error;
    const existing = await findApplicationForListing(listingId);
    if (existing === null) throw error;
    return existing;
  }
}

/** `MAX_PAGE_LIMIT` on the backend. */
const SCAN_PAGE_SIZE = 100;
/** Bounded on purpose: past this the honest answer is the conflict message, not a crawl. */
const SCAN_MAX_PAGES = 5;

async function findApplicationForListing(listingId: string): Promise<string | null> {
  for (let page = 0; page < SCAN_MAX_PAGES; page += 1) {
    const offset = page * SCAN_PAGE_SIZE;
    const result = await portal.myApplications({ limit: SCAN_PAGE_SIZE, offset });
    const match = result.items.find((item) => item.listing_id === listingId);
    if (match) return match.id;
    if (offset + result.items.length >= result.total) break;
  }
  return null;
}

function DetailSkeleton() {
  return (
    <div className="mt-6 space-y-4">
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-10 w-full max-w-xl" />
      <Skeleton className="h-4 w-64" />
      <div className="grid gap-8 pt-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-56 w-full" />
      </div>
    </div>
  );
}
