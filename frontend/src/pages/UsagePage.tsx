import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { api } from "../api/client";
import type { UsageByUser, UsageTrend } from "../api/types";
import ChartCard from "../components/ChartCard";
import Empty from "../components/Empty";
import DataTable, { type Column } from "../components/DataTable";
import { fmtDate } from "../lib/format";

export default function UsagePage() {
  const [byUser, setByUser] = useState<UsageByUser[]>([]);
  const [trend, setTrend] = useState<UsageTrend[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      setTrend(await api<UsageTrend[]>("/metrics/usage/trend"));
      setByUser(await api<UsageByUser[]>("/metrics/usage/by-user"));
      setLoaded(true);
    })();
  }, []);

  const columns: Column<UsageByUser>[] = [
    {
      key: "user",
      header: "User",
      accessor: (r) => r.display_name || r.user_principal_name,
      render: (r) => (
        <div>
          <div className="font-medium text-slate-700 dark:text-slate-200">
            {r.display_name || r.user_principal_name}
          </div>
          <div className="text-xs text-slate-400 dark:text-slate-500">
            {r.user_principal_name}
          </div>
        </div>
      ),
    },
    { key: "department", header: "Department", accessor: (r) => r.department },
    { key: "job_title", header: "Job title", accessor: (r) => r.job_title },
    { key: "office", header: "Office", accessor: (r) => r.office_location },
    { key: "country", header: "Country", accessor: (r) => r.country },
    { key: "manager", header: "Manager", accessor: (r) => r.manager_name },
    {
      key: "total_tasks",
      header: "Total",
      type: "number",
      accessor: (r) => r.total_tasks,
      align: "right",
      filterable: false,
    },
    {
      key: "scheduled",
      header: "Scheduled",
      type: "number",
      accessor: (r) => r.scheduled_tasks,
      align: "right",
      filterable: false,
    },
    {
      key: "user_initiated",
      header: "User-initiated",
      type: "number",
      accessor: (r) => r.user_initiated_tasks,
      align: "right",
      filterable: false,
    },
    {
      key: "active_days",
      header: "Active days",
      type: "number",
      accessor: (r) => r.active_days,
      align: "right",
      filterable: false,
    },
    {
      key: "last_activity",
      header: "Last activity",
      type: "date",
      accessor: (r) => r.last_activity_date,
      render: (r) => fmtDate(r.last_activity_date),
      align: "right",
      filterable: false,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">
          Usage
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Cowork adoption — tasks, active users, retention. Framed as adoption &amp;
          enablement, not individual performance.
        </p>
      </div>

      {loaded && byUser.length === 0 && trend.length === 0 && (
        <Empty message="No usage data yet. Upload the admin-centre Cowork usage report CSV from the Upload page." />
      )}

      {trend.length > 0 && (
        <ChartCard title="Active users &amp; tasks by report window">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
              <XAxis
                dataKey="period_days"
                tickFormatter={(v) => `${v}d`}
                tick={{ fontSize: 11 }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="active_users" name="Active users" fill="#2f5ae0" radius={[4, 4, 0, 0]} />
              <Bar dataKey="total_tasks" name="Total tasks" fill="#8fb4fe" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {byUser.length > 0 && (
        <ChartCard title="Adoption by user (latest snapshot) — click a header to sort, type to filter">
          <DataTable
            columns={columns}
            rows={byUser}
            getRowKey={(r, i) => r.user_principal_name ?? i}
            initialSort={{ key: "total_tasks", dir: "desc" }}
            filterable
          />
        </ChartCard>
      )}
    </div>
  );
}
