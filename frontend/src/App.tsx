import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { useSetupStatus } from "./hooks/useSetupStatus";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import ConsumptionPage from "./pages/ConsumptionPage";
import UsagePage from "./pages/UsagePage";
import UsersPage from "./pages/UsersPage";
import SettingsPage from "./pages/SettingsPage";
import UploadPage from "./pages/UploadPage";
import BillingPolicyPage from "./pages/BillingPolicyPage";
import HelpPage from "./pages/HelpPage";
import AboutPage from "./pages/AboutPage";

export default function App() {
  const { user, loading } = useAuth();
  const { configured, checked } = useSetupStatus(Boolean(user));

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500 dark:text-slate-400">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  const adminOnly = (el: JSX.Element) =>
    user.role === "admin" ? el : <Navigate to="/" replace />;

  // First run: send admins straight to Settings (where the wizard opens itself)
  // until a connection is configured. Non-admins carry on to the dashboards and
  // see the usual empty states.
  const needsSetup = checked && !configured && user.role === "admin";

  return (
    <Layout>
      <Routes>
        <Route
          path="/"
          element={needsSetup ? <Navigate to="/settings" replace /> : <OverviewPage />}
        />
        <Route path="/consumption" element={<ConsumptionPage />} />
        <Route path="/usage" element={<UsagePage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/settings" element={adminOnly(<SettingsPage />)} />
        <Route path="/upload" element={adminOnly(<UploadPage />)} />
        <Route path="/billing-policies" element={adminOnly(<BillingPolicyPage />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
