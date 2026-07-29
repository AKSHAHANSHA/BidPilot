import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { PortalAlert, PortalButton, PortalField } from "../../components/portal/kit";
import { useAuth } from "../../lib/auth";

/**
 * Request a reset link.
 *
 * The confirmation is identical whether or not the address has an account. That is the whole
 * point of the endpoint's design — a page that said "no account found" would be a free
 * account-enumeration tool — so the UI must not undo it by reporting anything more specific.
 */
export function ForgotPasswordPage() {
  const { requestPasswordReset } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send the reset link.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter the email you signed up with and we will send you a link."
      footer={
        <Link to="/signin" className="text-portal-cyan hover:text-portal-ink">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <div className="portal-glass p-6">
          <p className="text-sm font-semibold">Check your inbox</p>
          <p className="mt-2 text-sm leading-relaxed text-portal-muted">
            If an account exists for <span className="text-portal-ink">{email}</span>, a reset
            link is on its way. The link is valid for one hour and can be used once.
          </p>
          <p className="mt-3 text-xs text-portal-faint">
            Running this locally? Mail goes to the application log by default — the link is
            printed there.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error ? <PortalAlert message={error} /> : null}
          <PortalField
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />
          <PortalButton type="submit" disabled={busy} className="w-full">
            {busy ? "Sending…" : "Send reset link"}
          </PortalButton>
        </form>
      )}
    </AuthLayout>
  );
}

/** Consume a reset token and set a new password. */
export function ResetPasswordPage() {
  const { resetPassword } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    // Checked here as well as on the server: the mismatch is the user's own typo, and a round
    // trip to be told so is a worse experience than an immediate answer.
    if (password !== confirmation) {
      setError("Those two passwords do not match.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not reset the password.");
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <AuthLayout title="That link is incomplete">
        <div className="portal-glass p-6">
          <p className="text-sm leading-relaxed text-portal-muted">
            This page needs the token from your reset email. Open the link from the email
            directly, or request a new one.
          </p>
          <div className="mt-4">
            <Link to="/forgot-password" className="text-sm text-portal-cyan hover:text-portal-ink">
              Request a new link
            </Link>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="Setting a new password signs you out everywhere else."
    >
      {done ? (
        <div className="portal-glass p-6">
          <p className="text-sm font-semibold text-portal-emerald">Password updated</p>
          <p className="mt-2 text-sm text-portal-muted">
            Every other session has been signed out. You can sign in with your new password now.
          </p>
          <PortalButton className="mt-4 w-full" onClick={() => navigate("/signin")}>
            Go to sign in
          </PortalButton>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error ? <PortalAlert message={error} /> : null}
          <PortalField
            label="New password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            hint="At least 12 characters."
            required
          />
          <PortalField
            label="Confirm new password"
            type="password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            autoComplete="new-password"
            required
          />
          <PortalButton type="submit" disabled={busy} className="w-full">
            {busy ? "Updating…" : "Update password"}
          </PortalButton>
        </form>
      )}
    </AuthLayout>
  );
}
