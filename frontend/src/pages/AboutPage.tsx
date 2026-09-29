import { useEffect, useState } from "react";
import { api } from "../api/client";
import ChartCard from "../components/ChartCard";
import { fmtDate } from "../lib/format";
import KpiCard from "../components/KpiCard";
import SuiteBlock from "../components/SuiteBlock";
import { buildStamp } from "../lib/buildStamp";

interface AboutMeta {
  version: string;
  build_date: string | null;
  build_time: string | null;
}

interface Freshness {
  cowork_events: number;
  cowork_usage_rows: number;
  daily_cost_rows: number;
  directory_users: number;
  earliest_event: string | null;
  latest_event: string | null;
  earliest_cost: string | null;
  latest_cost: string | null;
  last_run: { status: string; started_at: string | null; finished_at: string | null } | null;
}

// Defers to the shared formatter, which spells the month. An all-numeric date
// on a page whose whole job is telling you how fresh the data is would be an
// odd place to leave 7/16/2026 open to interpretation.
function fmtDay(value: string | null): string {
  return fmtDate(value);
}

function fmtDateTime(value: string | null): string {
  if (!value) return "—";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleString();
}

export default function AboutPage() {
  const [meta, setMeta] = useState<AboutMeta | null>(null);
  const [fresh, setFresh] = useState<Freshness | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setMeta(await api<AboutMeta>("/metrics/about"));
      } catch {
        /* ignore */
      }
      try {
        setFresh(await api<Freshness>("/metrics/freshness"));
      } catch {
        /* ignore */
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">About</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          What this tool does, how fresh the data is, and how the numbers are calculated.
        </p>
      </div>

      <ChartCard title="What this is">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Microsoft 365 Copilot Cowork has no single reporting API. This app is a{" "}
          <strong>collector</strong> that joins the available sources into one durable
          store and presents <strong>Consumption</strong> and <strong>Usage</strong> as
          separate views (joined on user, never blended — dollars vs task counts).
        </p>
        {meta && (
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
            Version{" "}
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {meta.version}
            </span>{" "}
            · {buildStamp(meta.build_date, meta.build_time)}
          </p>
        )}
      </ChartCard>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Cowork events"
          value={String(fresh?.cowork_events ?? "—")}
          hint="Purview audit rows collected"
        />
        <KpiCard
          label="Usage rows"
          value={String(fresh?.cowork_usage_rows ?? "—")}
          hint="From uploaded admin-centre CSVs"
        />
        <KpiCard
          label="Cost rows"
          value={String(fresh?.daily_cost_rows ?? "—")}
          hint="Daily Azure spend by resource group"
        />
        <KpiCard
          label="Directory users"
          value={String(fresh?.directory_users ?? "—")}
          hint="Imported from Microsoft Graph"
        />
      </div>

      <ChartCard title="Data freshness">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <Row label="Earliest audit event" value={fmtDay(fresh?.earliest_event ?? null)} />
          <Row label="Most recent audit event" value={fmtDay(fresh?.latest_event ?? null)} />
          <Row label="Earliest cost date" value={fmtDay(fresh?.earliest_cost ?? null)} />
          <Row label="Most recent cost date" value={fmtDay(fresh?.latest_cost ?? null)} />
          <Row
            label="Last run"
            value={fresh?.last_run ? fmtDateTime(fresh.last_run.finished_at) : "—"}
          />
          <Row label="Run status" value={fresh?.last_run?.status ?? "No run yet"} />
        </dl>
      </ChartCard>

      <ChartCard title="Data sources">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-700 dark:text-slate-400">
              <th className="py-2">Signal</th>
              <th>Source</th>
              <th>Mode</th>
            </tr>
          </thead>
          <tbody className="text-slate-600 dark:text-slate-300">
            <SourceRow s="Azure spend by resource group" src="Cost Management Query API" mode="Automated" auto />
            <SourceRow s="Cowork events / resources touched" src="Purview audit (CopilotInteraction)" mode="Automated" auto />
            <SourceRow s="Org context (dept, cost centre)" src="Microsoft Graph users" mode="Automated" auto />
            <SourceRow s="Cowork tasks / adoption" src="Admin centre Cowork usage report" mode="CSV upload" />
            <SourceRow s="Copilot credit consumption" src="Admin centre Cost Management" mode="CSV upload" />
          </tbody>
        </table>
        <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
          The two CSV sources have no Microsoft API. If Microsoft ships one later, the
          collector gains a loader and nothing downstream changes.
        </p>
      </ChartCard>

      <ChartCard title="Methodology">
        <ul className="list-inside list-disc space-y-2 text-sm text-slate-600 dark:text-slate-300">
          <li>
            <span className="font-medium">Consumption</span> is Azure spend plus Copilot
            credit consumption. <span className="font-medium">Usage</span> is task counts
            and adoption. The two are joined on user, never summed together.
          </li>
          <li>
            A <code>CopilotInteraction</code> record counts as Cowork when
            <code className="mx-1">CopilotEventData.AppHost == "cowork"</code> or
            <code className="mx-1">AppIdentity == "Copilot.M365Copilot.CoworkChat"</code>.
          </li>
          <li>
            Audit answers <em>who / when / what-touched</em> — not task volume (use Usage)
            or cost (use Consumption). <strong>Prompt text is never stored.</strong>
          </li>
          <li>
            Cost restates as charges settle, so the collector re-pulls and replaces a
            rolling window rather than trusting the first figure it sees.
          </li>
        </ul>
      </ChartCard>

      <SuiteBlock />

      <div className="card p-5">
        <div className="flex items-center gap-4">
          <img
            src="/loryan-cyborg.png"
            alt="Loryan Strant"
            className="h-16 w-16 rounded-full object-cover"
          />
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Created by
            </div>
            <a
              href="https://www.loryanstrant.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-lg font-semibold text-brand-600 hover:underline dark:text-brand-400"
            >
              Loryan Strant
            </a>
            <div className="mt-1">
              <a
                href="https://github.com/loryanstrant/M365Copilot-Cowork-Reporter"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600 hover:underline dark:text-slate-400 dark:hover:text-brand-400"
              >
                <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-current">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
                </svg>
                View on GitHub
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="text-xs text-slate-400 dark:text-slate-500">
        MIT-licensed. Community project — no Microsoft support agreement or SLA. The
        admin-centre CSV exports are the supported extraction path; no unsupported
        internal APIs are called.
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-2 dark:border-slate-700">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  );
}

function SourceRow({
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
    <tr className="border-b border-slate-100 dark:border-slate-800">
      <td className="py-2">{s}</td>
      <td>{src}</td>
      <td>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${
            auto
              ? "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400"
              : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
          }`}
        >
          {mode}
        </span>
      </td>
    </tr>
  );
}
