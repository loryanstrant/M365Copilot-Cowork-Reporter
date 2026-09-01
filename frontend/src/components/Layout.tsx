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

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const items = NAV.filter((n) => !n.admin || user?.role === "admin");

  return (
    <div className="flex h-full">
      <aside className="flex w-60 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <img src="/copilot-cowork.png" alt="Copilot Cowork" className="h-8 w-8" />
          <div>
            <div className="text-sm font-semibold text-brand-700 dark:text-brand-400">
              Copilot Cowork
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              Consumption &amp; Usage
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${
                  isActive
                    ? "bg-brand-50 font-medium text-brand-700 dark:bg-brand-500/10 dark:text-brand-400"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 px-5 py-4 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
          <button
            onClick={toggle}
            className="mb-3 flex w-full items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <span>{theme === "dark" ? "Dark mode" : "Light mode"}</span>
            <span aria-hidden>{theme === "dark" ? "🌙" : "☀️"}</span>
          </button>
          <div className="mb-1 truncate text-slate-600 dark:text-slate-300">
            {user?.username}
          </div>
          <div className="mb-2 uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {user?.role}
          </div>
          <button
            onClick={logout}
            className="text-brand-600 hover:underline dark:text-brand-400"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
