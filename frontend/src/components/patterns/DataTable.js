import React, { useEffect, useMemo, useState } from "react";
import { tableFeatures, useTable } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import Pagination from "@/components/patterns/Pagination";
import EmptyState from "@/components/patterns/EmptyState";
import DataTableToolbar from "@/components/patterns/DataTableToolbar";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { downloadCsv } from "@/utils/tableCsv";
import { cn } from "@/lib/utils";
import { DT } from "@/constants/testIds";

// Fase 40: inti tabel memakai @tanstack/react-table v9 (headless). Hanya fitur inti yang
// didaftarkan — sort & paginasi dikerjakan SERVER (lihat backend/listing.py), jadi tidak ada
// gunanya memuat row-model sort/filter/paginasi klien yang justru akan berbohong pada data
// terpaginasi.
const FEATURES = tableFeatures({});

/**
 * DataTable — pola WAJIB untuk seluruh daftar transaksional (blueprint IA V2 §5).
 *
 * Kontrak:
 *   columns : [{ key, header, render?(row), align?, sortable?, width?, hidden?, exportValue? }]
 *   rows    : array data (satu halaman)
 *   total   : jumlah seluruh hasil (untuk paginasi & label “x dari y”)
 *   query   : { q, sort, direction, skip, limit } — milik halaman (useListQuery: hidup di URL)
 *   onQueryChange(patch)
 *   filters : node React (FilterBar) — halaman yang menentukan filternya
 *   bulkActions: [{ key, label, testId, onRun(selectedRows, clear) }]
 */
