import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { PortalAlert, PortalButton, PortalField } from "../../components/portal/kit";
import { useAuth } from "../../lib/auth";

export function SignInPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Pick up where you left off — your tenders, applications and screening results."
      footer={
        <>
          New here?{" "}
          <Link to="/signup" className="text-portal-cyan hover:text-portal-ink">
            Create an account
          </Link>
        </>
      }
    >
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
        <PortalField
          label="Password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />

        <div className="flex justify-end">
          <Link
            to="/forgot-password"
            className="text-xs text-portal-muted transition-colors hover:text-portal-ink"
          >
            Forgot your password?
          </Link>
        </div>

        <PortalButton type="submit" disabled={busy} className="w-full">
          {busy ? "Signing in…" : "Sign in"}
        </PortalButton>
      </form>
    </AuthLayout>
  );
}
