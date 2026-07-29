import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PortalLogo } from "../../components/portal/PortalShell";

/**
 * The frame every authentication screen shares.
 *
 * A split layout: the form on the left at a comfortable reading width, and a panel on the
 * right that stays on the marketplace's message. The panel is hidden below `lg` rather than
 * stacked — on a phone it would push the form itself below the fold, which is the one thing
 * a sign-in screen must never do.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Registration collects organisation details and needs a two-column form. */
  wide?: boolean;
}) {
  return (
    <div className="portal min-h-screen">
      <div className="portal-field" aria-hidden="true" />
      <div className="portal-grid" aria-hidden="true" />

      <div className="grid min-h-screen lg:grid-cols-[1fr_minmax(0,38rem)]">
        <div className="flex flex-col px-5 py-8 sm:px-10">
          <Link to="/" className="inline-flex w-fit">
            <PortalLogo />
          </Link>

          <div className="flex flex-1 items-center justify-center py-10">
            <div className={`w-full ${wide ? "max-w-2xl" : "max-w-md"}`}>
              <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
              {subtitle ? (
                <p className="mt-2 text-sm leading-relaxed text-portal-muted">{subtitle}</p>
              ) : null}

              <div className="mt-8">{children}</div>

              {footer ? <p className="mt-6 text-sm text-portal-muted">{footer}</p> : null}
            </div>
          </div>
        </div>

        <aside className="relative hidden overflow-hidden border-l border-portal-line bg-portal-deep/50 lg:block">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-32 top-1/4 h-96 w-96 rounded-full bg-[radial-gradient(circle,var(--color-portal-violet),transparent_70%)] opacity-30 blur-3xl"
          />
          <div className="relative flex h-full flex-col justify-center px-14">
            <blockquote className="text-2xl font-medium leading-snug">
              &ldquo;Every submission is checked against the buyer&rsquo;s requirement list before
              a human reads it — so a missing certificate is something you fix, not something you
              lose a tender over.&rdquo;
            </blockquote>

            <dl className="mt-12 grid grid-cols-3 gap-6 border-t border-portal-line pt-8">
              <div>
                <dt className="text-xs uppercase tracking-wide text-portal-faint">Categories</dt>
                <dd className="mt-1 text-2xl font-semibold">30</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-portal-faint">Emirates</dt>
                <dd className="mt-1 text-2xl font-semibold">7</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-portal-faint">Doc checks</dt>
                <dd className="mt-1 text-2xl font-semibold">24</dd>
              </div>
            </dl>

            <p className="mt-8 text-xs leading-relaxed text-portal-faint">
              Screening scores are calculated in code from verified document matches. The language
              model proposes matches and quotes its source; it never produces the number.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
