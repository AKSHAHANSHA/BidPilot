import { useState, type FormEvent } from "react";
import { useAuth } from "../lib/auth";
import { Button, Card, Field, ProblemAlert } from "../components/ui";

export function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, displayName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12 bg-ink text-paper">
        <div className="font-display text-4xl leading-none">
          BidPilot <span className="text-signal">UAE</span>
        </div>
        <div>
          <p className="font-display text-3xl leading-tight max-w-md">
            Know whether to bid before spending days preparing.
          </p>
          <p className="mt-4 text-sm text-paper/70 max-w-md">
            Upload a tender, compare it against your company evidence, and get a cited,
            explainable bid-readiness score. The score is calculated by explicit rules — never
            guessed by a model.
          </p>
        </div>
        <div className="text-xs text-paper/50">A production-minded portfolio project.</div>
      </div>

      <div className="grid place-items-center p-6">
        <Card className="w-full max-w-md p-8">
          <h1 className="font-display text-2xl mb-1">
            {mode === "login" ? "Sign in" : "Create your account"}
          </h1>
          <p className="text-sm text-ink-muted mb-6">
            {mode === "login"
              ? "Access your tender desk."
              : "Start reviewing tenders in minutes."}
          </p>
          <form onSubmit={submit} className="space-y-4">
            {error ? <ProblemAlert message={error} /> : null}
            {mode === "register" ? (
              <Field
                label="Display name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                autoComplete="name"
              />
            ) : null}
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
          <button
            className="mt-4 text-sm text-signal underline"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
          </button>
        </Card>
      </div>
    </div>
  );
}
