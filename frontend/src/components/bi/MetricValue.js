import React from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Info } from "lucide-react";

import { cn } from "@/lib/utils";
import { useReference } from "@/context/ReferenceContext";
import { formatCompact, formatIDR, formatNumber } from "@/utils/formatters";
import { BI } from "@/constants/testIds";

/**
 * MetricValue & MetricState — cara BAKU menggambar angka BI (Fase 44).
 *
 * Aturan yang dipegang komponen ini (kelanjutan pelajaran Fase 36/37/43):
 *   - `kosong`   : datanya TIDAK ADA → tulis “belum ada data”, JANGAN gambar 0. Menggambar 0
 *                  membuat orang menyimpulkan “hasilnya nol” padahal yang benar adalah
 *                  “kita belum tahu” — dua kesimpulan yang sangat berbeda untuk keputusan.
 *   - `sebagian` : angkanya boleh tampil TAPI wajib berlabel + menyebut cakupannya
 *                  (“dari 40 dari 47 lead”), supaya tidak dibaca sebagai angka final.
 *   - `lengkap`  : tampil biasa.
 * Label status diambil dari SSOT `metric_state` sehingga tidak ada kosakata yang diketik ulang.
 */
const ICON = { lengkap: CheckCircle2, sebagian: AlertTriangle, kosong: CircleSlash };
const TONE = {
  lengkap: "bg-emerald-50 text-emerald-700 border-emerald-200",
  sebagian: "bg-amber-50 text-amber-800 border-amber-200",
  kosong: "bg-slate-100 text-slate-600 border-slate-300",
};

export function formatMetric(value, unit) {
  if (value === null || value === undefined) return null;
  if (unit === "idr") return formatIDR(value);
  if (unit === "pct") return `${formatNumber(value)}%`;
  if (unit === "days") return `${formatNumber(value)} hari`;
  if (unit === "hours") return `${formatNumber(value)} jam`;
  if (unit === "ratio") return `${formatNumber(value)}×`;
  if (unit === "text") return String(value);
  return formatNumber(value);
}

/** Versi ringkas untuk ruang sempit: Rp 212.500.000 → "Rp 212,5 jt". */
export function formatMetricCompact(value, unit) {
  if (value === null || value === undefined) return null;
  if (unit === "idr") return `Rp ${formatCompact(value)}`;
  if (["pct", "days", "hours", "ratio", "text"].includes(unit)) return formatMetric(value, unit);
  return formatCompact(value);
}

export function MetricStateBadge({ state, coverage, className }) {
  const { labelOf } = useReference();
  const key = state || "kosong";
  const Icon = ICON[key] || CircleSlash;
  const detail = key === "sebagian" && coverage
    ? ` (${formatNumber(coverage.rows)}/${formatNumber(coverage.total)})` : "";
  return (
    <span data-testid={BI.cardState} data-state={key}
      className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]",
        TONE[key] || TONE.kosong, className)}>
      <Icon className="h-3 w-3" />
      {labelOf("metric_state", key)}{detail}
    </span>
  );
}

export function MetricValue({ metric, className }) {
  const text = formatMetric(metric?.value, metric?.unit);
  if (text === null) {
    return (
      <span data-testid={BI.cardValue} data-empty="true"
        className={cn("text-sm italic text-muted-foreground", className)}
        title={metric?.note || "data belum ada"}>
        belum ada data
      </span>
    );
  }
  return (
    <span data-testid={BI.cardValue}
      className={cn("font-heading text-2xl font-semibold tabular-nums leading-none", className)}>
      {text}
    </span>
  );
}

/** Catatan kejujuran di bawah angka: apa yang belum ada / apa batas cakupannya. */
export function MetricNote({ metric, className }) {
  if (!metric?.note && !(metric?.missing || []).length) return null;
  return (
    <p className={cn("flex items-start gap-1 text-[11px] text-muted-foreground", className)}>
      <Info className="mt-0.5 h-3 w-3 shrink-0" />
      <span>{metric.note || (metric.missing || []).join("; ")}</span>
    </p>
  );
}
