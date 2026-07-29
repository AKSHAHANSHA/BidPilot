import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./lib/auth";
import { Spinner } from "./components/ui";
import { AppShell } from "./components/AppShell";
import { TenderDeskPage } from "./pages/TenderDeskPage";
import { NewTenderPage } from "./pages/NewTenderPage";
import { TenderPage } from "./pages/TenderPage";
import { CompanyProfilePage } from "./pages/CompanyProfilePage";
import { EngineeringNotesPage } from "./pages/EngineeringNotesPage";
import { LandingPage } from "./pages/portal/LandingPage";
import { TendersPage } from "./pages/portal/TendersPage";
import { SignInPage } from "./pages/portal/SignInPage";
import { SignUpPage } from "./pages/portal/SignUpPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/portal/PasswordPages";
import { VendorDashboardPage } from "./pages/portal/VendorDashboardPage";
import { CompanyDashboardPage } from "./pages/portal/CompanyDashboardPage";

/**
 * Routing.
 *
 * The marketplace is a public shopfront, so the previous "no user, show the sign-in form"
 * gate is gone: unauthenticated traffic reaches the landing page, the catalogue and the
 * sign-up flow. Only the dashboards and the original analysis workspace require an account,
 * and each of those is wrapped in `RequireAuth` individually rather than by a single
 * top-level branch.
 */
export function App() {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center">
        <Spinner label="Loading BidPilot…" />
      </div>
    );
  }

  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/tenders" element={<TendersPage />} />
      <Route path="/categories" element={<TendersPage />} />
      <Route path="/signin" element={<RedirectIfSignedIn><SignInPage /></RedirectIfSignedIn>} />
      <Route path="/signup" element={<RedirectIfSignedIn><SignUpPage /></RedirectIfSignedIn>} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Signed in — the marketplace side */}
      <Route
        path="/dashboard"
        element={
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/projects"
        element={
          <RequireAuth>
            <TendersPage />
          </RequireAuth>
        }
      />

      {/* Signed in — the original tender-analysis workspace, unchanged */}
      <Route
        path="/workspace/*"
        element={
          <RequireAuth>
            <AppShell>
              <Routes>
                <Route path="/" element={<TenderDeskPage />} />
                <Route path="tenders/new" element={<NewTenderPage />} />
                <Route path="tenders/:tenderId" element={<TenderPage />} />
                <Route path="company" element={<CompanyProfilePage />} />
                <Route path="about" element={<EngineeringNotesPage />} />
                <Route path="*" element={<Navigate to="/workspace" replace />} />
              </Routes>
            </AppShell>
          </RequireAuth>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

/** The dashboard a signed-in account sees depends on which side of the marketplace it is on. */
function Dashboard() {
  const { user } = useAuth();
  return user?.account_type === "company" ? <CompanyDashboardPage /> : <VendorDashboardPage />;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  // `state` carries where they were headed so sign-in can return them there, and `replace`
  // keeps the protected URL out of history — a back button should not retry a blocked page.
  return user ? (
    <>{children}</>
  ) : (
    <Navigate to="/signin" state={{ from: location.pathname }} replace />
  );
}

function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user ? <Navigate to="/dashboard" replace /> : <>{children}</>;
}
