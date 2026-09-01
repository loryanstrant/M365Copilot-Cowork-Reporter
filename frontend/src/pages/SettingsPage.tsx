import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AppConfig, TestConnection } from "../api/types";
import { Card } from "../components/Card";

export default function SettingsPage() {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [secret, setSecret] = useState("");
  const [subs, setSubs] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [test, setTest] = useState<TestConnection | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const c = await api<AppConfig>("/admin/config");
      setCfg(c);
      setSubs((c.azure_subscription_ids || []).join(", "));
    })();
  }, []);

  if (!cfg) return <div className="text-slate-500">Loading…</div>;

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const body: Record<string, unknown> = {
        tenant_id: cfg!.tenant_id,
        client_id: cfg!.client_id,
        azure_subscription_ids: subs
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        cost_rolling_window_days: cfg!.cost_rolling_window_days,
        audit_backfill_days: cfg!.audit_backfill_days,
        schedule_interval_hours: cfg!.schedule_interval_hours,
        report_access_group_id: cfg!.report_access_group_id,
      };
      if (secret) body.client_secret = secret;
      const updated = await api<AppConfig>("/admin/config", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setCfg(updated);
      setSecret("");
      setMsg("Saved.");
    } catch (e) {
      setMsg(`Error: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    setBusy(true);
    setTest(null);
    try {
      setTest(await api<TestConnection>("/admin/test-connection", { method: "POST" }));
    } finally {
      setBusy(false);
    }
  }

  async function runIngest() {
    setMsg(null);
    const r = await api<{ status: string; detail: string }>("/admin/ingest/run", {
      method: "POST",
    });
    setMsg(r.detail);
  }

  async function seedDemo() {
    setMsg(null);
    const r = await api<{ status: string; detail: string }>("/admin/seed-demo", {
      method: "POST",
    });
    setMsg(r.detail);
  }

  const field = "w-full rounded-md border border-slate-300 px-3 py-2 text-sm";
  const label = "mb-1 block text-sm text-slate-600";

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-800">Settings</h1>

      <Card title="App registration (Graph + Azure)">
        <p className="mb-4 text-xs text-slate-500">
          One app registration drives all automated collectors. Required app roles:{" "}
          <code>AuditLogsQuery.Read.All</code>, <code>User.Read.All</code>, and{" "}
          <em>Cost Management Reader</em> on each Azure subscription below.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className={label}>Tenant ID</label>
            <input
              className={field}
              value={cfg.tenant_id || ""}
              onChange={(e) => setCfg({ ...cfg, tenant_id: e.target.value })}
            />
          </div>
          <div>
            <label className={label}>Client ID</label>
            <input
              className={field}
              value={cfg.client_id || ""}
              onChange={(e) => setCfg({ ...cfg, client_id: e.target.value })}
            />
          </div>
          <div>
            <label className={label}>
              Client secret {cfg.has_client_secret && "(saved — leave blank to keep)"}
            </label>
            <input
              className={field}
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={cfg.has_client_secret ? "••••••••" : ""}
            />
          </div>
          <div>
            <label className={label}>Azure subscription IDs (comma-separated)</label>
            <input
              className={field}
              value={subs}
              onChange={(e) => setSubs(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
            />
          </div>
        </div>
      </Card>

      <Card title="Collector tuning">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className={label}>Schedule interval (hours)</label>
            <input
              type="number"
              className={field}
              value={cfg.schedule_interval_hours}
              onChange={(e) =>
                setCfg({ ...cfg, schedule_interval_hours: Number(e.target.value) })
              }
            />
          </div>
          <div>
            <label className={label}>Cost rolling window (days)</label>
            <input
              type="number"
              className={field}
              value={cfg.cost_rolling_window_days}
              onChange={(e) =>
                setCfg({ ...cfg, cost_rolling_window_days: Number(e.target.value) })
              }
            />
          </div>
          <div>
            <label className={label}>Audit backfill (days)</label>
            <input
              type="number"
              className={field}
              value={cfg.audit_backfill_days}
              onChange={(e) =>
                setCfg({ ...cfg, audit_backfill_days: Number(e.target.value) })
              }
            />
          </div>
        </div>
      </Card>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={save}
          disabled={busy}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
        >
          Save
        </button>
        <button
          onClick={runTest}
          disabled={busy}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100"
        >
          Test connection
        </button>
        <button
          onClick={runIngest}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100"
        >
          Run collectors now
        </button>
        <button
          onClick={seedDemo}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100"
        >
          Seed demo data
        </button>
      </div>

      {msg && <div className="text-sm text-slate-600">{msg}</div>}

      {test && (
        <Card title="Connection test">
          <ul className="space-y-1 text-sm">
            <Check ok={test.graph_token} label="Graph token acquired" />
            <Check ok={test.directory_read} label="Directory read (User.Read.All)" />
            <Check ok={test.audit_query} label="Purview audit query (AuditLogsQuery.Read.All)" />
            <Check ok={test.arm_token} label="Azure ARM token" />
            <Check ok={test.cost_read} label="Cost Management read" />
          </ul>
          {test.detail && (
            <div className="mt-3 rounded bg-slate-50 px-3 py-2 text-xs text-slate-600">
              {test.detail}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className={ok ? "text-green-600" : "text-slate-300"}>
        {ok ? "✓" : "○"}
      </span>
      <span className={ok ? "text-slate-700" : "text-slate-400"}>{label}</span>
    </li>
  );
}
