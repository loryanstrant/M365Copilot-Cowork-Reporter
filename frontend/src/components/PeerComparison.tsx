import ChartCard from "./ChartCard";
import { CHART_COLORS } from "./chartTheme";
import { fmtNumber } from "../lib/format";

/**
 * The shape this component needs, declared here rather than imported from a
 * repo's `api/types`.
 *
 * That is deliberate: the component is shared across the four reports, and
 * each of them names its own standing type differently. Declaring the contract
 * here means a repo can pass whatever its endpoint returns as long as the
 * fields line up, and the component carries its own definition of what it
 * needs when it is copied into the next app.
 */
export interface PeerStatShape {
  /** The measure's name, as the server chose to call it. */
  label: string;
  mine: number;
  /** Median across the viewer's peers. Zero when the team is withheld. */
  team_median: number;
  org_median: number;
  team_people: number;
  org_people: number;
}

export interface PeerStandingShape {
  team_label: string | null;
  /**
   * Why the team series is or is not drawn — an explicit state rather than a
   * null the UI has to interpret. "too_small" and "unknown" are different
   * facts about the tenant and only one of them can be acted on.
   */
  team_state: "shown" | "too_small" | "unknown";
  /** Peers found, excluding the viewer. Non-zero even when withheld. */
  team_peers: number;
  /**
   * The disclosure floor, from the server. The copy below names it rather than
   * hard-coding it, because the threshold is the backend's to own and a page
   * that says "five" while the API uses six is worse than one that says
   * nothing.
   */
  min_team_peers: number;
  period_days: number;
  period_from: string | null;
  period_to: string | null;
  org_percentile: number;
  org_people: number;
  stats: PeerStatShape[];
}

/** Select, reorder or rename the measures. Omit to show them all as sent. */
export interface PeerMeasure {
  /** Matches `PeerStatShape.label` as the API sends it. */
  label: string;
  /** Shown instead, when the API's word is not the product's word. */
  as?: string;
}

function fmtPeriod(from: string | null, to: string | null, days: number): string {
  if (!from || !to) return `the last ${days} days`;
  const d = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
    });
  return `${d(from)} – ${d(to)}`;
}

/**
 * Why there is no team series, in the reader's terms.
 *
 * The two reasons are different facts about the tenant and only one of them is
 * fixable: a team below the disclosure floor will never be shown, whereas an
 * unknown team means nobody has populated departments and somebody could.
 * Collapsing them into "no team data" leaves an administrator with no idea
 * which of those they are looking at, and no idea whether there is anything to
 * do about it.
 */
export function teamWithheldNote(standing: PeerStandingShape): string | null {
  if (standing.team_state === "shown") return null;
  if (standing.team_state === "too_small") {
    const who =
      standing.team_peers === 0
        ? "you are the only person in it"
        : `there ${standing.team_peers === 1 ? "is" : "are"} ${
            standing.team_peers
          } ${standing.team_peers === 1 ? "person" : "people"} in it besides you`;
    return `Your team is too small to show — ${who}, and a team average is only shown from ${standing.min_team_peers}. Below that, the average and your own figure together would give an individual's number away.`;
  }
  return "We don't know which team you're in — your directory record has no department or manager, so there is nobody to compare you with.";
}

/**
 * You, your team and the organisation, on the same measures over one window.
 *
 * Only medians are rendered, and a withheld team arrives already zeroed from
 * the server — this component never has to hide a figure, because a figure it
 * could hide is one that already reached the browser.
 *
 * The measures are whatever the endpoint sends, so the component is not tied
 * to any one report's nouns; pass `measures` to subset, reorder or rename them.
 */
export default function PeerComparison({
  standing,
  measures,
  title = "How you compare",
}: {
  standing: PeerStandingShape;
  measures?: PeerMeasure[];
  title?: string;
}) {
  const { team_label, org_percentile, org_people, stats } = standing;

  const shown: { stat: PeerStatShape; label: string }[] = measures
    ? measures
        .map((m) => {
          const stat = stats.find((s) => s.label === m.label);
          return stat ? { stat, label: m.as ?? stat.label } : null;
        })
        .filter((x): x is { stat: PeerStatShape; label: string } => x !== null)
    : stats.map((stat) => ({ stat, label: stat.label }));

  const period = fmtPeriod(
    standing.period_from,
    standing.period_to,
    standing.period_days,
  );
  const withheld = teamWithheldNote(standing);

  return (
    <ChartCard
      title={title}
      subtitle={`${period} · ● you're in the top ${Math.max(
        100 - org_percentile,
        1,
      )}% of the ${org_people.toLocaleString()} people in this organisation${
        team_label ? `, and against ${team_label}` : ""
      }`}
    >
      <div className="grid gap-6 md:grid-cols-3">
        {shown.map(({ stat, label }) => (
          <PeerBars
            key={stat.label}
            stat={stat}
            label={label}
            teamLabel={standing.team_state === "shown" ? team_label : null}
          />
        ))}
      </div>
      {withheld && (
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
          {withheld}
        </p>
      )}
      <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
        Only medians are shown — never another individual's figures. Your
        percentile is measured against the whole organisation, not your team.
      </p>
    </ChartCard>
  );
}

function PeerBars({
  stat,
  label,
  teamLabel,
}: {
  stat: PeerStatShape;
  label: string;
  teamLabel: string | null;
}) {
  // Scale all three bars against the largest of them, so the comparison is
  // honest: scaling each to its own width would make every row look equal.
  const max = Math.max(stat.mine, stat.team_median, stat.org_median, 1);
  const rows: { label: string; value: number; colour: string; suffix?: string }[] = [
    { label: "You", value: stat.mine, colour: CHART_COLORS[0] },
  ];
  if (teamLabel) {
    rows.push({
      // The manager fallback already names itself a team ("Ping Lim's team"),
      // so prefixing it again reads as "Your team · Ping Lim's team".
      label: teamLabel.endsWith("'s team") ? teamLabel : `Your team · ${teamLabel}`,
      value: stat.team_median,
      colour: CHART_COLORS[1],
      suffix: "median",
    });
  }
  rows.push({
    label: "Organisation",
    value: stat.org_median,
    colour: "#94a3b8",
    suffix: "median",
  });

  return (
    <div>
      <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {label}
      </div>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="truncate font-medium text-slate-700 dark:text-slate-200">
                {r.label}
              </span>
              <span className="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">
                {fmtNumber(r.value)}
                {r.suffix ? ` ${r.suffix}` : ""}
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700/60">
              <div
                className="h-3 rounded-full"
                style={{
                  width: `${Math.max((r.value / max) * 100, 2)}%`,
                  backgroundColor: r.colour,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
