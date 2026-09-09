import React from "react";
import { Columns3, Download, RefreshCw, Rows3, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DT } from "@/constants/testIds";

/**
 * DataTableToolbar — baris alat di atas tabel: cari · filter (slot) · pilih kolom ·
 * kerapatan baris · ekspor · muat ulang. Dipisah dari DataTable supaya keduanya tetap
 * kecil & mudah dibaca (batas compliance komponen).
 */
export default function DataTableToolbar({
  query = {}, onQueryChange, columns = [], hidden, onToggleColumn, filters = null,
  searchPlaceholder = "Cari…", onExport, exportDisabled, dense, onToggleDense, onRefresh,
  testIds = {}, total = 0, rowsShown = 0, label = "baris",
}) {
  const searchId = `${testIds.search || DT.search}-input`;
  return (
    <div className="space-y-2">
      <div className="toolbar">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input id={searchId} data-testid={testIds.search || DT.search}
            className="search-field pl-9" aria-label={searchPlaceholder}
            placeholder={searchPlaceholder} value={query.q || ""}
            onChange={(e) => onQueryChange?.({ q: e.target.value })} />
        </div>
        {filters}
        <span aria-hidden="true" className="mx-0.5 hidden h-6 w-px bg-border sm:block" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button data-testid={testIds.columns || DT.columns} variant="outline" size="sm">
              <Columns3 className="mr-1.5 h-4 w-4" /> Kolom
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-popover">
            <DropdownMenuLabel>Tampilkan kolom</DropdownMenuLabel>
            {columns.map((c) => (
              <DropdownMenuCheckboxItem key={c.key} checked={!hidden.has(c.key)}
                data-testid={`${DT.columnOption}-${c.key}`}
                onCheckedChange={() => onToggleColumn(c.key)}>
                {c.header}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button data-testid={testIds.density || DT.density} variant="outline" size="sm"
          aria-label={dense ? "Baris longgar" : "Baris padat"}
          title={dense ? "Baris longgar" : "Baris padat"} onClick={onToggleDense}>
          <Rows3 className="h-4 w-4" />
        </Button>
        <Button data-testid={testIds.export || DT.export} variant="outline" size="sm"
          onClick={onExport} disabled={exportDisabled}>
          <Download className="mr-1.5 h-4 w-4" /> CSV
        </Button>
        {onRefresh ? (
          <Button data-testid={testIds.refresh || DT.refresh} variant="outline" size="sm"
            aria-label="Muat ulang data" title="Muat ulang" onClick={onRefresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
      <p data-testid={testIds.total || DT.total} className="text-xs text-muted-foreground">
        Menampilkan <span className="font-medium text-foreground tabular-nums">{rowsShown}</span>
        {" "}dari <span className="font-medium text-foreground tabular-nums">{total}</span> {label}
        {query.q ? <> · pencarian “{query.q}”</> : null}
      </p>
    </div>
  );
}
