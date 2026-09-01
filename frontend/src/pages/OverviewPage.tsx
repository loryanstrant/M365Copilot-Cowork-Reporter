import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Kpis, Status } from "../api/types";
import { Card, Kpi, Empty } from "../components/Card";
import { fmtMoney, fmtNumber, fmtDate } from "../lib/format";

export default function OverviewPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setKpis(await api<Kpis>("/metrics/kpis?days=30"));
      } catch (e) {
        setErr(String(e));
      }
      try {
        setStatus(await api<Status>("/admin/status"));
      } catch {
        /* viewer role has no admin/status; ignore */
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Overview</h1>
        <p className="text-sm text-slate-500">
          Cowork consumption and usage across the tenant (last 30 days).
        </p>
      </div>

      {err && <Empty message={`Could not load metrics: ${err}`} />}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <Kpi
          label="Azure cost (30d)"
          value={kpis ? fmtMoney(kpis.total_cost, kpis.currency) : "—"}
          hint="Cost Management (automated)"
        />
        <Kpi
          label="Credits consumed"
          value={kpis ? fmtNumber(kpis.total_credits) : "—"}
          hint="Latest admin CSV snapshot"
        />
        <Kpi
          label="Cowork tasks"
          value={kpis ? fmtNumber(kpis.total_tasks) : "—"}
          hint="Latest usage snapshot"
        />
        <Kpi
          label="Active Cowork users"
          value={kpis ? fmtNumber(kpis.active_users) : "—"}
        />
        <Kpi
          label="Audit events"
          value={kpis ? fmtNumber(kpis.cowork_events) : "—"}
          hint="Purview CopilotInteraction (Cowork)"
        />
      </div>

      {status && (
        <Card title="Data sources">
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-3">
            <SourceRow label="Azure cost rows" value={status.daily_cost_rows} auto />
            <SourceRow label="Audit events" value={status.cowork_events} auto />
            <SourceRow label="Directory users" value={status.directory_users} auto />
            <SourceRow label="Cowork usage rows (CSV)" value={status.cowork_usage_rows} />
            <SourceRow label="Credit rows (CSV)" value={status.credit_rows} />
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
            {status.last_run
              ? `Last collector run: ${status.last_run.status} at ${fmtDate(
                  status.last_run.finished_at || status.last_run.started_at,
                )}`
              : "No collector run yet."}
            {!status.configured && (
              <span className="ml-2 text-amber-600">
                Credentials not configured — see Settings.
              </span>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

function SourceRow({
  label,
  value,
  auto,
}: {
  label: string;
  value: number;
  auto?: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2">
      <span className="text-slate-600">
        {label}
        <span
          className={`ml-2 rounded px-1.5 py-0.5 text-[10px] uppercase ${
            auto ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
          }`}
        >
          {auto ? "auto" : "csv"}
        </span>
      </span>
      <span className="font-medium text-slate-800">{fmtNumber(value)}</span>
    </div>
  );
}
