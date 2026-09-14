import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BillingPolicy } from "../api/types";
import { Card, Empty } from "../components/Card";

const EMPTY: BillingPolicy = {
  resource_group: "",
  billing_policy_name: "",
  cost_centre: "",
  business_owner: "",
  project: "",
  notes: "",
};

export default function BillingPolicyPage() {
  const [rows, setRows] = useState<BillingPolicy[]>([]);
  const [draft, setDraft] = useState<BillingPolicy>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    setRows(await api<BillingPolicy[]>("/admin/billing-policies"));
  }
  useEffect(() => {
    load();
  }, []);

  async function save() {
    if (!draft.resource_group.trim()) return;
    await api("/admin/billing-policies", {
      method: "PUT",
      body: JSON.stringify(draft),
    });
    setDraft(EMPTY);
    setMsg("Saved.");
    await load();
  }

  async function edit(r: BillingPolicy) {
    setDraft(r);
  }

  async function remove(rg: string) {
    await api(`/admin/billing-policies/${encodeURIComponent(rg)}`, { method: "DELETE" });
    await load();
  }

  const field = "input";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Chargeback mapping</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Map each Azure resource group (= billing policy) to a cost centre and owner.
          This is the chargeback layer Microsoft's tooling doesn't provide — it turns the
          cost view into a per-business-unit view.
        </p>
      </div>

      <Card title={draft.resource_group ? `Edit: ${draft.resource_group}` : "Add mapping"}>
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Resource group</label>
            <input
              className={field}
              value={draft.resource_group}
              onChange={(e) => setDraft({ ...draft, resource_group: e.target.value })}
              placeholder="rg-copilot-cowork-prod"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Billing policy name</label>
            <input
              className={field}
              value={draft.billing_policy_name || ""}
              onChange={(e) => setDraft({ ...draft, billing_policy_name: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Cost centre</label>
            <input
              className={field}
              value={draft.cost_centre || ""}
              onChange={(e) => setDraft({ ...draft, cost_centre: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Business owner</label>
            <input
              className={field}
              value={draft.business_owner || ""}
              onChange={(e) => setDraft({ ...draft, business_owner: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Project</label>
            <input
              className={field}
              value={draft.project || ""}
              onChange={(e) => setDraft({ ...draft, project: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Notes</label>
            <input
              className={field}
              value={draft.notes || ""}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </div>
        </div>
        <div className="mt-4 flex gap-3">
          <button onClick={save} className="btn-primary">
            {draft.resource_group && rows.find((r) => r.resource_group === draft.resource_group)
              ? "Update"
              : "Add"}
          </button>
          {draft.resource_group && (
            <button onClick={() => setDraft(EMPTY)} className="btn-secondary">
              Clear
            </button>
          )}
        </div>
        {msg && <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">{msg}</div>}
      </Card>

      <Card title="Mappings">
        {rows.length === 0 ? (
          <Empty message="No mappings yet." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500 dark:text-slate-400 dark:border-slate-700">
                <th className="py-2">Resource group</th>
                <th>Policy</th>
                <th>Cost centre</th>
                <th>Owner</th>
                <th>Project</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.resource_group} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono text-xs">{r.resource_group}</td>
                  <td>{r.billing_policy_name || "—"}</td>
                  <td>{r.cost_centre || "—"}</td>
                  <td>{r.business_owner || "—"}</td>
                  <td>{r.project || "—"}</td>
                  <td className="text-right">
                    <button
                      onClick={() => edit(r)}
                      className="mr-3 text-brand-600 hover:underline dark:text-brand-400"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => remove(r.resource_group)}
                      className="text-red-500 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
