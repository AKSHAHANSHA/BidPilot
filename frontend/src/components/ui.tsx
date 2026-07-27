import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const base =
    "inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium border transition-[background,box-shadow] duration-150 disabled:opacity-50 disabled:cursor-not-allowed rounded-[3px] min-h-11";
  const styles = {
    primary: "bg-ink text-paper border-ink hover:shadow-[3px_3px_0_var(--color-signal)]",
    ghost: "bg-transparent text-ink border-rule-soft hover:border-ink",
    danger: "bg-signal text-white border-signal hover:shadow-[3px_3px_0_var(--color-ink)]",
  }[variant];
  return <button className={`${base} ${styles} ${className}`} {...props} />;
}

export function Field({
  label,
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-ink-muted mb-1">
        {label}
      </span>
      <input
        className="w-full border border-rule-soft bg-surface px-3 py-2 text-sm rounded-[3px] focus:border-ink outline-none min-h-11"
        {...props}
      />
      {error ? <span className="block text-xs text-danger mt-1">{error}</span> : null}
    </label>
  );
}

export function TextArea({
  label,
  error,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; error?: string }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-ink-muted mb-1">
        {label}
      </span>
      <textarea
        className="w-full border border-rule-soft bg-surface px-3 py-2 text-sm rounded-[3px] focus:border-ink outline-none"
        {...props}
      />
      {error ? <span className="block text-xs text-danger mt-1">{error}</span> : null}
    </label>
  );
}

export function Select({
  label,
  error,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; error?: string }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-ink-muted mb-1">
        {label}
      </span>
      <select
        className="w-full border border-rule-soft bg-surface px-3 py-2 text-sm rounded-[3px] focus:border-ink outline-none min-h-11"
        {...props}
      >
        {children}
      </select>
      {error ? <span className="block text-xs text-danger mt-1">{error}</span> : null}
    </label>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`bg-surface border border-rule-soft rounded-[3px] ${className}`}>
      {children}
    </section>
  );
}

export function DecisionStamp({ label }: { label: string }) {
  const tone: Record<string, string> = {
    strong_bid: "border-success text-success",
    conditional_bid: "border-warning text-warning",
    weak_bid: "border-warning text-warning",
    do_not_bid: "border-signal text-signal",
    insufficient_information: "border-ink-muted text-ink-muted",
  };
  return (
    <span
      className={`inline-block border-2 px-3 py-1 font-display text-lg uppercase tracking-wider rounded-[2px] -rotate-2 ${tone[label] ?? "border-ink text-ink"}`}
    >
      {label.replace(/_/g, " ")}
    </span>
  );
}

export function Meter({ value }: { value: number }) {
  const tone = value >= 80 ? "bg-success" : value >= 60 ? "bg-warning" : value >= 40 ? "bg-warning" : "bg-signal";
  return (
    <div className="w-full h-3 bg-rule-soft rounded-[2px] overflow-hidden">
      <div className={`h-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone: Record<string, string> = {
    met: "bg-[color:var(--color-success)]/10 text-success border-success",
    partially_met: "bg-[color:var(--color-warning)]/10 text-warning border-warning",
    not_met: "bg-signal-soft text-signal border-signal",
    needs_clarification: "bg-[color:var(--color-info)]/10 text-info border-info",
    not_applicable: "bg-transparent text-ink-muted border-rule-soft",
    unreviewed: "bg-transparent text-ink-muted border-rule-soft",
  };
  return (
    <span
      className={`inline-block border px-2 py-0.5 text-xs font-medium rounded-[2px] whitespace-nowrap ${tone[status] ?? "border-rule-soft text-ink-muted"}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted" role="status">
      <span className="inline-block w-3 h-3 border-2 border-ink border-t-transparent rounded-full animate-spin" />
      {label}
    </div>
  );
}

export function ProblemAlert({ message }: { message: string }) {
  return (
    <div className="border border-signal bg-signal-soft text-signal px-3 py-2 text-sm rounded-[3px]" role="alert">
      {message}
    </div>
  );
}
