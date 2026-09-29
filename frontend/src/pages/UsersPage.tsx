import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DirectoryUser } from "../api/types";
import ChartCard from "../components/ChartCard";
import Empty from "../components/Empty";
import DataTable, { type Column } from "../components/DataTable";

export default function UsersPage() {
  const [users, setUsers] = useState<DirectoryUser[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      setUsers(await api<DirectoryUser[]>("/metrics/users"));
      setLoaded(true);
    })();
  }, []);

  const columns: Column<DirectoryUser>[] = [
    { key: "name", header: "Name", accessor: (r) => r.display_name },
    { key: "upn", header: "UPN", accessor: (r) => r.user_principal_name },
    { key: "job_title", header: "Job title", accessor: (r) => r.job_title },
    { key: "department", header: "Department", accessor: (r) => r.department },
    { key: "company", header: "Company", accessor: (r) => r.company_name },
    { key: "office", header: "Office", accessor: (r) => r.office_location },
    { key: "city", header: "City", accessor: (r) => r.city },
    { key: "country", header: "Country", accessor: (r) => r.country },
    { key: "manager", header: "Manager", accessor: (r) => r.manager_name },
    { key: "type", header: "Type", accessor: (r) => r.user_type },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">
          Tenant users
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Directory users imported from Microsoft Graph — the profile fields that power
          filtering and cost-centre rollups. Click a header to sort, type to filter.
        </p>
      </div>

      {loaded && users.length === 0 ? (
        <Empty message="No users imported yet. Configure the app registration in Settings and run the collectors." />
      ) : (
        <ChartCard title={`${users.length} users`}>
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
