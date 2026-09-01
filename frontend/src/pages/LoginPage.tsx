import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full w-full">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-brand-500 p-12 text-white lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, white 0, transparent 40%), radial-gradient(circle at 80% 60%, white 0, transparent 35%)",
          }}
        />
        <div className="relative flex items-center gap-3">
          <img
            src="/copilot-cowork.png"
            alt="Copilot Cowork"
            className="h-11 w-11 drop-shadow"
          />
          <span className="text-lg font-semibold">Copilot Cowork Reporter</span>
        </div>
        <div className="relative max-w-md">
          <h1 className="text-3xl font-semibold leading-tight">
            Consumption &amp; usage for Microsoft 365 Copilot Cowork
          </h1>
          <p className="mt-4 text-brand-100">
            One durable view across Azure cost, Copilot credits, adoption and Purview
            audit — no Fabric, no Power BI, no FinOps toolkit required.
          </p>
        </div>
        <div className="relative text-sm text-brand-100/80">
          Community project · MIT-licensed
        </div>
      </div>

      {/* Sign-in panel */}
      <div className="flex w-full items-center justify-center px-6 lg:w-1/2">
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <img src="/copilot-cowork.png" alt="Copilot Cowork" className="h-14 w-14" />
            <div className="mt-3 text-lg font-semibold text-brand-700">
              Copilot Cowork Reporter
            </div>
          </div>

          <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">Welcome back</h2>
          <p className="mb-6 mt-1 text-sm text-slate-500 dark:text-slate-400">
            Sign in to view your Cowork reporting.
          </p>

          {error && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <label className="mb-1.5 block text-sm font-medium text-slate-600 dark:text-slate-300">
            Username
          </label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mb-4 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-800 shadow-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            placeholder="admin"
            autoFocus
          />

          <label className="mb-1.5 block text-sm font-medium text-slate-600 dark:text-slate-300">
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-6 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-800 shadow-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            placeholder="••••••••"
          />

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <p className="mt-6 text-center text-xs text-slate-400">
            Protected by your admin password · Entra SSO optional
          </p>
        </form>
      </div>
    </div>
  );
}
