import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { api } from "../api/client";
import type { CostByGroup, CostTrend } from "../api/types";
import { Card, Empty } from "../components/Card";
import { fmtMoney } from "../lib/format";

export default function ConsumptionPage() {
  const [byGroup, setByGroup] = useState<CostByGroup[]>([]);
  const [trend, setTrend] = useState<CostTrend[]>([]);
  const [currency, setCurrency] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      const g = await api<CostByGroup[]>("/metrics/cost/by-group?days=30");
      const t = await api<CostTrend[]>("/metrics/cost/trend?days=30");
      setByGroup(g);
      setTrend(t);
      const k = await api<{ currency: string | null }>("/metrics/kpis?days=30");
      setCurrency(k.currency);
      setLoaded(true);
    })();
  }, []);

  const hasData = byGroup.length > 0 || trend.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Consumption</h1>
        <p className="text-sm text-slate-500">
          Azure spend (automated) and Copilot credit consumption. Dollars, not tasks.
        </p>
      </div>

      {loaded && !hasData && (
        <Empty message="No cost data yet. Configure Azure subscriptions in Settings and run the collector, or upload a credits CSV." />
      )}

      {trend.length > 0 && (
        <Card title="Daily Azure cost (30 days)">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
              <XAxis dataKey="cost_date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => fmtMoney(v, currency)} />
              <Line
                type="monotone"
                dataKey="cost"
                stroke="#2f5ae0"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {byGroup.length > 0 && (
        <Card title="Cost by resource group → chargeback">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={byGroup} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="resource_group"
                width={160}
                tick={{ fontSize: 11 }}
              />
              <Tooltip formatter={(v: number) => fmtMoney(v, currency)} />
              <Bar dataKey="cost" fill="#3b6ef5" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2">Resource group</th>
                <th>Cost centre</th>
                <th>Project</th>
                <th className="text-right">Cost</th>
              </tr>
            </thead>
            <tbody>
              {byGroup.map((r) => (
                <tr key={r.resource_group} className="border-b border-slate-100">
                  <td className="py-2 font-mono text-xs">{r.resource_group || "—"}</td>
                  <td>{r.cost_centre || <span className="text-amber-600">unmapped</span>}</td>
                  <td>{r.project || "—"}</td>
                  <td className="text-right font-medium">{fmtMoney(r.cost, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-slate-400">
            Unmapped resource groups appear in the Chargeback admin page — map them to a
            cost centre there.
          </p>
        </Card>
      )}
    </div>
  );
}
