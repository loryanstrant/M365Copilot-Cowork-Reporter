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
import { Card, Empty } from "../components/Card";
import { fmtNumber, fmtDate } from "../lib/format";

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Usage</h1>
        <p className="text-sm text-slate-500">
          Cowork adoption — tasks, active users, retention. Framed as adoption &amp;
          enablement, not individual performance.
        </p>
      </div>

      {loaded && byUser.length === 0 && trend.length === 0 && (
        <Empty message="No usage data yet. Upload the admin-centre Cowork usage report CSV from the Upload page." />
      )}

      {trend.length > 0 && (
        <Card title="Active users &amp; tasks by report window">
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
        </Card>
      )}

      {byUser.length > 0 && (
        <Card title="Adoption by user (latest snapshot)">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2">User</th>
                <th>Department</th>
                <th className="text-right">Total</th>
                <th className="text-right">Scheduled</th>
                <th className="text-right">User-initiated</th>
                <th className="text-right">Active days</th>
                <th className="text-right">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {byUser.map((u) => (
                <tr key={u.user_principal_name} className="border-b border-slate-100">
                  <td className="py-2">
                    <div className="font-medium text-slate-700">
                      {u.display_name || u.user_principal_name}
                    </div>
                    <div className="text-xs text-slate-400">{u.user_principal_name}</div>
                  </td>
                  <td>{u.department || "—"}</td>
                  <td className="text-right font-medium">{fmtNumber(u.total_tasks)}</td>
                  <td className="text-right">{fmtNumber(u.scheduled_tasks)}</td>
                  <td className="text-right">{fmtNumber(u.user_initiated_tasks)}</td>
                  <td className="text-right">{fmtNumber(u.active_days)}</td>
                  <td className="text-right text-slate-500">{fmtDate(u.last_activity_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
