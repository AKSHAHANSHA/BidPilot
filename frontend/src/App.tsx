import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { Spinner } from "./components/ui";
import { AppShell } from "./components/AppShell";
import { AuthPage } from "./pages/AuthPage";
import { TenderDeskPage } from "./pages/TenderDeskPage";
import { NewTenderPage } from "./pages/NewTenderPage";
import { TenderPage } from "./pages/TenderPage";
import { CompanyProfilePage } from "./pages/CompanyProfilePage";
import { EngineeringNotesPage } from "./pages/EngineeringNotesPage";

export function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center">
        <Spinner label="Loading BidPilot…" />
      </div>
    );
  }

  if (!user) return <AuthPage />;

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<TenderDeskPage />} />
        <Route path="/tenders/new" element={<NewTenderPage />} />
        <Route path="/tenders/:tenderId" element={<TenderPage />} />
        <Route path="/company" element={<CompanyProfilePage />} />
        <Route path="/about" element={<EngineeringNotesPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
