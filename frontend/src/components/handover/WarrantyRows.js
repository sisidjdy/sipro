import React from "react";
import { ShieldCheck } from "lucide-react";

import { formatDateWIB } from "@/utils/formatters";
import { P50 } from "@/constants/testIds";

const PILL = {
  aktif: "border-emerald-200 bg-emerald-50 text-emerald-800",
  hampir_habis: "border-amber-200 bg-amber-50 text-amber-900",
  habis: "border-slate-200 bg-slate-100 text-slate-600",
};

/**
 * Masa garansi per bagian pekerjaan (Fase 50A).
 *
 * Setelan lama hanya punya SATU angka “masa retensi/garansi bangunan” untuk semua
 * pekerjaan, padahal struktur bertahun dan finishing berbulan. Tabel ini menjawab
 * pertanyaan pembeli — “bagian ini masih garansi sampai kapan?” — dengan dasar yang bisa
 * diperiksa: lama bulan, tanggal mulai, tanggal habis, dan sisa harinya.
 */
export default function WarrantyRows({ rows = [], missing, detail, compact = false }) {
  if (missing) {
    return (
      <div data-testid={P50.warrantyMissing}
        className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-[13px] text-slate-700">
        {detail || "Rumah ini belum diserahterimakan, jadi masa garansi belum mulai — "
          + "belum ada data, bukan nol hari."}
      </div>
    );
  }
  if (!rows.length) return null;
  return (
    <div className="space-y-2">
      {!compact ? (
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <ShieldCheck className="h-4 w-4 text-primary" /> Masa garansi per bagian
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <table className="w-full text-[13px]">
          <thead className="bg-secondary/60 text-left text-[12px] text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Bagian</th>
              <th className="px-3 py-2">Lama</th>
              <th className="px-3 py-2">Mulai</th>
              <th className="px-3 py-2">Sampai</th>
              <th className="px-3 py-2">Keadaan</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.category} data-testid={P50.warrantyRow} data-state={r.state}
                className="border-t">
                <td className="px-3 py-2 font-medium">{r.label}</td>
                <td className="px-3 py-2 tabular-nums">{r.months} bulan</td>
                <td className="px-3 py-2 text-muted-foreground">{formatDateWIB(r.starts_at)}</td>
                <td className="px-3 py-2 text-muted-foreground">{formatDateWIB(r.expires_at)}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                    PILL[r.state] || PILL.habis}`}>
                    {r.state_label}
                  </span>
                  <span className="ml-1.5 text-[11px] text-muted-foreground">
                    {r.days_left >= 0 ? `sisa ${r.days_left} hari`
                      : `lewat ${Math.abs(r.days_left)} hari`}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail ? <p className="text-[12px] text-muted-foreground">{detail}</p> : null}
    </div>
  );
}