export default function DataTable({
  columns = [], rows = [], total = 0, query = {}, onQueryChange, loading = false,
  error = "", filters = null, bulkActions = [], rowKey = (r) => r.id,
  onRowClick, emptyTitle = "Belum ada data", emptyDescription = "", emptyAction = null,
  emptyActionLabel = "", searchPlaceholder = "Cari…", exportName = "data", testId,
  testIds = {}, dense: denseProp = false, footer = null, onRefresh, label = "baris",
}) {
  const [hidden, setHidden] = useState(() => new Set(columns.filter((c) => c.hidden)
    .map((c) => c.key)));
  const [dense, setDense] = useState(denseProp);
  const [selected, setSelected] = useState(() => new Set());
  // Pilihan baris TIDAK dibawa antar halaman/hasil filter: aksi massal harus berlaku pada
  // baris yang benar-benar dilihat pemakai saat menekannya.
  useEffect(() => { setSelected(new Set()); }, [query.skip, query.limit, query.q, query.sort]);

  const visible = useMemo(() => columns.filter((c) => !hidden.has(c.key)), [columns, hidden]);
  const selectedRows = rows.filter((r) => selected.has(rowKey(r)));
  const selectable = bulkActions.length > 0;

  const columnDefs = useMemo(() => visible.map((c) => ({
    id: c.key,
    accessorFn: (row) => row[c.key],
    header: () => c.header,
    cell: ({ row }) => (c.render ? c.render(row.original) : (row.original[c.key] ?? "-")),
    meta: { align: c.align, width: c.width, className: c.className, sortable: c.sortable,
      sticky: c.sticky },
  })), [visible]);

  const table = useTable({
    key: testId || DT.root,
    features: FEATURES,
    columns: columnDefs,
    data: rows,
    getRowId: (row, index) => String(rowKey(row) ?? index),
  });

  const toggleColumn = (key) => setHidden((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const toggleRow = (key) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(rowKey(r)));

  const sortBy = (key, sortable) => {
    if (!sortable || !onQueryChange) return;
    const dir = query.sort === key && query.direction !== "desc" ? "desc" : "asc";
    onQueryChange({ sort: key, direction: dir });
  };

  const headerCells = table.getHeaderGroups()[0]?.headers || [];

  return (
    <div data-testid={testId || DT.root} className="space-y-3">
      <DataTableToolbar query={query} onQueryChange={onQueryChange} columns={columns}
        hidden={hidden} onToggleColumn={toggleColumn} filters={filters}
        searchPlaceholder={searchPlaceholder} testIds={testIds} total={total}
        rowsShown={rows.length} label={label} dense={dense}
        onToggleDense={() => setDense((d) => !d)} onRefresh={onRefresh}
        exportDisabled={!rows.length}
        onExport={() => downloadCsv(visible, rows, exportName)} />

      {selectable && selectedRows.length ? (
        <div data-testid={testIds.bulkBar || DT.bulkBar}
          className="flex flex-wrap items-center gap-2 rounded-xl border border-primary/30 bg-accent px-3 py-2 shadow-sm">
          <span className="text-sm font-medium tabular-nums">
            {selectedRows.length} baris dipilih
          </span>
          {bulkActions.map((a) => (
            <Button key={a.key} data-testid={a.testId} size="sm" variant={a.variant || "secondary"}
              onClick={() => a.onRun(selectedRows, () => setSelected(new Set()))}>
              {a.label}
            </Button>
          ))}
          <Button data-testid={DT.bulkClear} size="sm" variant="ghost"
            onClick={() => setSelected(new Set())}>Bersihkan</Button>
        </div>
      ) : null}

      {loading ? <LoadingCards count={3} /> : null}
      {!loading && error ? <ErrorState message={error} onRetry={onRefresh} /> : null}
      {!loading && !error && !rows.length ? (
        <EmptyState title={emptyTitle} description={emptyDescription}
          actionLabel={emptyActionLabel} onAction={emptyAction} />
      ) : null}

      {!loading && !error && rows.length ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader>
              <TableRow>
                {selectable ? (
                  <TableHead className="w-10">
                    <Checkbox aria-label="Pilih semua baris pada halaman ini"
                      checked={allChecked} data-testid={testIds.selectAll || DT.selectAll}
                      onCheckedChange={(v) => setSelected(v
                        ? new Set(rows.map((r) => rowKey(r))) : new Set())} />
                  </TableHead>
                ) : null}
                {headerCells.map((header) => {
                  const meta = header.column.columnDef.meta || {};
                  const key = header.column.id;
                  return (
                    <TableHead key={header.id} style={meta.width ? { width: meta.width } : undefined}
                      className={cn(meta.align === "right" && "text-right",
                        "whitespace-nowrap", meta.sticky && "col-actions-head")}
                      aria-sort={query.sort === key
                        ? (query.direction === "desc" ? "descending" : "ascending") : undefined}>
                      {meta.sortable ? (
                        <button type="button" data-testid={`${DT.sort}-${key}`}
                          onClick={() => sortBy(key, true)}
                          className="inline-flex items-center gap-1 hover:text-foreground">
                          <table.FlexRender header={header} />
                          {query.sort === key
                            ? (query.direction === "desc"
                              ? <ArrowDown className="h-3.5 w-3.5 text-primary" />
                              : <ArrowUp className="h-3.5 w-3.5 text-primary" />)
                            : <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" />}
                        </button>
                      ) : <table.FlexRender header={header} />}
                    </TableHead>
                  );
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-testid={testIds.row || DT.row}
                  data-row-id={row.id}
                  className={cn(onRowClick && "cursor-pointer", dense && "h-9")}
                  onClick={() => onRowClick?.(row.original)}>
                  {selectable ? (
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox aria-label="Pilih baris ini"
                        data-testid={`${DT.rowSelect}-${row.id}`}
                        checked={selected.has(rowKey(row.original))}
                        onCheckedChange={() => toggleRow(rowKey(row.original))} />
                    </TableCell>
                  ) : null}
                  {row.getAllCells().map((cell) => {
                    const meta = cell.column.columnDef.meta || {};
                    return (
                      <TableCell key={cell.id}
                        className={cn(meta.align === "right" && "text-right tabular-nums",
                          "align-middle text-sm", meta.sticky && "col-actions",
                          meta.className)}>
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}

      {footer}
      {onQueryChange && total > 0 ? (
        <Pagination total={total} skip={query.skip || 0} limit={query.limit || 25}
          testId={testIds.pagination || DT.pagination} label={label}
          onChange={(p) => onQueryChange(p)} sizes={[10, 25, 50, 100]} />
      ) : null}
    </div>
  );
}
