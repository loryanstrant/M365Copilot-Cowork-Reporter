import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type {
  MyActivity,
  MyDay,
  MyEvent,
  MyStanding,
  MyTopItem,
  PeerStat,
} from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import Empty from "../components/Empty";
import KpiCard from "../components/KpiCard";
import { CHART_COLORS, barGradId } from "../components/chartTheme";
import { fmtDate, fmtDayShort, fmtNumber } from "../lib/format";

const DAYS = 30;

/**
 * "Your activity": the landing page for anyone signed in with a work account.
 *
 * It leads with aggregates and charts rather than a list of rows. The session
 * table is still here, at the bottom and collapsed, because it is genuinely
 * useful when you want to check one specific interaction — but it answers
 * "what did I do at 11:04 on Tuesday", which is not the question anyone opens
 * this page with.
 *
 * Every figure comes from fact_cowork_event.created_at. fact_cowork_usage is a
 * snapshot per rolling report window rather than a daily series, so it cannot
 * back a per-day chart at all.
 */
export default function PersonalPage() {
  const { user } = useAuth();
  const [activity, setActivity] = useState<MyActivity | null>(null);
  const [daily, setDaily] = useState<MyDay[]>([]);
  const [standing, setStanding] = useState<MyStanding | null>(null);
  const [agents, setAgents] = useState<MyTopItem[]>([]);
  const [tools, setTools] = useState<MyTopItem[]>([]);
  const [events, setEvents] = useState<MyEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [a, d, s, ag, tl, ev] = await Promise.all([
          api<MyActivity>(`/metrics/me/activity?days=${DAYS}`),
          api<MyDay[]>(`/metrics/me/daily?days=${DAYS}`),
          api<MyStanding>(`/metrics/me/standing?days=${DAYS}`),
          api<MyTopItem[]>(`/metrics/me/top-agents?days=${DAYS}`),
          api<MyTopItem[]>(`/metrics/me/top-tools?days=${DAYS}`),
          api<MyEvent[]>("/metrics/me/events?limit=25"),
        ]);
        if (!active) return;
        setActivity(a);
        setDaily(d);
        setStanding(s);
        setAgents(ag);
        setTools(tl);
        setEvents(ev);
      } catch {
        if (active) setErr("We couldn't load your activity just now.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;
  }

  const hasData = Boolean(activity?.has_data);
  const perDay = (n: number) =>
    activity && activity.active_days > 0 ? (n / activity.active_days).toFixed(1) : "0";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Your Cowork activity</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          How you've been using Copilot Cowork over the last {DAYS} days. Only you and
          your administrators can see this.
        </p>
      </div>

      <OrgViewBanner canViewOrg={user?.can_view_org ?? false} />

      {err && <Empty message={err} />}

      {!hasData && !err ? (
        <ChartCard title="Your activity">
          <div className="py-10 text-center">
            <h2 className="mb-2 text-lg font-semibold text-slate-800 dark:text-slate-100">
              Nothing to show yet
            </h2>
            <p className="mx-auto max-w-md text-sm text-slate-500 dark:text-slate-400">
              We can't find any Cowork activity for your account in the last {DAYS}{" "}
              days. That usually means you haven't used Cowork since reporting started,
              or the collectors haven't run yet.
            </p>
          </div>
        </ChartCard>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard
              label="Sessions"
              value={fmtNumber(activity?.sessions ?? 0)}
              hint={
                activity?.last_activity_date
                  ? `Last active ${fmtDate(activity.last_activity_date)}`
                  : "No recorded sessions"
              }
            />
            <KpiCard
              label="Avg tools per day"
              value={perDay(activity?.tools ?? 0)}
              hint={`${fmtNumber(activity?.tools ?? 0)} tool calls over ${
                activity?.active_days ?? 0
              } active days`}
            />
            <KpiCard
              label="Avg files per day"
              value={perDay(activity?.files ?? 0)}
              hint={`${fmtNumber(activity?.files ?? 0)} files touched over ${
                activity?.active_days ?? 0
              } active days`}
            />
            <KpiCard
              label="Active days"
              value={fmtNumber(activity?.active_days ?? 0)}
              hint={`of the last ${DAYS} days`}
            />
          </div>

          <ChartCard
            title="Your sessions per day"
            subtitle={`Cowork audit events, last ${DAYS} days`}
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  className="stroke-slate-200 dark:stroke-slate-700"
                />
                <XAxis
                  dataKey="day"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(d: string) => fmtDayShort(d)}
                  minTickGap={28}
                />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(59,110,245,0.06)" }}
                  content={<ChartTooltip />}
                />
                <Bar
                  dataKey="sessions"
                  name="Sessions"
                  fill={`url(#${barGradId(0)})`}
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {standing && <Standing standing={standing} />}

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard
              title="Your top agents"
              subtitle={`Sessions by agent, last ${DAYS} days`}
            >
              <RankedBars rows={agents} colour={CHART_COLORS[0]} empty="No agents recorded yet." />
            </ChartCard>
            <ChartCard
              title="Your top tools"
              subtitle={`Tool calls, last ${DAYS} days`}
            >
              <RankedBars rows={tools} colour={CHART_COLORS[3]} empty="No tool calls recorded yet." />
            </ChartCard>
          </div>

          <details className="card p-5">
            <summary className="cursor-pointer text-sm font-semibold text-slate-700 dark:text-slate-200">
              Your recent Cowork sessions
              <span className="ml-2 font-normal text-slate-400 dark:text-slate-500">
                {events.length} most recent
              </span>
            </summary>
            {events.length === 0 ? (
              <div className="mt-4">
                <Empty message="No audit events recorded for your account yet." />
              </div>
            ) : (
              <table className="mt-4 w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left dark:border-slate-700">
                    <th className="px-3 py-2 font-medium text-slate-500 dark:text-slate-400">
                      When
                    </th>
                    <th className="px-3 py-2 font-medium text-slate-500 dark:text-slate-400">
                      Agent
                    </th>
                    <th className="px-3 py-2 text-right font-medium text-slate-500 dark:text-slate-400">
                      Tools
                    </th>
                    <th className="px-3 py-2 text-right font-medium text-slate-500 dark:text-slate-400">
                      Files touched
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr
                      key={e.event_id}
                      className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                    >
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                        {fmtDate(e.created_at)}
                      </td>
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                        {e.agent_name || e.app_host || "Cowork"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-800 dark:text-slate-100">
                        {e.tools}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-800 dark:text-slate-100">
                        {e.accessed_resources}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </details>
        </>
      )}
    </div>
  );
}

/** A ranked list of labelled bars, sized against the largest value present. */
function RankedBars({
  rows,
  colour,
  empty,
}: {
  rows: MyTopItem[];
  colour: string;
  empty: string;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">{empty}</p>;
  }
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <div key={r.name ?? "—"}>
          <div className="mb-1 flex items-center justify-between gap-2 text-xs">
            <span className="truncate text-slate-700 dark:text-slate-200">
              {r.name ?? "—"}
            </span>
            <span className="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">
              {fmtNumber(r.value)}
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
      ))}
    </div>
  );
}

