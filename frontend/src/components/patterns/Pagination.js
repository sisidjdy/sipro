import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { WORK } from "@/constants/testIds";

/**
 * Pagination — kontrol halaman ringkas & konsisten untuk semua daftar panjang.
 *
 * Sebelum Fase 29 banyak daftar memuat 50–500 baris sekaligus tanpa navigasi halaman:
 * pengguna harus menggulir sangat jauh dan permintaan jadi berat. Komponen ini memakai
 * kontrak `skip`/`limit` yang sudah didukung backend (`parse_pagination`).
 */
export default function Pagination({
  total = 0, skip = 0, limit = 20, onChange, sizes = [10, 20, 50],
  label = "data", testId = WORK.pagination,
}) {
  const from = total === 0 ? 0 : skip + 1;
  const to = Math.min(skip + limit, total);
  const canPrev = skip > 0;
  const canNext = to < total;
  if (!total) return null;

  return (
    <div data-testid={testId}
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
      <p data-testid={WORK.pageInfo} className="text-xs text-muted-foreground">
        Menampilkan <span className="font-medium text-foreground tabular-nums">{from}–{to}</span>
        {" "}dari <span className="font-medium text-foreground tabular-nums">{total}</span> {label}
      </p>
      <div className="flex items-center gap-2">
        <Select value={String(limit)}
          onValueChange={(v) => onChange({ skip: 0, limit: Number(v) })}>
          <SelectTrigger aria-label="Jumlah baris per halaman" className="h-8 w-32 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {sizes.map((n) => (
              <SelectItem key={n} value={String(n)}>{n} / halaman</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button data-testid={WORK.pagePrev} size="sm" variant="outline" disabled={!canPrev}
          aria-label="Halaman sebelumnya"
          onClick={() => onChange({ skip: Math.max(0, skip - limit), limit })}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button data-testid={WORK.pageNext} size="sm" variant="outline" disabled={!canNext}
          aria-label="Halaman berikutnya"
          onClick={() => onChange({ skip: skip + limit, limit })}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
