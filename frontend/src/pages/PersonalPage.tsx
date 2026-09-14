import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { MyComparison, MyEvent, MySummary } from "../api/types";
import { Card, Kpi, Empty } from "../components/Card";
import { fmtDate, fmtNumber } from "../lib/format";

/**
 * The landing page for anyone signed in with a work account: their own Cowork
 * activity, and nobody else's. The server derives "me" from the token, so there
 * is no user to pass in from here.
 */
export default function PersonalPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<MySummary | null>(null);
  const [events, setEvents] = useState<MyEvent[]>([]);
  const [comparison, setComparison] = useState<MyComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [s, e, c] = await Promise.all([
          api<MySummary>("/metrics/me/summary?days=30"),
          api<MyEvent[]>("/metrics/me/events?limit=25"),
          api<MyComparison>("/metrics/me/comparison?days=30"),
        ]);
        if (!active) return;
        setSummary(s);
        setEvents(e);
        setComparison(c);
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

  const hasData = Boolean(summary?.has_data);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Your Cowork activity</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          How you've been using Copilot Cowork. Only you and your administrators can
          see this.
        </p>
      </div>

      <OrgViewBanner canViewOrg={user?.can_view_org ?? false} />

      {err && <Empty message={err} />}

      {!hasData && !err ? (
        <Card title="Your activity">
          <div className="py-10 text-center">
            <h2 className="mb-2 text-lg font-semibold text-slate-800 dark:text-slate-100">
              Nothing to show yet
            </h2>
            <p className="mx-auto max-w-md text-sm text-slate-500 dark:text-slate-400">
              We can't find any Cowork activity for your account. That usually means
              you haven't used Cowork since reporting started, or the latest usage
              export hasn't been uploaded yet.
            </p>
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Kpi
              label="Your Cowork tasks"
              value={fmtNumber(summary?.total_tasks ?? 0)}
              hint={
                summary?.report_period
                  ? `Latest ${summary.report_period}-day snapshot`
                  : "Latest usage snapshot"
              }
            />
            <Kpi
              label="Active days"
              value={fmtNumber(summary?.active_days ?? 0)}
              hint={
                summary?.last_activity_date
                  ? `Last active ${fmtDate(summary.last_activity_date)}`
                  : undefined
              }
            />
            <Kpi
              label="Your sessions"
              value={fmtNumber(summary?.cowork_events ?? 0)}
              hint="Purview audit events"
            />
            <Kpi
              label="Credits consumed"
              value={fmtNumber(summary?.credits_consumed ?? 0)}
              hint="Latest admin CSV snapshot"
            />
          </div>

          {comparison && comparison.people_counted > 0 && (
            <Card title="How you compare">
              <p className="text-sm text-slate-600 dark:text-slate-300">
                You ran {fmtNumber(comparison.my_tasks)} tasks against an organisation
                median of {fmtNumber(comparison.org_median_tasks)} across{" "}
                {fmtNumber(comparison.people_counted)} active people.{" "}
                {comparison.above_median
                  ? "You're above the median."
                  : "You're below the median."}
              </p>
              <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
                Only the median is shown — never another individual's figures.
              </p>
            </Card>
          )}

          <Card title="Your recent Cowork sessions">
            {events.length === 0 ? (
              <Empty message="No audit events recorded for your account yet." />
            ) : (
              <table className="w-full text-sm">
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
          </Card>
        </>
      )}
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
    <Card>
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
    </Card>
  );
}