/**
 * You against your team and the organisation.
 *
 * Only medians are shown. The personal page is reachable by every signed-in
 * user, so putting a named colleague's figures here would hand everyone a
 * league table of people who never agreed to be in one.
 */
function fmtPeriod(from: string | null, to: string | null, days: number): string {
  if (!from || !to) return `the last ${days} days`;
  const d = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
    });
  return `${d(from)} – ${d(to)}`;
}

/**
 * Why there is no team series, in the reader's terms.
 *
 * The two reasons are different facts about the tenant and only one of them is
 * fixable: a team below the disclosure floor will never be shown, whereas an
 * unknown team means nobody has populated departments and somebody could.
 * Collapsing them into "no team data" leaves an administrator with no idea
 * which of those they are looking at.
 */
function teamWithheldNote(standing: MyStanding): string | null {
  if (standing.team_state === "shown") return null;
  if (standing.team_state === "too_small") {
    return `Your team is too small to show — ${standing.team_peers} ${
      standing.team_peers === 1 ? "person" : "people"
    } besides you, and a team average is only shown from ${
      standing.min_team_peers
    }. Below that, the average and your own figure would give away an individual's number.`;
  }
  return "We don't know which team you're in — your directory record has no department or manager, so there is nobody to compare you with.";
}

function Standing({ standing }: { standing: MyStanding }) {
  const { team_label, org_percentile, org_people, stats } = standing;
  const period = fmtPeriod(
    standing.period_from,
    standing.period_to,
    standing.period_days,
  );
  const withheld = teamWithheldNote(standing);
  return (
    <ChartCard
      title="How you compare"
      subtitle={`${period} · ● you're in the top ${Math.max(
        100 - org_percentile,
        1,
      )}% of the ${org_people.toLocaleString()} people in this organisation${
        team_label ? `, and against ${team_label}` : ""
      }`}
    >
      <div className="grid gap-6 md:grid-cols-3">
        {stats.map((s) => (
          <PeerBars key={s.label} stat={s} teamLabel={team_label} />
        ))}
      </div>
      {withheld && (
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
          {withheld}
        </p>
      )}
      <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
        Only medians are shown — never another individual's figures. Your
        percentile is measured against the whole organisation, not your team.
      </p>
    </ChartCard>
  );
}

