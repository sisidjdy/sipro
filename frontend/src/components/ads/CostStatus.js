import React from "react";
import { AlertTriangle, CheckCircle2, CircleSlash } from "lucide-react";

import { cn } from "@/lib/utils";
import { useReference } from "@/context/ReferenceContext";
import { ADS } from "@/constants/testIds";

/**
 * CostStatus & SourceLabels — dua penanda KEJUJURAN ANGKA yang dipakai di semua layar biaya
 * iklan (spec `docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §1 & §8).
 *
 * Kenapa ini komponen, bukan teks biasa di tiap tabel: aturannya harus sama di mana pun.
 * — `missing`  : biaya BELUM diinput → CPL/CAC/ROAS tidak boleh ditampilkan sebagai 0.
 * — `partial`  : baru sebagian hari terisi → angkanya masih akan berubah, dan itu harus
 *                dikatakan (berapa hari terisi dari berapa hari yang seharusnya).
 * — `complete` : semua hari dalam rentang punya angka.
 * Label kelompok & label sumber angka (manual/csv/api) diambil dari SSOT `/api/reference`,
 * jadi tidak ada kosakata yang diketik ulang di layar.
 */
const ICON = { complete: CheckCircle2, partial: AlertTriangle, missing: CircleSlash };
const TONE = {
  complete: "bg-emerald-50 text-emerald-700 border-emerald-200",
  partial: "bg-amber-50 text-amber-800 border-amber-200",
  missing: "bg-rose-50 text-rose-700 border-rose-200",
};

export function CostStatusBadge({ status, spendDays = null, expectedDays = null, className }) {
  const { labelOf } = useReference();
  const key = status || "missing";
  const Icon = ICON[key] || CircleSlash;
  const detail = key === "partial" && spendDays !== null && expectedDays
    ? ` (${spendDays}/${expectedDays} hari)` : "";
  return (
    <span data-testid={ADS.costBadge} data-cost-status={key}
      className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs",
        TONE[key] || TONE.missing, className)}>
      <Icon className="h-3 w-3" />
      {labelOf("ads_cost_status", key)}{detail}
    </span>
  );
}

/** Label asal angka biaya (manual / impor CSV / tarikan API) — wajib tampil di tabel & grafik. */
export function SourceLabels({ sources = [], className }) {
  const { labelOf } = useReference();
  if (!sources || !sources.length) {
    return <span className={cn("text-xs text-muted-foreground", className)}>belum ada angka</span>;
  }
  return (
    <span data-testid={ADS.sourceLabel} className={cn("flex flex-wrap gap-1", className)}>
      {sources.map((s) => (
        <span key={s} data-source={s}
          className="rounded border bg-secondary px-1.5 py-0.5 text-[11px] text-secondary-foreground">
          {labelOf("ad_spend_source", s)}
        </span>
      ))}
    </span>
  );
}

/**
 * Angka metrik biaya. Bila nilainya null, TIDAK menampilkan "0" — menampilkan alasan.
 * Ini inti pelajaran Fase 36/37: nol dan "belum ada data" adalah dua hal yang berbeda.
 */
export function CostMetric({ value, render, note = "data biaya belum lengkap", className }) {
  if (value === null || value === undefined) {
    return (
      <span title={note} className={cn("text-xs italic text-muted-foreground", className)}>
        belum lengkap
      </span>
    );
  }
  return <span className={cn("tabular-nums", className)}>{render ? render(value) : value}</span>;
}
