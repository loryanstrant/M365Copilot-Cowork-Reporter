import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

// Sidebar sections: "You" is the personal view, "Organisation" is everything
// tenant-wide and only appears for people allowed to see it.
const PERSONAL_NAV = [{ to: "/me", label: "Your activity" }];

const ORG_NAV = [
  { to: "/overview", label: "Overview" },
  { to: "/consumption", label: "Consumption" },
  { to: "/usage", label: "Usage" },
  { to: "/users", label: "Tenant users" },
];

const ADMIN_NAV = [
  { to: "/upload", label: "Upload CSV" },
  { to: "/billing-policies", label: "Chargeback" },
  { to: "/settings", label: "Settings" },
];

const HELP_NAV = [
  { to: "/help", label: "Setup guide" },
  { to: "/about", label: "About" },
];

function navClass({ isActive }: { isActive: boolean }): string {
  return [
    "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-brand-600 text-white"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white",
  ].join(" ");
}

/** Groups the sidebar into "You" and "Organisation" so the split is obvious. */
function NavSectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
      {children}
    </div>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();

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
          {user?.has_personal_view && (
            <>
              <NavSectionLabel>You</NavSectionLabel>
              {PERSONAL_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} className={navClass}>
                  {n.label}
                </NavLink>
              ))}
            </>
          )}

          {user?.can_view_org && (
            <>
              <NavSectionLabel>Organisation</NavSectionLabel>
              {ORG_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} className={navClass}>
                  {n.label}
                </NavLink>
              ))}
            </>
          )}

          {user?.role === "admin" && (
            <>
              <NavSectionLabel>Administration</NavSectionLabel>
              {ADMIN_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} className={navClass}>
                  {n.label}
                </NavLink>
              ))}
            </>
          )}

          <NavSectionLabel>Help</NavSectionLabel>
          {HELP_NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={navClass}>
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
