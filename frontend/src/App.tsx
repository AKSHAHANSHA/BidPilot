import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { Spinner } from "./components/ui";
import { AppShell } from "./components/AppShell";
import { AuthPage, ForgotPasswordPage } from "./pages/AuthPage";
import { LandingPage } from "./pages/LandingPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { VendorDashboardPage } from "./pages/VendorDashboardPage";
import { CompanyDashboardPage } from "./pages/CompanyDashboardPage";
import { CompanyNewProjectPage } from "./pages/CompanyNewProjectPage";
import { TenderDeskPage } from "./pages/TenderDeskPage";
import { NewTenderPage } from "./pages/NewTenderPage";
import { TenderPage } from "./pages/TenderPage";
import { CompanyProfilePage } from "./pages/CompanyProfilePage";
import { EngineeringNotesPage } from "./pages/EngineeringNotesPage";

/**
 * TenderSphere route table.
 *
 * Public routes (`/`, `/projects`, `/projects/:id`, `/auth/*`) render without the app shell —
 * their own dark headers/footers. Everything else is behind the shell and requires
 * authentication. Signed-in vendors and companies share the same shell but see different
 * dashboards on `/`.
 */
export function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center">
        <Spinner label="Loading TenderSphere…" />
      </div>
    );
  }

  return (
    <Routes>
      {/* --- Public --------------------------------------------------- */}
      <Route path="/" element={user ? <AuthedRoot /> : <LandingPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      <Route
        path="/auth"
        element={user ? <Navigate to="/" replace /> : <AuthPage />}
      />
      <Route path="/auth/forgot-password" element={<ForgotPasswordPage />} />

      {/* --- Authenticated (require sign-in) ------------------------- */}
      <Route
        path="/company/projects/new"
        element={requireAuth(user, <AppShell><CompanyNewProjectPage /></AppShell>)}
      />
      <Route
        path="/company/profile"
        element={requireAuth(user, <AppShell><CompanyProfilePage /></AppShell>)}
      />
      {/* Old BidPilot flow is now the vendor-only "AI self-check" tool. */}
      <Route
        path="/self-check"
        element={requireAuth(user, <AppShell><TenderDeskPage /></AppShell>)}
      />
      <Route
        path="/self-check/new"
        element={requireAuth(user, <AppShell><NewTenderPage /></AppShell>)}
      />
      <Route
        path="/self-check/:tenderId"
        element={requireAuth(user, <AppShell><TenderPage /></AppShell>)}
      />
      <Route
        path="/about"
        element={requireAuth(user, <AppShell><EngineeringNotesPage /></AppShell>)}
      />

      {/* Legacy paths that used to be top-level in BidPilot. Redirect them to the new self-check namespace so bookmarks still work. */}
      <Route path="/tenders/new" element={<Navigate to="/self-check/new" replace />} />
      <Route path="/tenders/:tenderId" element={<Navigate to="/self-check" replace />} />
      <Route path="/company" element={<Navigate to="/company/profile" replace />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function AuthedRoot() {
  const { user } = useAuth();
  return (
    <AppShell>
      {user?.account_type === "company" ? <CompanyDashboardPage /> : <VendorDashboardPage />}
    </AppShell>
  );
}

function requireAuth(user: unknown, element: ReactElement): ReactElement {
  return user ? element : <Navigate to="/auth?mode=login" replace />;
}
