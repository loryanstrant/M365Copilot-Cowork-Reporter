import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

const NAV = [
  { to: "/", label: "Overview", end: true, admin: false },
  { to: "/consumption", label: "Consumption", admin: false },
  { to: "/usage", label: "Usage", admin: false },
  { to: "/users", label: "Tenant users", admin: false },
  { to: "/upload", label: "Upload CSV", admin: true },
  { to: "/billing-policies", label: "Chargeback", admin: true },
  { to: "/settings", label: "Settings", admin: true },
  { to: "/help", label: "Setup guide", admin: false },
  { to: "/about", label: "About", admin: false },
];

function navClass({ isActive }: { isActive: boolean }): string {
  return [
    "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-brand-600 text-white"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white",
  ].join(" ");
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const items = NAV.filter((n) => !n.admin || user?.role === "admin");

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-center gap-3 px-5 py-5">
          <img src="/app-logo.png" alt="Copilot Cowork" className="h-8 w-8 shrink-0" />
          <div>
            <div className="text-sm font-semibold text-brand-600 dark:text-brand-500">
              M365 Copilot
            </div>
            <div className="text-lg font-bold leading-tight text-slate-900 dark:text-white">
              Cowork Reporter
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={navClass}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-3 border-t border-slate-200 px-4 py-4 text-sm dark:border-slate-700">
          <button
            onClick={toggle}
            className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            <span>{theme === "dark" ? "Dark" : "Light"} mode</span>
            <span aria-hidden>{theme === "dark" ? "🌙" : "☀️"}</span>
          </button>
          <div>
            <div className="font-medium text-slate-800 dark:text-slate-100">
              {user?.username}
            </div>
            <div className="mb-3 text-xs uppercase tracking-wide text-slate-400">
              {user?.role}
            </div>
            <button
              onClick={logout}
              className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-[1600px] px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
