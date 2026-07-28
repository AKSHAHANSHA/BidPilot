import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth, type AccountType } from "../lib/auth";
import { fetchCategories, type CategoryDto } from "../lib/marketplace";

/**
 * TenderSphere sign-in / sign-up. Role toggle at the top of the register form flips between
 * vendor-specific and company-specific field sets. Sign-in stays a plain email/password form.
 */
export function AuthPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const initialMode = (params.get("mode") === "register" ? "register" : "login") as
    | "login"
    | "register";
  const initialRole = (params.get("role") === "company" ? "company" : "vendor") as AccountType;

  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [role, setRole] = useState<AccountType>(initialRole);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [location, setLocation] = useState("");
  const [primaryCategory, setPrimaryCategory] = useState("");
  const [bio, setBio] = useState("");
  const [categories, setCategories] = useState<CategoryDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (mode === "register") {
      fetchCategories().then(setCategories).catch(() => setCategories([]));
    }
  }, [mode]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register({
          email,
          password,
          display_name: displayName,
          account_type: role,
          location: location || undefined,
          primary_category: primaryCategory || undefined,
          bio: bio || undefined,
        });
      }
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#08090f] text-white grid md:grid-cols-2">
      <aside className="hidden md:flex flex-col justify-between p-12 relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-70 pointer-events-none"
          style={{
            background:
              "radial-gradient(600px 400px at 20% 20%, rgba(180,120,255,0.4), transparent), radial-gradient(500px 400px at 80% 80%, rgba(90,220,255,0.35), transparent)",
          }}
        />
        <Link to="/" className="relative flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block w-6 h-6 rounded-full"
            style={{
              background:
                "conic-gradient(from 210deg, #ff8bd4, #7fe4ff, #a3ffcf, #ff8bd4)",
              boxShadow: "0 0 20px rgba(180,120,255,0.6)",
            }}
          />
          <span className="font-display text-xl tracking-tight">TenderSphere</span>
        </Link>
        <div className="relative">
          <p className="font-display text-4xl leading-tight max-w-md">
            One portal for every UAE government-sector tender.
          </p>
          <p className="mt-4 text-white/70 max-w-md">
            Vendors get instant AI screening on every application. Companies get scored applicants
            and a live pipeline dashboard.
          </p>
        </div>
        <div className="relative text-xs text-white/40">
          Advisory only. AI output is not a legal opinion.
        </div>
      </aside>

      <div className="grid place-items-center p-6">
        <div className="w-full max-w-md rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-md p-8 shadow-[0_20px_60px_-40px_rgba(180,120,255,0.6)]">
          <h1 className="font-display text-3xl mb-1">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="text-sm text-white/60 mb-6">
            {mode === "login"
              ? "Access your TenderSphere dashboard."
              : "Choose your role and start in under a minute."}
          </p>

          {mode === "register" ? (
            <div className="mb-4 grid grid-cols-2 gap-2 p-1 bg-white/5 border border-white/10 rounded-lg">
              {(["vendor", "company"] as AccountType[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRole(r)}
                  className={`py-2 text-sm rounded-md transition-colors ${
                    role === r
                      ? "bg-white text-black font-semibold"
                      : "text-white/70 hover:text-white"
                  }`}
                >
                  {r === "vendor" ? "I'm a Vendor" : "I'm a Company"}
                </button>
              ))}
            </div>
          ) : null}

          <form onSubmit={submit} className="space-y-3">
            {error ? (
              <div className="text-sm border border-red-400/40 bg-red-500/10 text-red-200 px-3 py-2 rounded">
                {error}
              </div>
            ) : null}

            {mode === "register" ? (
              <DarkField
                label={role === "company" ? "Company name" : "Display name"}
                value={displayName}
                onChange={setDisplayName}
                required
                autoComplete="name"
              />
            ) : null}
            <DarkField
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              required
              autoComplete="email"
            />
            <DarkField
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />

            {mode === "register" ? (
              <>
                <DarkField
                  label="Location"
                  value={location}
                  onChange={setLocation}
                  placeholder="Dubai, UAE"
                />
                <div>
                  <label className="block text-xs uppercase tracking-widest text-white/50 mb-1">
                    {role === "company"
                      ? "Sector you procure for"
                      : "Primary service category"}
                  </label>
                  <select
                    value={primaryCategory}
                    onChange={(e) => setPrimaryCategory(e.target.value)}
                    className="w-full rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-3 py-2 text-sm"
                  >
                    <option value="">Select a category</option>
                    {categories.map((c) => (
                      <option key={c.slug} value={c.slug}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs uppercase tracking-widest text-white/50 mb-1">
                    {role === "company" ? "About your organisation" : "Short bio"}
                  </label>
                  <textarea
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    rows={3}
                    placeholder={
                      role === "company"
                        ? "Tell vendors about the projects you procure."
                        : "Tell buyers about your capabilities, certifications, past work."
                    }
                    className="w-full rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-3 py-2 text-sm"
                  />
                </div>
              </>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="w-full mt-2 px-4 py-2 rounded-lg bg-white text-black font-semibold hover:bg-white/90 disabled:opacity-50"
            >
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="mt-4 flex items-center justify-between text-xs text-white/60">
            <button
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              className="underline underline-offset-4 hover:text-white"
            >
              {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
            </button>
            {mode === "login" ? (
              <Link
                to="/auth/forgot-password"
                className="underline underline-offset-4 hover:text-white"
              >
                Forgot password?
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function DarkField(props: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  autoComplete?: string;
}) {
  const { label, value, onChange, type = "text", required, placeholder, autoComplete } = props;
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-widest text-white/50 mb-1">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className="w-full rounded-md bg-white/5 border border-white/10 focus:border-white/40 outline-none px-3 py-2 text-sm"
      />
    </label>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setSent(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#08090f] text-white grid place-items-center p-6">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-md p-8">
        <Link to="/auth" className="text-xs text-white/50 hover:text-white">
          ← Back to sign in
        </Link>
        <h1 className="font-display text-3xl mt-4 mb-2">Reset your password</h1>
        {sent ? (
          <p className="text-sm text-white/70">
            If that email is registered, we've sent instructions to reset the password. In this
            portfolio demo, email delivery is not wired up — see the deployment docs.
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-3 mt-4">
            <DarkField label="Email" type="email" value={email} onChange={setEmail} required />
            <button
              type="submit"
              disabled={busy}
              className="w-full px-4 py-2 rounded-lg bg-white text-black font-semibold hover:bg-white/90 disabled:opacity-50"
            >
              {busy ? "Sending…" : "Send reset instructions"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
