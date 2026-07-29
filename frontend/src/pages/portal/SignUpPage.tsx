import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import {
  PortalAlert,
  PortalButton,
  PortalField,
  PortalSelect,
  PortalTextArea,
} from "../../components/portal/kit";
import { useAuth, type AccountType, type OrganisationInput } from "../../lib/auth";
import { humanise } from "../../lib/format";

const EMIRATES = [
  "abu_dhabi",
  "dubai",
  "sharjah",
  "ajman",
  "umm_al_quwain",
  "ras_al_khaimah",
  "fujairah",
];

const ACCOUNT_TYPES: {
  value: AccountType;
  title: string;
  blurb: string;
  detail: string;
}[] = [
  {
    value: "vendor",
    title: "Vendor",
    blurb: "I want to bid for work",
    detail: "Browse tenders, apply, and have your documents screened before you submit.",
  },
  {
    value: "company",
    title: "Buying organisation",
    blurb: "I want to publish tenders",
    detail: "Publish opportunities, set the document checklist, and review scored applicants.",
  },
];

export function SignUpPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  // The landing page links here with ?type=vendor / ?type=company, so the choice a visitor
  // already made on the CTA is not asked a second time.
  const requested = params.get("type");
  const [accountType, setAccountType] = useState<AccountType>(
    requested === "company" ? "company" : "vendor",
  );

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organisation, setOrganisation] = useState<OrganisationInput>({
    name: "",
    description: "",
    emirate: "dubai",
    contact_email: "",
  });

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setOrg = <K extends keyof OrganisationInput>(key: K, value: OrganisationInput[K]) =>
    setOrganisation((previous) => ({ ...previous, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Optional fields are dropped when blank rather than sent as "": the API validates
      // maximum lengths and URL shapes, and an empty string is a value, not an absence.
      const trimmed: OrganisationInput = { ...organisation };
      for (const key of Object.keys(trimmed) as (keyof OrganisationInput)[]) {
        if (trimmed[key] === "" || trimmed[key] === undefined) delete trimmed[key];
      }

      await register({
        email,
        password,
        display_name: displayName,
        account_type: accountType,
        organisation: trimmed,
      });
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the account.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      wide
      title="Create your account"
      subtitle="One account per organisation. Which side of the marketplace you are on is fixed once you register, so pick carefully."
      footer={
        <>
          Already registered?{" "}
          <Link to="/signin" className="text-portal-cyan hover:text-portal-ink">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-8" noValidate>
        {error ? <PortalAlert message={error} /> : null}

        <fieldset>
          <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-portal-muted">
            Account type
          </legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {ACCOUNT_TYPES.map((option) => {
              const active = accountType === option.value;
              return (
                <label
                  key={option.value}
                  className={`cursor-pointer rounded-xl border p-4 transition-colors ${
                    active
                      ? "border-portal-violet bg-portal-violet/10"
                      : "border-portal-line bg-portal-deep/50 hover:border-portal-line-bright"
                  }`}
                >
                  <input
                    type="radio"
                    name="account_type"
                    value={option.value}
                    checked={active}
                    onChange={() => setAccountType(option.value)}
                    className="sr-only"
                  />
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{option.title}</span>
                    <span
                      aria-hidden="true"
                      className={`h-3.5 w-3.5 rounded-full border ${
                        active
                          ? "border-portal-violet bg-portal-violet"
                          : "border-portal-line-bright"
                      }`}
                    />
                  </span>
                  <span className="mt-1 block text-xs text-portal-cyan">{option.blurb}</span>
                  <span className="mt-2 block text-xs leading-relaxed text-portal-muted">
                    {option.detail}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <fieldset className="space-y-4">
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-portal-muted">
            Your sign-in details
          </legend>
          <div className="grid gap-4 sm:grid-cols-2">
            <PortalField
              label="Your name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              autoComplete="name"
              maxLength={120}
              required
            />
            <PortalField
              label="Work email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </div>
          <PortalField
            label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            hint="At least 12 characters. A passphrase is easier to remember and harder to guess."
            required
          />
        </fieldset>

        <fieldset className="space-y-4">
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-portal-muted">
            {accountType === "company" ? "Your organisation" : "Your company"}
          </legend>

          <PortalField
            label={accountType === "company" ? "Organisation name" : "Company name"}
            value={organisation.name}
            onChange={(event) => setOrg("name", event.target.value)}
            autoComplete="organization"
            maxLength={255}
            required
          />

          <PortalTextArea
            label="What you do"
            value={organisation.description}
            onChange={(event) => setOrg("description", event.target.value)}
            rows={3}
            maxLength={4000}
            hint={
              accountType === "company"
                ? "Shown on every tender you publish."
                : "Used to match you against open tenders, and shown to buyers you apply to."
            }
            required
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <PortalSelect
              label="Emirate"
              value={organisation.emirate}
              onChange={(event) => setOrg("emirate", event.target.value)}
              required
            >
              {EMIRATES.map((emirate) => (
                <option key={emirate} value={emirate}>
                  {humanise(emirate)}
                </option>
              ))}
            </PortalSelect>
            <PortalField
              label="City"
              value={organisation.city ?? ""}
              onChange={(event) => setOrg("city", event.target.value)}
              maxLength={120}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <PortalField
              label="Organisation email"
              type="email"
              value={organisation.contact_email}
              onChange={(event) => setOrg("contact_email", event.target.value)}
              hint="Never shown publicly."
              required
            />
            <PortalField
              label="Phone"
              value={organisation.contact_phone ?? ""}
              onChange={(event) => setOrg("contact_phone", event.target.value)}
              maxLength={40}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <PortalField
              label="Industry"
              value={organisation.industry ?? ""}
              onChange={(event) => setOrg("industry", event.target.value)}
              maxLength={120}
            />
            <PortalField
              label="Trade licence / registration no."
              value={organisation.registration_number ?? ""}
              onChange={(event) => setOrg("registration_number", event.target.value)}
              maxLength={100}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <PortalField
              label="Website"
              type="url"
              placeholder="https://"
              value={organisation.website ?? ""}
              onChange={(event) => setOrg("website", event.target.value)}
            />
            <PortalField
              label="Year established"
              type="number"
              min={1800}
              max={2200}
              value={organisation.year_established ?? ""}
              onChange={(event) =>
                setOrg(
                  "year_established",
                  event.target.value ? Number(event.target.value) : undefined,
                )
              }
            />
            <PortalField
              label="Employees"
              type="number"
              min={0}
              value={organisation.employee_count ?? ""}
              onChange={(event) =>
                setOrg("employee_count", event.target.value ? Number(event.target.value) : undefined)
              }
            />
          </div>
        </fieldset>

        <PortalButton type="submit" disabled={busy} className="w-full">
          {busy ? "Creating your account…" : "Create account"}
        </PortalButton>
      </form>
    </AuthLayout>
  );
}
