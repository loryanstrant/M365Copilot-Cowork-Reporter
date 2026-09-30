import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ChartTooltip from "./ChartTooltip";
import { barGradId } from "./chartTheme";

export interface TimelinePoint {
  [measure: string]: string | number | null;
}

export interface TimelineSeries {
  key: string;
  label: string;
  /** Index into the suite palette. Used for the gradient fill and the legend. */
  colorIndex?: number;
}

/** Every calendar day between the first and last point, zero-filled. */
function fillDays(
  points: TimelinePoint[],
  series: TimelineSeries[],
  dateKey: string,
): TimelinePoint[] {
  const dated = points.filter((p) => p[dateKey]);
  if (dated.length === 0) return [];
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const at = (p: TimelinePoint) => String(p[dateKey]).slice(0, 10);
  const byDate = new Map(dated.map((p) => [at(p), p]));
  const keys = dated.map(at).sort();
  const start = new Date(`${keys[0]}T00:00:00Z`);
  const end = new Date(`${keys[keys.length - 1]}T00:00:00Z`);

  const out: TimelinePoint[] = [];
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const key = iso(d);
    const hit = byDate.get(key);
    if (hit) {
      out.push(hit);
    } else {
      const blank: TimelinePoint = { [dateKey]: key };
      for (const s of series) blank[s.key] = 0;
      out.push(blank);
    }
  }
  return out;
}

/**
 * Daily bars with a rolling-average line over them.
 *
 * Shared across the suite so the four reports' personal timelines behave
 * identically. Two deliberate choices:
 *
 * - **Every day in the range gets a slot, including days with nothing.** A
 *   chart that silently skips empty days compresses a fortnight of silence
 *   into a single gridline, and "I didn't touch it for two weeks" is usually
 *   the useful signal on a personal page. Cowork's /metrics/me/daily already
 *   zero-fills its window, so here the fill is a no-op — it is kept because
 *   the component has to behave the same way against an endpoint that groups
 *   by date and therefore skips them.
 * - The trend line is a *trailing* average, so it never implies knowledge of
 *   days that have not happened yet.
 */
export default function ActivityTimeline({
  points,
  series,
  dateKey = "date",
  trendOf,
  trendWindow = 7,
  height = 220,
}: {
  points: TimelinePoint[];
  series: TimelineSeries[];
  /** The field holding the ISO date. Cowork's daily endpoint calls it "day". */
  dateKey?: string;
  /** Which series the trend line averages. Defaults to the first. */
  trendOf?: string;
  trendWindow?: number;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No activity in this period yet.
      </p>
    );
  }

  const trendKey = trendOf ?? series[0]?.key;
  const filled = fillDays(points, series, dateKey);

  const data = filled.map((p, i) => {
    const window = filled
      .slice(Math.max(0, i - (trendWindow - 1)), i + 1)
      .map((q) => Number(q[trendKey] ?? 0));
    const avg = window.reduce((a, b) => a + b, 0) / (window.length || 1);
    return { ...p, __trend: Math.round(avg * 10) / 10 };
  });

  const dayLabel = (iso: string) =>
    new Date(`${String(iso).slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
          {/* Grid and axes are themed by class rather than by a literal colour:
              this app has a real dark mode, and a hard-coded light grey grid
              is invisible on the dark canvas and too heavy on the light one. */}
          <CartesianGrid
            strokeDasharray="3 3"
            vertical={false}
            className="stroke-slate-200 dark:stroke-slate-700"
          />
          <XAxis
            dataKey={dateKey}
            tickFormatter={(v) => dayLabel(String(v))}
            tick={{ fontSize: 11 }}
            minTickGap={24}
          />
          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: "rgba(59,110,245,0.06)" }}
            content={<ChartTooltip />}
            labelFormatter={(v) => dayLabel(String(v))}
          />
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              fill={`url(#${barGradId(s.colorIndex ?? i)})`}
              radius={[3, 3, 0, 0]}
            />
          ))}
          <Line
            type="monotone"
            dataKey="__trend"
            name={`${trendWindow}-day average`}
            // Slate, not a palette colour: the trend is not another category
            // alongside the bars, and it reads on both canvases.
            stroke="#64748b"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
