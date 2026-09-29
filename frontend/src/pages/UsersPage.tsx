import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { DirectoryUser } from "../api/types";
import ChartCard from "../components/ChartCard";
import Empty from "../components/Empty";
import DataTable, { type Column } from "../components/DataTable";
import { fmtDate, fmtNumber } from "../lib/format";

export default function UsersPage() {
  const [users, setUsers] = useState<DirectoryUser[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      setUsers(await api<DirectoryUser[]>("/metrics/users"));
      setLoaded(true);
    })();
  }, []);

  // Memoised because DataTable's filter and sort both key off this array —
  // rebuilding it every render would defeat their memoisation on every
  // keystroke in a filter box.
  const columns: Column<DirectoryUser>[] = useMemo(
    () => [
      { key: "name", header: "Name", accessor: (r) => r.display_name },
      { key: "upn", header: "UPN", accessor: (r) => r.user_principal_name },
      { key: "job_title", header: "Job title", accessor: (r) => r.job_title },
      { key: "department", header: "Department", accessor: (r) => r.department },
      // Company and Office are deliberately not shown, and the choice was
      // measured rather than guessed. At a 1600px window the card gives the
      // table 1254px; with both present it wanted 1380 and the Licence column
      // fell off the right edge. Company is the same string on every row in a
      // single-tenant directory, so it is width spent on nothing; Office is
      // geography that Department and Country already cover for this page's
      // purpose. Without them the table measures 1138px and has room to
      // spare. Both fields are still returned by the API.
      { key: "country", header: "Country", accessor: (r) => r.country },
      { key: "manager", header: "Manager", accessor: (r) => r.manager_name },
      {
        key: "tasks",
        header: "Tasks",
        type: "number",
        align: "right",
        filterable: false,
        accessor: (r) => r.total_tasks,
        render: (r) => fmtNumber(r.total_tasks),
      },
      {
        key: "sessions",
        header: "Sessions",
        type: "number",
        align: "right",
        filterable: false,
        accessor: (r) => r.cowork_events,
        render: (r) => fmtNumber(r.cowork_events),
      },
      {
        key: "last_seen",
        header: "Last active",
        type: "date",
        filterable: false,
        accessor: (r) => r.last_activity_date,
        render: (r) => (r.last_activity_date ? fmtDate(r.last_activity_date) : "—"),
      },
      {
        key: "licensed",
        header: "Licence",
        accessor: (r) => (r.has_copilot_license ? "Licensed" : "Not licensed"),
        // Shape plus word, never colour alone.
        render: (r) => (
          <span className="whitespace-nowrap">
            <span aria-hidden>{r.has_copilot_license ? "●" : "○"}</span>{" "}
            {r.has_copilot_license ? "Licensed" : "Not licensed"}
          </span>
        ),
      },
    ],
    [],
  );

  const idle = users.filter((u) => u.total_tasks === 0 && u.cowork_events === 0).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Tenant users</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          People who hold a Microsoft 365 Copilot licence and appear in the Cowork
          report data. Someone with a licence and nothing against their name is
          listed rather than hidden — that is the row worth finding. Click a header
          to sort, type to filter.
        </p>
      </div>

      {loaded && users.length === 0 ? (
        <Empty message="No licensed users found in the report data yet. Configure the app registration in Settings and run the collectors, then upload a Cowork usage report." />
      ) : (
        <ChartCard
          title={`${fmtNumber(users.length)} licensed users in the data`}
          subtitle={
            idle > 0
              ? `${fmtNumber(idle)} hold a licence with no recorded activity`
              : "Every licensed person here has recorded activity"
          }
        >
          <DataTable
            columns={columns}
            rows={users}
            getRowKey={(r, i) => r.user_principal_name ?? i}
            initialSort={{ key: "name", dir: "asc" }}
            filterable
          />
        </ChartCard>
      )}
    </div>
  );
}
