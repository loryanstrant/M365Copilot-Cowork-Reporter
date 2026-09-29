import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { useSetupStatus } from "./hooks/useSetupStatus";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import BriefingPage from "./pages/BriefingPage";
import PersonalPage from "./pages/PersonalPage";
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

  // Anyone signed in with a work account lands on their own data. The password
  // admin has no Entra identity, so there is no "me" to show them — they go
  // straight to the organisation view.
  const landing = needsSetup ? (
    <Navigate to="/settings" replace />
  ) : user.has_personal_view ? (
    <PersonalPage />
  ) : (
    <OverviewPage />
  );

  // Organisation pages are gated. The API enforces this too — this only keeps
  // someone from landing on a page that would just error.
  const org = (el: JSX.Element) =>
    user.can_view_org ? el : <Navigate to="/" replace />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={landing} />
        <Route path="/me" element={<PersonalPage />} />
        <Route path="/overview" element={org(<OverviewPage />)} />
        <Route path="/briefing" element={org(<BriefingPage />)} />
        <Route path="/consumption" element={org(<ConsumptionPage />)} />
        <Route path="/usage" element={org(<UsagePage />)} />
        <Route path="/users" element={org(<UsersPage />)} />
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
