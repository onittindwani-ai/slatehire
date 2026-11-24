"use client";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  /** CSS grid track, for example "2fr" or "120px". */
  width?: string;
  align?: "left" | "right";
  render?: (row: T) => ReactNode;
  /** Value used for sorting. Leave out to make the column unsortable. */
  sortValue?: (row: T) => string | number;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  label: string;
  rowHeight?: number;
  height?: number;
  onRowOpen?: (row: T) => void;
  selectable?: boolean;
  rowActions?: (row: T) => ReactNode;
  bulkActions?: (selected: T[], clear: () => void) => ReactNode;
}

type Sort = { key: string; dir: "asc" | "desc" } | null;

/** Windowed rows (5,000 rows stay smooth), sortable columns, sticky header, keyboard control: j and k or arrows move, enter opens, x selects, escape clears. */
export function DataTable<T>({ columns, rows, rowKey, label, rowHeight = 44, height = 480, onRowOpen, selectable, rowActions, bulkActions }: DataTableProps<T>) {
  const [sort, setSort] = useState<Sort>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [active, setActive] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const scroller = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    const out = [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      return x < y ? -1 : x > y ? 1 : 0;
    });
    return sort.dir === "desc" ? out.reverse() : out;
  }, [rows, sort, columns]);

  const template = [selectable ? "28px" : null, ...columns.map((c) => c.width ?? "1fr"), rowActions ? "auto" : null].filter(Boolean).join(" ");
  const overscan = 6;
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const visible = Math.ceil(height / rowHeight) + overscan * 2;
  const slice = sorted.slice(start, start + visible);
  const clear = useCallback(() => setSelected(new Set()), []);

  useEffect(() => setActive((a) => Math.min(a, Math.max(0, sorted.length - 1))), [sorted.length]);

  function ensureVisible(i: number) {
    const el = scroller.current;
    if (!el) return;
    const top = i * rowHeight;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (top + rowHeight > el.scrollTop + height - 40) el.scrollTop = top + rowHeight - height + 40;
  }

  function onKey(e: KeyboardEvent) {
    if ((e.target as HTMLElement).closest("button, input, a")) return;
    const key = e.key;
    if (key === "j" || key === "ArrowDown") {
      e.preventDefault();
      const n = Math.min(sorted.length - 1, active + 1);
      setActive(n);
      ensureVisible(n);
    } else if (key === "k" || key === "ArrowUp") {
      e.preventDefault();
      const n = Math.max(0, active - 1);
      setActive(n);
      ensureVisible(n);
    } else if (key === "Enter") {
      // stop the Enter from also activating whatever takes focus when the row opens (for example a sheet's close button)
      e.preventDefault();
      const row = sorted[active];
      if (row && onRowOpen) onRowOpen(row);
    } else if (key === "x" && selectable) {
      const row = sorted[active];
      if (row) toggle(rowKey(row));
    } else if (key === "Escape") clear();
  }

  function toggle(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  const selectedRows = useMemo(() => sorted.filter((r) => selected.has(rowKey(r))), [sorted, selected, rowKey]);

  return (
    <div className="sx-table" data-scrolled={scrollTop > 4}>
      <div
        ref={scroller}
        className="sx-table__scroll"
        style={{ height }}
        role="grid"
        aria-label={label}
        aria-rowcount={sorted.length + 1}
        tabIndex={0}
        onKeyDown={onKey}
        onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      >
        <div className="sx-table__head" role="row" style={{ gridTemplateColumns: template }}>
          {selectable ? <span role="columnheader" aria-label="Select" /> : null}
          {columns.map((c) => {
            const dir = sort?.key === c.key ? sort.dir : null;
            return (
              <span key={c.key} role="columnheader" aria-sort={dir ? (dir === "asc" ? "ascending" : "descending") : undefined} style={{ textAlign: c.align }}>
                {c.sortValue ? (
                  <button className="sx-table__sort" type="button" onClick={() => setSort(!dir ? { key: c.key, dir: "asc" } : dir === "asc" ? { key: c.key, dir: "desc" } : null)}>
                    {c.header}
                    {dir === "asc" ? <ArrowUp size={12} aria-hidden /> : dir === "desc" ? <ArrowDown size={12} aria-hidden /> : <ChevronsUpDown size={12} aria-hidden />}
                  </button>
                ) : c.header}
              </span>
            );
          })}
          {rowActions ? <span role="columnheader" aria-label="Actions" /> : null}
        </div>
        <div role="rowgroup" style={{ position: "relative", height: sorted.length * rowHeight }}>
          {slice.map((row, i) => {
            const index = start + i;
            const id = rowKey(row);
            return (
              <div
                key={id}
                role="row"
                aria-rowindex={index + 2}
                aria-selected={selectable ? selected.has(id) : undefined}
                className="sx-table__row"
                data-active={index === active}
                data-selected={selected.has(id) || undefined}
                style={{ top: index * rowHeight, height: rowHeight, gridTemplateColumns: template }}
                onClick={() => setActive(index)}
                onDoubleClick={() => onRowOpen?.(row)}
              >
                {selectable ? <span role="gridcell"><input type="checkbox" aria-label="Select row" checked={selected.has(id)} onChange={() => toggle(id)} /></span> : null}
                {columns.map((c) => (
                  <span key={c.key} role="gridcell" className={`sx-table__cell${c.align === "right" ? " sx-table__cell--num" : ""}`}>
                    {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "")}
                  </span>
                ))}
                {rowActions ? <span role="gridcell" className="sx-table__actions">{rowActions(row)}</span> : null}
              </div>
            );
          })}
        </div>
      </div>
      <div className="sx-table__footer">
        <span className="sx-num">{sorted.length.toLocaleString("en-US")} rows</span>
        <span>j k move, enter opens{selectable ? ", x selects" : ""}</span>
      </div>
      {selectable && selectedRows.length > 0 && bulkActions ? (
        <div className="sx-bulkbar sx-card sx-card--glass" role="toolbar" aria-label="Actions for selected rows">
          <span className="sx-num"><strong>{selectedRows.length}</strong> selected</span>
          {bulkActions(selectedRows, clear)}
        </div>
      ) : null}
    </div>
  );
}
