import { Card } from "../components/Card";

export default function AboutPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-800">About</h1>

      <Card title="What this reports">
        <p className="text-sm text-slate-600">
          Microsoft 365 Copilot Cowork has no single reporting API. This app is a{" "}
          <strong>collector</strong> that joins the available sources into one durable
          store and presents <strong>Consumption</strong> and <strong>Usage</strong> as
          separate views (joined on user, never blended — dollars vs task counts).
        </p>
      </Card>

      <Card title="Data sources">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2">Signal</th>
              <th>Source</th>
              <th>Mode</th>
            </tr>
          </thead>
          <tbody className="text-slate-600">
            <Row s="Azure spend by resource group" src="Cost Management Query API" mode="Automated" auto />
            <Row s="Cowork events / resources touched" src="Purview audit (CopilotInteraction)" mode="Automated" auto />
            <Row s="Org context (dept, cost centre)" src="Microsoft Graph users" mode="Automated" auto />
            <Row s="Cowork tasks / adoption" src="Admin centre Cowork usage report" mode="CSV upload" />
            <Row s="Copilot credit consumption" src="Admin centre Cost Management" mode="CSV upload" />
          </tbody>
        </table>
        <p className="mt-4 text-xs text-slate-500">
          The two CSV sources have no Microsoft API. If Microsoft ships one later, the
          collector gains a loader and nothing downstream changes.
        </p>
      </Card>

      <Card title="Cowork identification (Purview audit)">
        <p className="text-sm text-slate-600">
          A <code>CopilotInteraction</code> record is treated as Cowork when
          <code className="mx-1">CopilotEventData.AppHost == "cowork"</code> or
          <code className="mx-1">AppIdentity == "Copilot.M365Copilot.CoworkChat"</code>.
          Audit answers <em>who / when / what-touched</em> — not task volume (use Usage)
          or cost (use Consumption). Prompt text is never stored.
        </p>
      </Card>

      <div className="text-xs text-slate-400">
        MIT-licensed. Community project — no Microsoft support agreement or SLA. The
        admin-centre CSV exports are the supported extraction path; no unsupported
        internal APIs are called.
      </div>
    </div>
  );
}

function Row({
  s,
  src,
  mode,
  auto,
}: {
  s: string;
  src: string;
  mode: string;
  auto?: boolean;
}) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2">{s}</td>
      <td>{src}</td>
      <td>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${
            auto ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
          }`}
        >
          {mode}
        </span>
      </td>
    </tr>
  );
}
