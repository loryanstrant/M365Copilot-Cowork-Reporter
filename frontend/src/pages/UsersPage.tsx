import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DirectoryUser } from "../api/types";
import { Card, Empty } from "../components/Card";
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
    { key: "name", header: "Name", value: (r) => r.display_name },
    { key: "upn", header: "UPN", value: (r) => r.user_principal_name },
    { key: "job_title", header: "Job title", value: (r) => r.job_title },
    { key: "department", header: "Department", value: (r) => r.department },
    { key: "company", header: "Company", value: (r) => r.company_name },
    { key: "office", header: "Office", value: (r) => r.office_location },
    { key: "city", header: "City", value: (r) => r.city },
    { key: "country", header: "Country", value: (r) => r.country },
    { key: "manager", header: "Manager", value: (r) => r.manager_name },
    { key: "type", header: "Type", value: (r) => r.user_type },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">
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
        <Card title={`${users.length} users`}>
          <DataTable columns={columns} rows={users} initialSortKey="name" initialSortDir="asc" />
        </Card>
      )}
    </div>
  );
}
