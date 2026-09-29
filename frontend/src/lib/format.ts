// Small formatting helpers shared across pages.

export function fmtMoney(value: number, currency: string | null): string {
  const cur = currency || "USD";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: cur,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${cur} ${value.toFixed(0)}`;
  }
}

export function fmtNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

/**
 * A date a reader cannot misread.
 *
 * toLocaleDateString() with no arguments follows the browser's locale, which
 * renders 9 August as "8/9/2026" in the United States and "9/8/2026" almost
 * everywhere else. On a report that is read in one country and screenshotted
 * for another, an all-numeric date is a genuine ambiguity — so the month is
 * always spelled.
 */
export function fmtDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** The same date without the year, for dense chart axes. */
export function fmtDayShort(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
