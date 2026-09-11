import type { ReactNode } from "react";
import { EmptyState } from "./EmptyState";

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  /** Custom cell renderer; defaults to (row as any)[key]. */
  render?: (row: T) => ReactNode;
  /** Hide on narrow screens to keep tables readable on laptops/tablets. */
  hideOnMobile?: boolean;
  width?: string;
};

const alignCls = { left: "text-left", right: "text-right tabular-nums", center: "text-center" };

export function DataTable<T>({
  columns,
  rows,
  keyField,
  loading,
  empty,
  onRowClick,
  rowActions,
  stickyHeader,
  selectedIds,
  onToggleRow,
  onToggleAll,
}: {
  columns: Column<T>[];
  rows: T[];
  keyField: (row: T) => string;
  loading?: boolean;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  /** Trailing actions cell, right-aligned. */
  rowActions?: (row: T) => ReactNode;
  /** Cap height and keep the header visible while the body scrolls (long lists). */
  stickyHeader?: boolean;
  /** When provided, renders a leading checkbox column for row selection. */
  selectedIds?: Set<string>;
  onToggleRow?: (id: string) => void;
  onToggleAll?: (checked: boolean) => void;
}) {
  const selectable = !!selectedIds;
  const allSelected = selectable && rows.length > 0 && rows.every((r) => selectedIds!.has(keyField(r)));
  if (loading && rows.length === 0) {
    return (
      <div className="overflow-hidden rounded-xl border border-line">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 border-b border-line/60 px-4 py-3 last:border-0">
            <div className="h-3 flex-1 animate-pulse rounded bg-white/5" />
            <div className="h-3 w-24 animate-pulse rounded bg-white/5" />
          </div>
        ))}
      </div>
    );
  }
  if (rows.length === 0) {
    return <>{empty ?? <EmptyState title="Sin resultados" description="No hay datos para mostrar." />}</>;
  }
  const thBase = stickyHeader ? "sticky top-0 z-10 bg-panel" : "";
  return (
    <div className={`rounded-xl border border-line bg-panel ${stickyHeader ? "max-h-[70vh] overflow-auto" : "overflow-x-auto"}`}>
      <table className="w-full min-w-[36rem] text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
            {selectable && (
              <th className={`w-10 px-4 py-2.5 ${thBase}`}>
                <input type="checkbox" checked={allSelected} onChange={(e) => onToggleAll?.(e.target.checked)} aria-label="Seleccionar todo" />
              </th>
            )}
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={`px-4 py-2.5 font-medium ${alignCls[c.align ?? "left"]} ${thBase} ${c.hideOnMobile ? "hidden md:table-cell" : ""}`}
              >
                {c.header}
              </th>
            ))}
            {rowActions && <th className={`px-4 py-2.5 ${thBase}`} />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={keyField(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-line/50 last:border-0 ${selectable && selectedIds!.has(keyField(row)) ? "bg-brand/5" : ""} ${onRowClick ? "cursor-pointer hover:bg-white/[0.03]" : ""}`}
            >
              {selectable && (
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={selectedIds!.has(keyField(row))} onChange={() => onToggleRow?.(keyField(row))} aria-label="Seleccionar fila" />
                </td>
              )}
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-4 py-3 text-text ${alignCls[c.align ?? "left"]} ${c.hideOnMobile ? "hidden md:table-cell" : ""}`}
                >
                  {c.render ? c.render(row) : ((row as Record<string, ReactNode>)[c.key] ?? "—")}
                </td>
              ))}
              {rowActions && (
                <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center justify-end gap-1.5">{rowActions(row)}</div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
