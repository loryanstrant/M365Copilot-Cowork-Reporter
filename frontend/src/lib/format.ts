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

export function fmtDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString();
}
