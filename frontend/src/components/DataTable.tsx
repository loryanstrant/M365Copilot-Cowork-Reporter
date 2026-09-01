import { useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  /** Value used for sorting/filtering (string or number). */
  value: (row: T) => string | number | null | undefined;
  /** Optional custom cell renderer; defaults to the value. */
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
  /** Set false to disable filtering for this column (e.g. numeric-only). */
  filterable?: boolean;
}

type SortDir = "asc" | "desc";

export default function DataTable<T>({
  columns,
  rows,
  initialSortKey,
  initialSortDir = "desc",
  emptyMessage = "No rows.",
}: {
  columns: Column<T>[];
  rows: T[];
  initialSortKey?: string;
  initialSortDir?: SortDir;
  emptyMessage?: string;
}) {
  const [sortKey, setSortKey] = useState<string | undefined>(initialSortKey);
  const [sortDir, setSortDir] = useState<SortDir>(initialSortDir);
  const [filters, setFilters] = useState<Record<string, string>>({});

  const filtered = useMemo(() => {
    let out = rows;
    for (const [key, term] of Object.entries(filters)) {
      if (!term) continue;
      const col = columns.find((c) => c.key === key);
      if (!col) continue;
      const lc = term.toLowerCase();
      out = out.filter((r) =>
        String(col.value(r) ?? "")
          .toLowerCase()
          .includes(lc),
      );
    }
    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      if (col) {
        out = [...out].sort((a, b) => {
          const av = col.value(a);
          const bv = col.value(b);
          if (av == null && bv == null) return 0;
          if (av == null) return 1;
          if (bv == null) return -1;
          let cmp: number;
          if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
          else cmp = String(av).localeCompare(String(bv));
          return sortDir === "asc" ? cmp : -cmp;
        });
      }
    }
    return out;
  }, [rows, columns, filters, sortKey, sortDir]);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-700 dark:text-slate-400">
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`py-2 ${c.align === "right" ? "text-right" : ""}`}
                >
                  <button
                    onClick={() => toggleSort(c.key)}
                    className="inline-flex items-center gap-1 font-semibold hover:text-slate-700 dark:hover:text-slate-200"
                  >
                    {c.header}
                    <span className="text-[10px]">
                      {sortKey === c.key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
            <tr className="border-b border-slate-100 dark:border-slate-800">
              {columns.map((c) => (
                <th key={c.key} className="pb-2 pr-2">
                  {c.filterable === false ? null : (
                    <input
                      value={filters[c.key] || ""}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, [c.key]: e.target.value }))
                      }
                      placeholder="Filter…"
                      className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs font-normal text-slate-700 outline-none focus:border-brand-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                    />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={`py-2 ${c.align === "right" ? "text-right" : ""}`}
                  >
                    {c.render ? c.render(r) : (c.value(r) ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <div className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
          {emptyMessage}
        </div>
      )}
      <div className="mt-3 text-xs text-slate-400 dark:text-slate-500">
        {filtered.length} of {rows.length} rows
      </div>
    </div>
  );
}
