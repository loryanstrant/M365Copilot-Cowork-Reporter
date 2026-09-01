import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/", label: "Overview", end: true, admin: false },
  { to: "/consumption", label: "Consumption", admin: false },
  { to: "/usage", label: "Usage", admin: false },
  { to: "/upload", label: "Upload CSV", admin: true },
  { to: "/billing-policies", label: "Chargeback", admin: true },
  { to: "/settings", label: "Settings", admin: true },
  { to: "/about", label: "About", admin: false },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const items = NAV.filter((n) => !n.admin || user?.role === "admin");

  return (
    <div className="flex h-full">
      <aside className="flex w-60 flex-col border-r border-slate-200 bg-white">
        <div className="px-5 py-5">
          <div className="text-sm font-semibold text-brand-700">Copilot Cowork</div>
          <div className="text-xs text-slate-500">Consumption &amp; Usage</div>
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
                    ? "bg-brand-50 font-medium text-brand-700"
                    : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 px-5 py-4 text-xs text-slate-500">
          <div className="mb-1 truncate">{user?.username}</div>
          <div className="mb-2 uppercase tracking-wide text-slate-400">{user?.role}</div>
          <button
            onClick={logout}
            className="text-brand-600 hover:underline"
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
