import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { Link } from "react-router-dom";

/**
 * The marketplace design system.
 *
 * Separate from `components/ui.tsx` on purpose: that kit is the paper theme's, built around
 * hairline rules and an editorial red, and every control here needs the opposite treatment.
 * Sharing one kit would mean every component carrying a theme prop, which is a worse trade
 * than two small kits with no conditionals in them.
 */

/* ------------------------------------------------------------------ text -- */

export function GradientText({ children }: { children: ReactNode }) {
  return <span className="portal-gradient-text">{children}</span>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-portal-muted">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-portal-cyan portal-pulse" />
      {children}
    </span>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "left",
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  align?: "left" | "center";
}) {
  return (
    <header className={`max-w-2xl ${align === "center" ? "mx-auto text-center" : ""}`}>
      {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
      <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h2>
      {description ? (
        <p className="mt-3 text-base leading-relaxed text-portal-muted">{description}</p>
      ) : null}
    </header>
  );
}

/* --------------------------------------------------------------- buttons -- */

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold " +
  "min-h-11 transition-[transform,box-shadow,background,border-color] duration-200 " +
  "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0";

const BUTTON_VARIANTS = {
  primary:
    "text-white border border-transparent " +
    "bg-[linear-gradient(100deg,var(--color-portal-violet),var(--color-portal-indigo)_55%,var(--color-portal-cyan))] " +
    "shadow-[0_10px_30px_-12px_var(--color-portal-violet)] hover:-translate-y-0.5 " +
    "hover:shadow-[0_16px_40px_-12px_var(--color-portal-violet)]",
  ghost:
    "text-portal-ink border border-portal-line bg-portal-deep/60 backdrop-blur " +
    "hover:border-portal-line-bright hover:-translate-y-0.5",
  quiet: "text-portal-muted border border-transparent hover:text-portal-ink",
} as const;

type Variant = keyof typeof BUTTON_VARIANTS;

export function PortalButton({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={`${BUTTON_BASE} ${BUTTON_VARIANTS[variant]} ${className}`} {...props} />;
}

export function PortalLinkButton({
  to,
  variant = "primary",
  className = "",
  children,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & {
  to: string;
  variant?: Variant;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={`${BUTTON_BASE} ${BUTTON_VARIANTS[variant]} ${className}`} {...props}>
      {children}
    </Link>
  );
}

/* ----------------------------------------------------------------- cards -- */

export function GlassCard({
  children,
  className = "",
  interactive = false,
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
}) {
  return (
    <div
      className={`portal-glass ${interactive ? "portal-glass-lift portal-edge" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

/* ----------------------------------------------------------------- chips -- */

export function Chip({
  children,
  active = false,
  count,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  active?: boolean;
  count?: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm transition-colors duration-200 ${
        active
          ? "border-transparent bg-[linear-gradient(100deg,var(--color-portal-violet),var(--color-portal-cyan))] text-white"
          : "border-portal-line bg-portal-deep/50 text-portal-muted hover:border-portal-line-bright hover:text-portal-ink"
      }`}
      {...props}
    >
      {children}
      {count !== undefined ? (
        <span className={active ? "text-white/75" : "text-portal-faint"}>{count}</span>
      ) : null}
    </button>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-portal-line px-2.5 py-0.5 text-xs text-portal-muted">
      {children}
    </span>
  );
}

/** Tone is chosen by the caller from meaning, never derived from the string, so an unknown
 *  status can never silently render as "success". */
export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "positive" | "warning" | "danger" | "accent";
}) {
  const tones = {
    neutral: "border-portal-line text-portal-muted",
    positive: "border-portal-emerald/40 text-portal-emerald bg-portal-emerald/10",
    warning: "border-portal-amber/40 text-portal-amber bg-portal-amber/10",
    danger: "border-portal-rose/40 text-portal-rose bg-portal-rose/10",
    accent: "border-portal-violet/40 text-portal-violet bg-portal-violet/10",
  } as const;
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/* ------------------------------------------------------------- feedback --- */

export function PortalSpinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-portal-muted" role="status">
      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-portal-line-bright border-t-portal-cyan" />
      {label}
    </div>
  );
}

export function PortalAlert({
  message,
  tone = "danger",
}: {
  message: string;
  tone?: "danger" | "info";
}) {
  const tones = {
    danger: "border-portal-rose/40 bg-portal-rose/10 text-portal-rose",
    info: "border-portal-line bg-portal-deep/60 text-portal-muted",
  } as const;
  return (
    <div className={`rounded-xl border px-3.5 py-2.5 text-sm ${tones[tone]}`} role="alert">
      {message}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`portal-shimmer rounded-xl ${className}`} aria-hidden="true" />;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="portal-glass flex flex-col items-center gap-3 px-6 py-14 text-center">
      <p className="text-lg font-semibold">{title}</p>
      <p className="max-w-md text-sm text-portal-muted">{description}</p>
      {action}
    </div>
  );
}

/* ---------------------------------------------------------------- inputs -- */

const FIELD_BASE =
  "w-full rounded-xl border border-portal-line bg-portal-deep/70 px-3.5 py-2.5 text-sm " +
  "text-portal-ink placeholder:text-portal-faint outline-none transition-colors duration-200 " +
  "focus:border-portal-violet min-h-11";

export function PortalField({
  label,
  error,
  hint,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-portal-muted">
        {label}
      </span>
      <input className={`${FIELD_BASE} ${className}`} {...props} />
      {hint && !error ? <span className="mt-1 block text-xs text-portal-faint">{hint}</span> : null}
      {error ? <span className="mt-1 block text-xs text-portal-rose">{error}</span> : null}
    </label>
  );
}

export function PortalTextArea({
  label,
  error,
  hint,
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  error?: string;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-portal-muted">
        {label}
      </span>
      <textarea className={`${FIELD_BASE} ${className}`} {...props} />
      {hint && !error ? <span className="mt-1 block text-xs text-portal-faint">{hint}</span> : null}
      {error ? <span className="mt-1 block text-xs text-portal-rose">{error}</span> : null}
    </label>
  );
}

export function PortalSelect({
  label,
  error,
  children,
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-portal-muted">
        {label}
      </span>
      <select className={`${FIELD_BASE} ${className}`} {...props}>
        {children}
      </select>
      {error ? <span className="mt-1 block text-xs text-portal-rose">{error}</span> : null}
    </label>
  );
}
