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
      { key: "department", header: "Department", accessor: (r) => r.department },
      // Four directory fields are deliberately not shown, and the choice was
      // measured in the running app rather than guessed. At a 1440px window —
      // an ordinary laptop, and the width worth designing for — the card gives
      // this table 1094px. With Company, Office, Job title and Country present
      // it wanted 1210px and the Licence column, which is the one people come
      // here for, was pushed off the right edge.
      //
      // What survives is what answers the page's question, "who holds a licence
      // and is not using it": who they are, who manages them, and what they
      // have done. Company is the same string on every row in a single-tenant
      // directory; Office and Country are geography that Department covers well
      // enough here; Job title says less than Department for this purpose. All
      // four are still returned by the API.
      //
      // Measured after trimming, in the running app at 1440px: the table no
      // longer overflows its container at all.
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
          Everyone who holds a Microsoft 365 Copilot licence, whether or not they
          have ever used Cowork. Someone with a licence and nothing against their
          name is listed with zeroes rather than hidden — that is the row worth
          finding. Click a header to sort, type to filter.
        </p>
      </div>

      {loaded && users.length === 0 ? (
        <Empty message="No licensed users found. Configure the app registration in Settings and run the collectors — licences are read from the directory, so this fills in as soon as the user sync has run." />
      ) : (
        <ChartCard
          title={`${fmtNumber(users.length)} licensed users`}
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
