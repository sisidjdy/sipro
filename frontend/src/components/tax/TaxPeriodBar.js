import React from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Pemilih masa pajak (YYYY-MM) yang dipakai bersama semua panel pajak Fase 49.
 *
 * Kenapa ada tombol cepat: masa pajak yang PUNYA data diambil dari server, jadi pemakai tidak
 * perlu menebak bulan mana yang berisi — sekaligus mencegah layar menampilkan “nihil” untuk
 * bulan yang sebenarnya belum pernah ada transaksinya.
 */
export default function TaxPeriodBar({
  period, onChange, periods = [], inputId, inputTestId, quickTestId, onRefresh, children,
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="space-y-1">
        <Label className="text-xs" htmlFor={inputId}>Masa pajak (bulan)</Label>
        <Input id={inputId} type="month" className="w-[170px]" data-testid={inputTestId}
          value={period} onChange={(e) => onChange(e.target.value || period)} />
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {periods.slice(0, 6).map((p) => (
          <Button key={p} type="button" size="sm" className="h-8 text-xs"
            variant={p === period ? "default" : "outline"} data-testid={quickTestId} data-period={p}
            aria-label={`Pilih masa pajak ${p}`} onClick={() => onChange(p)}>
            {p}
          </Button>
        ))}
        {children}
        {onRefresh ? (
          <Button type="button" size="icon" variant="outline" aria-label="Muat ulang data pajak"
            title="Muat ulang" onClick={onRefresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}
