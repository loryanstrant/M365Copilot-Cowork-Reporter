import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Briefing, BriefingDelta } from "../api/types";
import ChartCard from "../components/ChartCard";
import Empty from "../components/Empty";
import KpiCard from "../components/KpiCard";
import { CHART_COLORS } from "../components/chartTheme";
import { fmtMoney, fmtNumber } from "../lib/format";

/**
 * The executive briefing: this period against the one before it, in sentences.
 *
 * Deliberately deterministic. Every figure is SQL and every sentence is
 * assembled here from those figures against fixed thresholds — there is no
 * model anywhere in this page. It is the screen most likely to be shown to a
 * customer or a finance team, and one invented number in that setting costs
 * more than the whole feature is worth.
 */
export default function BriefingPage() {
  const [data, setData] = useState<Briefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setData(await api<Briefing>("/metrics/briefing?days=30"));
      } catch {
        setErr("We couldn't build the briefing just now.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;
  }
  if (err) return <Empty message={err} />;
  if (!data) return null;

  const money = (n: number) => fmtMoney(n, data.currency);
  const isCost = (d: BriefingDelta) => d.label === "Azure cost";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Executive briefing</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          The last {data.window_days} days against the {data.window_days} before them.
          Every figure is measured, not estimated — nothing on this page is generated.
        </p>
      </div>

      {!data.has_data ? (
        <Empty message="There is no Cowork activity or Azure cost recorded yet. Run the collectors, or load demo data from Settings." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {data.deltas.map((d) => (
              <KpiCard
                key={d.label}
                label={d.label}
                value={isCost(d) ? money(d.current) : fmtNumber(d.current)}
                hint={deltaSentence(d, isCost(d) ? money : fmtNumber)}
              />
            ))}
          </div>

          <ChartCard
            title="What the numbers say"
            subtitle="Assembled from the figures above — no narrative is generated"
          >
            <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-200">
              {headlines(data).map((line) => (
                <li key={line} className="flex gap-2">
                  <span aria-hidden className="text-slate-400">
                    ●
                  </span>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
          </ChartCard>

          <ChartCard
            title="Licence adoption"
            subtitle={`${fmtNumber(data.active_licensed_users)} of ${fmtNumber(
              data.licensed_users,
            )} licensed people used Cowork in the period`}
          >
            <AdoptionBar
              active={data.active_licensed_users}
              total={data.licensed_users}
            />
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Leading agents" subtitle="Sessions in the period">
              <Ranked
                rows={data.top_agents.map((a) => ({
                  name: a.name,
                  value: a.value,
                  previous: a.previous,
                }))}
                colour={CHART_COLORS[0]}
                format={fmtNumber}
                empty="No named agents recorded in this period."
              />
            </ChartCard>
            <ChartCard title="Leading resource groups" subtitle="Azure cost in the period">
              <Ranked
                rows={data.top_resource_groups.map((r) => ({
                  name: r.name,
                  value: r.value,
                  previous: r.previous,
                }))}
                colour={CHART_COLORS[2]}
                format={money}
                empty="No Azure cost recorded in this period."
              />
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}

/** "up 24% on the previous 30 days", or an honest alternative. */
function deltaSentence(d: BriefingDelta, fmt: (n: number) => string): string {
  if (d.change_pct === null) {
    return d.current > 0 ? "New this period" : "Nothing recorded either period";
  }
  if (Math.abs(d.change_pct) < 1) return `Level with ${fmt(d.previous)} before`;
  const direction = d.change_pct > 0 ? "up" : "down";
  return `${direction} ${Math.abs(d.change_pct)}% on ${fmt(d.previous)}`;
}

/**
 * The prose, assembled from fixed thresholds.
 *
 * Each sentence is a direct restatement of a number that is already on the
 * page. Nothing here interprets, predicts or recommends — a briefing that
 * hedges is one a reader has to verify, which defeats the point.
 */
function headlines(d: Briefing): string[] {
  const out: string[] = [];
  const sessions = d.deltas.find((x) => x.label === "Sessions");
  const cost = d.deltas.find((x) => x.label === "Azure cost");
  const files = d.deltas.find((x) => x.label === "Files touched");

  if (sessions) {
    if (sessions.change_pct === null) {
      out.push(
        `Cowork recorded ${fmtNumber(sessions.current)} sessions, the first activity in the reporting window.`,
      );
    } else if (Math.abs(sessions.change_pct) < 5) {
      out.push(
        `Cowork use held steady at ${fmtNumber(sessions.current)} sessions, within 5% of the previous period.`,
      );
    } else {
      out.push(
        `Cowork sessions ${sessions.change_pct > 0 ? "rose" : "fell"} ${Math.abs(
          sessions.change_pct,
        )}% to ${fmtNumber(sessions.current)}.`,
      );
    }
  }

  if (d.licensed_users > 0) {
    const pct = Math.round((d.active_licensed_users / d.licensed_users) * 100);
    out.push(
      `${pct}% of licensed people used Cowork in the period — ${fmtNumber(
        d.idle_licensed_users,
      )} hold a licence they did not use.`,
    );
  }

  if (cost && cost.current > 0) {
    if (cost.change_pct === null) {
      out.push(`Azure spend was ${fmtMoney(cost.current, d.currency)} in the period.`);
    } else {
      out.push(
        `Azure spend ${cost.change_pct >= 0 ? "rose" : "fell"} ${Math.abs(
          cost.change_pct,
        )}% to ${fmtMoney(cost.current, d.currency)}.`,
      );
    }
  }

  // Only worth saying when the two moved in opposite directions: that is the
  // combination a reader would otherwise have to spot for themselves.
  if (sessions?.change_pct != null && cost?.change_pct != null) {
    if (cost.change_pct > 5 && sessions.change_pct < -5) {
      out.push("Spend rose while sessions fell, so cost per session increased.");
    } else if (cost.change_pct < -5 && sessions.change_pct > 5) {
      out.push("Sessions rose while spend fell, so cost per session decreased.");
    }
  }

  if (files && files.current > 0) {
    out.push(
      `Cowork touched ${fmtNumber(files.current)} files across ${fmtNumber(
        sessions?.current ?? 0,
      )} sessions.`,
    );
  }

  const topAgent = d.top_agents[0];
  if (topAgent?.name) {
    out.push(
      `${topAgent.name} was the most-used agent, with ${fmtNumber(
        topAgent.value,
      )} sessions.`,
    );
  }

  return out;
}

function AdoptionBar({ active, total }: { active: number; total: number }) {
  if (total === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No Copilot licences have been detected yet. Run the collectors to import them.
      </p>
    );
  }
  const pct = Math.round((active / total) * 100);
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <span className="font-semibold text-slate-800 dark:text-slate-100">{pct}% active</span>
        <span className="tabular-nums text-slate-500 dark:text-slate-400">
          {fmtNumber(total - active)} idle of {fmtNumber(total)}
        </span>
      </div>
      <div className="h-4 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700/60">
        <div
          className="h-4 rounded-full"
          style={{ width: `${Math.max(pct, 1)}%`, backgroundColor: CHART_COLORS[1] }}
        />
      </div>
    </div>
  );
}

function Ranked({
  rows,
  colour,
  format,
  empty,
}: {
  rows: { name: string | null; value: number; previous: number }[];
  colour: string;
  format: (n: number) => string;
  empty: string;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">{empty}</p>;
  }
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        // Shape plus word, never colour alone.
        const delta =
          r.previous > 0 ? Math.round(((r.value - r.previous) / r.previous) * 100) : null;
        return (
          <div key={r.name ?? "—"}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="truncate text-slate-700 dark:text-slate-200">
                {r.name ?? "—"}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {delta !== null && delta !== 0 && (
                  <span className="text-slate-400 dark:text-slate-500">
                    <span aria-hidden>{delta > 0 ? "▲" : "▼"}</span>{" "}
                    {Math.abs(delta)}%
                  </span>
                )}
                <span className="tabular-nums text-slate-500 dark:text-slate-400">
                  {format(r.value)}
                </span>
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700/60">
              <div
                className="h-3 rounded-full"
                style={{
                  width: `${Math.max((r.value / max) * 100, 2)}%`,
                  backgroundColor: colour,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
