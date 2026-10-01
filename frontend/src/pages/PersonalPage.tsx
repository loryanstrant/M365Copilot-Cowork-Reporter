import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type {
  MyActivity,
  MyDay,
  MyEvent,
  MyStanding,
  MyTopItem,
} from "../api/types";
import ActivityTimeline, {
  type TimelinePoint,
} from "../components/ActivityTimeline";
import ChartCard from "../components/ChartCard";
import Empty from "../components/Empty";
import KpiCard from "../components/KpiCard";
import PeerComparison from "../components/PeerComparison";
import { CHART_COLORS } from "../components/chartTheme";
import { fmtDate, fmtNumber } from "../lib/format";


/** Credits are issued and consumed whole, so the decimals were noise on every
 *  row that ever showed them. */
function fmtCredits(n: number): string {
  return Math.round(n).toLocaleString();
}

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
  const [tools, setTools] = useState<MyTopItem[]>([]);
  const [events, setEvents] = useState<MyEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [a, d, s, tl, ev] = await Promise.all([
          // No window: all time, so the chart and the totals above it cover
          // the same span. A 30-day chart under an all-time figure is two
          // claims on one screen with nothing to tell them apart.
          api<MyActivity>("/metrics/me/activity"),
          api<MyDay[]>("/metrics/me/daily"),
          api<MyStanding>("/metrics/me/standing"),
          api<MyTopItem[]>("/metrics/me/top-tools"),
          api<MyEvent[]>("/metrics/me/events?limit=25"),
        ]);
        if (!active) return;
        setActivity(a);
        setDaily(d);
        setStanding(s);
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
          How you've been using Copilot Cowork. Only you and
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
              We can't find any Cowork activity recorded for your account. That usually means you haven't used Cowork since reporting started,
              or the collectors haven't run yet.
            </p>
          </div>
        </ChartCard>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
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
              hint="with recorded activity"
            />
            {/* The hint distinguishes "you used none" from "none were
                imported". A bare 0.00 cannot, and this report spent a while
                showing the second while looking like the first. */}
            <KpiCard
              label="Credits used"
              value={fmtCredits(activity?.credits_consumed ?? 0)}
              hint={
                activity?.credits_available
                  ? "Your share of the latest credit upload"
                  : "No credit figures imported yet"
              }
            />
          </div>

          <ChartCard
            title="Your sessions per day"
            subtitle="Cowork audit events, with a 7-day trailing average"
          >
            <ActivityTimeline
              points={daily as unknown as TimelinePoint[]}
              dateKey="day"
              series={[{ key: "sessions", label: "Sessions", colorIndex: 0 }]}
            />
          </ChartCard>

          {standing && <PeerComparison standing={standing} />}

          {/* Tools alone, full width. The agent breakdown that used to sit
              beside it is gone: every event in this report is Cowork, so
              ranking agents ranked one thing against itself. */}
          <ChartCard
            title="Your top tools"
            subtitle="Tool calls"
          >
            <RankedBars rows={tools} colour={CHART_COLORS[3]} empty="No tool calls recorded yet." />
          </ChartCard>

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
