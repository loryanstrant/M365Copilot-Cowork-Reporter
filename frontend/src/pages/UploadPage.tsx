import { useState } from "react";
import { upload } from "../api/client";
import type { UploadResult } from "../api/types";
import { Card } from "../components/Card";

export default function UploadPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Upload admin CSVs</h1>
        <p className="text-sm text-slate-500">
          Microsoft ships no API for Cowork task metrics or Copilot Credit consumption.
          Export them from the M365 admin centre and upload here — re-uploading a fresher
          export just updates the rows.
        </p>
      </div>

      <UploadCard
        title="Cowork usage report"
        description="M365 admin centre → Copilot → Cowork → Usage → Export CSV. Columns: User Principal Name, Display Name, Total/Scheduled/User-initiated Tasks, Active Days, Last Activity Date."
        endpoint="/admin/upload/cowork-usage"
        extraFields={[
          { name: "report_period", label: "Report period (days: 7/28/90/180)", type: "number" },
          { name: "report_refresh_date", label: "Report refresh date (optional)", type: "date" },
        ]}
      />

      <UploadCard
        title="Copilot Credits / Cost Management"
        description="M365 admin centre → Copilot → Cost Management (or Reports → Credits) → Export CSV. Attributes credits to users, services (incl. Cowork), or groups."
        endpoint="/admin/upload/credit-consumption"
        extraFields={[
          {
            name: "scope_type",
            label: "Export scope",
            type: "select",
            options: ["user", "service", "group", "summary"],
          },
          { name: "as_of_date", label: "As-of date (optional)", type: "date" },
        ]}
      />
    </div>
  );
}

interface FieldDef {
  name: string;
  label: string;
  type: "number" | "date" | "select";
  options?: string[];
}

function UploadCard({
  title,
  description,
  endpoint,
  extraFields,
}: {
  title: string;
  description: string;
  endpoint: string;
  extraFields: FieldDef[];
}) {
  const [file, setFile] = useState<File | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<UploadResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      for (const [k, v] of Object.entries(values)) if (v) form.append(k, v);
      setResult(await upload<UploadResult>(endpoint, form));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded-md border border-slate-300 px-3 py-2 text-sm";

  return (
    <Card title={title}>
      <p className="mb-4 text-xs text-slate-500">{description}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm text-slate-600">CSV file</label>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm"
          />
        </div>
        {extraFields.map((f) => (
          <div key={f.name}>
            <label className="mb-1 block text-sm text-slate-600">{f.label}</label>
            {f.type === "select" ? (
              <select
                className={field}
                value={values[f.name] || f.options?.[0] || ""}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
              >
                {f.options?.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={f.type}
                className={field}
                value={values[f.name] || ""}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
              />
            )}
          </div>
        ))}
      </div>
      <button
        onClick={submit}
        disabled={!file || busy}
        className="mt-4 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
      >
        {busy ? "Uploading…" : "Upload"}
      </button>
      {result && (
        <div className="mt-3 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
          Imported {result.imported} of {result.rows} rows ({result.skipped} skipped).
        </div>
      )}
      {err && (
        <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>
      )}
    </Card>
  );
}
