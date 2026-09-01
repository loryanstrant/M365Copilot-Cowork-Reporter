import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import ConsumptionPage from "./pages/ConsumptionPage";
import UsagePage from "./pages/UsagePage";
import SettingsPage from "./pages/SettingsPage";
import UploadPage from "./pages/UploadPage";
import BillingPolicyPage from "./pages/BillingPolicyPage";
import HelpPage from "./pages/HelpPage";
import AboutPage from "./pages/AboutPage";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  const adminOnly = (el: JSX.Element) =>
    user.role === "admin" ? el : <Navigate to="/" replace />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/consumption" element={<ConsumptionPage />} />
        <Route path="/usage" element={<UsagePage />} />
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