function PeerBars({ stat, teamLabel }: { stat: PeerStat; teamLabel: string | null }) {
  // Scale all three bars against the largest of them, so the comparison is
  // honest: scaling each to its own width would make every row look equal.
  const max = Math.max(stat.mine, stat.team_median, stat.org_median, 1);
  const rows: { label: string; value: number; colour: string; suffix?: string }[] = [
    { label: "You", value: stat.mine, colour: CHART_COLORS[0] },
  ];
  if (teamLabel) {
    rows.push({
      // The manager fallback already names itself a team ("Ping Lim's team"),
      // so prefixing it again reads as "Your team · Ping Lim's team".
      label: teamLabel.endsWith("'s team")
        ? teamLabel
        : `Your team · ${teamLabel}`,
      value: stat.team_median,
      colour: CHART_COLORS[1],
      suffix: "median",
    });
  }
  rows.push({
    label: "Organisation",
    value: stat.org_median,
    colour: "#94a3b8",
    suffix: "median",
  });

  return (
    <div>
      <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {stat.label}
      </div>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="truncate font-medium text-slate-700 dark:text-slate-200">
                {r.label}
              </span>
              <span className="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">
                {fmtNumber(r.value)}
                {r.suffix ? ` ${r.suffix}` : ""}
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700/60">
              <div
                className="h-3 rounded-full"
                style={{
                  width: `${Math.max((r.value / max) * 100, 2)}%`,
                  backgroundColor: r.colour,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * The way through to organisation-wide reporting. When the user isn't allowed,
 * this is shown locked rather than hidden — otherwise people assume the feature
 * is broken and raise a ticket, instead of knowing to ask for access.
 */
function OrgViewBanner({ canViewOrg }: { canViewOrg: boolean }) {
  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {canViewOrg ? (
          <>
            <div>
              <div className="font-medium text-slate-800 dark:text-slate-100">
                Looking for everyone else?
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400">
                You have access to organisation-wide reporting.
              </div>
            </div>
            <Link to="/overview" className="btn-primary whitespace-nowrap">
              View organisation data →
            </Link>
          </>
        ) : (
          <>
            <div>
              <div className="font-medium text-slate-800 dark:text-slate-100">
                Organisation view
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400">
                🔒 Organisation-wide reporting is limited to an approved group. Ask
                your administrator if you need access.
              </div>
            </div>
            <button className="btn-secondary whitespace-nowrap" disabled>
              Not available
            </button>
          </>
        )}
      </div>
    </div>
  );
}
