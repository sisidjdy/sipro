import React from "react";
import { ArrowUpRight, Lock } from "lucide-react";

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Count, Money, Pct, isNegative } from "@/components/budget/parts";
import { BUDGET } from "@/constants/testIds";

/**
 * TargetPeriodTable — rencana vs realisasi per bulan.
 *
 * Tiga hal yang WAJIB terlihat di tabel ini supaya target bisa dipercaya:
 *   1. bulan lampau bertanda **kunci** — angkanya tidak akan berubah lagi;
 *   2. **carry over** — kekurangan bulan sebelumnya yang dipindahkan, sehingga kenaikan
 *      target punya penjelasan angka, bukan kesan sistem mengarang;
 *   3. selisih (`gap`) dan pencapaian per bulan, bukan hanya total di akhir horizon.
 */
export default function TargetPeriodTable({ periods }) {
  const rows = periods || [];
  if (!rows.length) return null;
  return (
    <div data-testid={BUDGET.periodTable} className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <Table>
        <TableHeader><TableRow>
          <TableHead>Bulan</TableHead>
          <TableHead className="text-right">Rencana unit</TableHead>
          <TableHead className="text-right">Realisasi unit</TableHead>
          <TableHead className="text-right">Selisih</TableHead>
          <TableHead className="text-right">Pencapaian</TableHead>
          <TableHead className="text-right">Rencana pendapatan</TableHead>
          <TableHead className="text-right">Realisasi pendapatan</TableHead>
          <TableHead>Catatan</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.period} data-testid={BUDGET.periodRow}
              data-period={p.period} data-locked={p.locked ? "true" : "false"}>
              <TableCell className="whitespace-nowrap font-mono text-xs">
                <span className="inline-flex items-center gap-1">
                  {p.locked ? <Lock className="h-3 w-3 text-muted-foreground" /> : null}
                  {p.period}
                </span>
              </TableCell>
              <TableCell className="text-right text-sm font-medium">
                <Count value={p.unit_plan} />
              </TableCell>
              <TableCell className="text-right text-sm"><Count value={p.unit_actual} /></TableCell>
              <TableCell className={`text-right text-sm ${
                isNegative(p.gap) ? "text-rose-600"
                  : p.gap === null || p.gap === undefined ? "text-muted-foreground"
                    : "text-emerald-700"}`}>
                {p.gap === null || p.gap === undefined ? "–" : (p.gap > 0 ? `+${p.gap}` : p.gap)}
              </TableCell>
              <TableCell className="text-right text-sm">
                <Pct value={p.achievement_pct} />
              </TableCell>
              <TableCell className="text-right text-sm"><Money value={p.revenue_plan} /></TableCell>
              <TableCell className="text-right text-sm">
                <Money value={p.revenue_actual} />
              </TableCell>
              <TableCell className="max-w-[280px] text-[11px] text-muted-foreground">
                {p.carry_over ? (
                  <span data-testid={BUDGET.carryOver}
                    className="mr-1 inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-900">
                    <ArrowUpRight className="h-3 w-3" /> dipindahkan {p.carry_over} unit
                  </span>
                ) : null}
                {p.note}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
