import { Card } from "../components/Card";

export default function HelpPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Setup &amp; data guide</h1>
        <p className="text-sm text-slate-500">
          How to connect the automated sources and export the two admin-centre CSVs.
        </p>
      </div>

      <Card title="1. App registration (automated collectors)">
        <p className="mb-3 text-sm text-slate-600">
          One Entra app registration powers all three automated collectors: Purview
          audit (Cowork events), directory users, and Azure cost.
        </p>
        <ol className="ml-5 list-decimal space-y-2 text-sm text-slate-600">
          <li>
            In <strong>Entra admin centre → App registrations → New registration</strong>,
            create an app (single tenant is fine). Copy the{" "}
            <strong>Directory (tenant) ID</strong> and{" "}
            <strong>Application (client) ID</strong>.
          </li>
          <li>
            Under <strong>Certificates &amp; secrets</strong>, create a{" "}
            <strong>client secret</strong> and copy its value immediately.
          </li>
          <li>
            Under <strong>API permissions → Add a permission → Microsoft Graph →
            Application permissions</strong>, add{" "}
            <code>AuditLogsQuery.Read.All</code> and <code>User.Read.All</code>, then
            click <strong>Grant admin consent</strong>.
          </li>
          <li>
            Paste tenant ID, client ID and secret into the{" "}
            <strong>Settings</strong> page and click <strong>Test connection</strong>.
          </li>
        </ol>
        <div className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Microsoft began enforcing <code>AuditLogsQuery.Read.All</code> in April 2026.
          The legacy <code>AuditLog.Read.All</code> silently returns zero Copilot records
          — make sure you grant the <em>Query</em> permission above.
        </div>
      </Card>

      <Card title="2. Azure Cost Management (spend by resource group)">
        <p className="mb-3 text-sm text-slate-600">
          Copilot pay-as-you-go spend lands on Azure resource groups (one per billing
          policy). This connects to the Cost Management Query API to pull daily cost.
        </p>
        <ol className="ml-5 list-decimal space-y-2 text-sm text-slate-600">
          <li>
            In the <strong>Azure portal → Subscriptions</strong>, open each subscription
            that holds a Copilot billing-policy resource group and copy its{" "}
            <strong>Subscription ID</strong>.
          </li>
          <li>
            On each subscription, go to{" "}
            <strong>Access control (IAM) → Add role assignment</strong> and grant{" "}
            <strong>Cost Management Reader</strong> to the app registration from step 1
            (search for it by name under “User, group, or service principal”).
          </li>
          <li>
            Paste the subscription IDs (comma-separated) into <strong>Settings →
            Azure subscription IDs</strong>, save, and <strong>Test connection</strong>{" "}
            — the “Cost Management read” check should go green.
          </li>
          <li>
            On the <strong>Chargeback</strong> page, map each resource group to a cost
            centre / owner so spend rolls up per business unit.
          </li>
        </ol>
        <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
          Cost data restates as charges settle, so the collector re-pulls and replaces a
          trailing window (default 10 days) each run — figures for the current period keep
          moving until the invoice closes. “Near-real-time” means yesterday’s costs by
          mid-morning, not live spend.
        </div>
      </Card>

      <Card title="3. Cowork usage report CSV (tasks &amp; adoption)">
        <p className="mb-3 text-sm text-slate-600">
          There is no API for Cowork task metrics — export the CSV and upload it on the{" "}
          <strong>Upload CSV</strong> page.
        </p>
        <ol className="ml-5 list-decimal space-y-2 text-sm text-slate-600">
          <li>
            Go to the <strong>Microsoft 365 admin centre</strong> (
            <code>admin.cloud.microsoft</code>).
          </li>
          <li>
            Open <strong>Copilot → Cowork → Usage</strong> tab (data is available from
            1 April 2026; default window is 28 days — widen it if you want more).
          </li>
          <li>
            Click <strong>Export</strong> to download the CSV. It contains User Principal
            Name, Display Name, Total/Scheduled/User-initiated Tasks, Active Days and Last
            Activity Date.
          </li>
          <li>
            On <strong>Upload CSV → Cowork usage report</strong>, choose the file, set the
            report period (7/28/90/180) matching the window you exported, and upload.
          </li>
        </ol>
      </Card>

      <Card title="4. Copilot Credits / Cost Management CSV (credit consumption)">
        <p className="mb-3 text-sm text-slate-600">
          Credit consumption also has no API — export it and upload on the{" "}
          <strong>Upload CSV</strong> page.
        </p>
        <ol className="ml-5 list-decimal space-y-2 text-sm text-slate-600">
          <li>
            In the <strong>Microsoft 365 admin centre</strong>, open{" "}
            <strong>Copilot → Cost Management</strong> (the Cowork &amp; Work IQ credit
            billing dashboard), or <strong>Reports → Usage → Microsoft Copilot →
            Credits</strong>.
          </li>
          <li>
            Choose the <strong>Consumption</strong> tab and the scope you want — by user,
            by service (includes a “Cowork” row), or by group.
          </li>
          <li>
            Click <strong>Export CSV</strong>.
          </li>
          <li>
            On <strong>Upload CSV → Copilot Credits / Cost Management</strong>, pick the
            matching <strong>Export scope</strong> and upload. Re-uploading a fresher
            export just updates the figures.
          </li>
        </ol>
        <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
          Tip: if the cost-centre / business-unit columns are blank, those aren’t standard
          Entra fields — an admin must populate department / a custom attribute for the
          org rollups to show.
        </div>
      </Card>

      <Card title="Privacy framing">
        <p className="text-sm text-slate-600">
          Present per-user figures as <strong>adoption and enablement</strong> (where is
          training needed, which teams haven’t started), not individual performance. If
          the tenant’s “Conceal user, group, and site names in all reports” setting is on,
          exported UPNs are hashed — decide that tenant-wide before relying on user-level
          detail.
        </p>
      </Card>
    </div>
  );
}
