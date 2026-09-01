import type { ReactNode } from "react";

export function Card({
  title,
  children,
  right,
}: {
  title?: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      {(title || right) && (
        <div className="mb-4 flex items-center justify-between">
          {title && <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-800 dark:text-slate-100">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">{hint}</div>}
    </div>
  );
}

export function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
      {message}
    </div>
  );
}
