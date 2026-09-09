import React from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import MoneyText from "@/components/patterns/MoneyText";
import { useReference } from "@/context/ReferenceContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import { ADS } from "@/constants/testIds";

const ROW_TONE = {
  new: "text-emerald-700", update: "text-sky-700", unchanged: "text-muted-foreground",
  rejected: "text-rose-700",
};

/**
 * ImportReport — satu tampilan laporan impor, dipakai DUA tempat: wizard impor (pratinjau)
 * dan Riwayat Impor (audit). Sengaja satu komponen supaya apa yang dilihat sebelum menyimpan
 * SAMA PERSIS dengan apa yang tercatat sesudahnya.
 *
 * Yang wajib terlihat: berapa baris masuk / diperbarui / sama / ditolak, dan untuk setiap
 * penolakan — ALASANNYA. Impor yang menolak baris tanpa memberi alasan memaksa orang menebak,
 * dan biasanya berakhir dengan mengubah berkas sampai “diterima” tanpa tahu apa yang salah.
 */
export default function ImportReport({ report, testId }) {
  const { labelOf } = useReference();
  if (!report) return null;
  const s = report.summary || {};
  const rows = report.rows || [];
  const applied = report.applied;

  return (
    <div data-testid={testId || ADS.importSummary} className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {/* Label ringkasan diambil dari SSOT `ads_row_status` (kecuali "Baris terbaca" yang
            bukan status baris) supaya kartu ringkasan dan tabel di bawahnya tidak bisa
            memakai kosakata yang berbeda saat labelnya diubah admin. */}
        {[
          ["total", "Baris terbaca", s.total],
          ["new", labelOf("ads_row_status", "new"), s.new],
          ["update", labelOf("ads_row_status", "update"), s.update],
          ["unchanged", labelOf("ads_row_status", "unchanged"), s.unchanged],
          ["rejected", labelOf("ads_row_status", "rejected"), s.rejected],
        ].map(([key, label, value]) => (
          <div key={key} data-summary={key} className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="font-heading text-lg font-semibold tabular-nums">{value || 0}</p>
          </div>
        ))}
      </div>
      <p className="text-sm">
        Total biaya baris yang lolos: <strong><MoneyText value={s.spend_total} /></strong>
        {report.status === "committed" && applied ? (
          <span className="ml-2 inline-flex items-center gap-1 text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            tersimpan: {applied.inserted} baru, {applied.updated} diperbarui,
            {" "}{applied.unchanged} sama
          </span>
        ) : null}
      </p>
      {report.error ? (
        <p className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3
          text-sm text-rose-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {report.error}
        </p>
      ) : null}
      {report.checksum ? (
        <p className="text-xs text-muted-foreground">
          Berkas: {report.filename} · sidik jari {String(report.checksum).slice(0, 12)}… ·
          {" "}oleh {report.imported_by} · {formatDateTimeWIB(report.created_at)}
        </p>
      ) : null}

      {rows.length ? (
        <div data-testid={ADS.importRowsTable}
          className="max-h-72 overflow-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted/70 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Baris</th>
                <th className="px-3 py-2 text-left">Hasil</th>
                <th className="px-3 py-2 text-left">Kampanye / tanggal</th>
                <th className="px-3 py-2 text-right">Biaya</th>
                <th className="px-3 py-2 text-left">Keterangan</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.line} data-testid={ADS.importRow} data-status={r.status}
                  className="border-t">
                  <td className="px-3 py-1.5 tabular-nums">{r.line}</td>
                  <td className={`px-3 py-1.5 font-medium ${ROW_TONE[r.status] || ""}`}>
                    {labelOf("ads_row_status", r.status)}
                  </td>
                  <td className="px-3 py-1.5">
                    {r.row
                      ? `${r.row.campaign_name} · ${r.row.date}`
                      : `${r.raw?.campaign_name || "?"} · ${r.raw?.date || "?"}`}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {r.row ? <MoneyText value={r.row.spend} /> : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-xs">
                    {r.reason ? <span className="text-rose-700">{r.reason}</span> : null}
                    {!r.reason && (r.diff || []).length ? (
                      <span className="text-sky-700">
                        {r.diff.map((d) => `${d.field}: ${d.before ?? "—"} → ${d.after ?? "—"}`)
                          .join("; ")}
                      </span>
                    ) : null}
                    {!r.reason && !(r.diff || []).length ? (
                      <span className="text-muted-foreground">—</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
