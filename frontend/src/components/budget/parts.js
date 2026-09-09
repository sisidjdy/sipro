import React from "react";

import { cn } from "@/lib/utils";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR, formatNumber } from "@/utils/formatters";
import { BUDGET } from "@/constants/testIds";

/**
 * parts.js — potongan tampilan bersama layar Target & Anggaran (Fase 45).
 *
 * Satu aturan yang dipaksakan komponen-komponen ini: **nol dan "belum ada data" digambar
 * BERBEDA.** Kalau keduanya sama, proyek yang anggarannya belum diisi akan terlihat paling
 * hemat dan target yang belum dihitung akan terlihat sudah tercapai. Karena itu:
 *
 *   - `value === null / undefined`  → tulisan "belum ada data" (bukan Rp 0 / 0%)
 *   - `value === 0` yang SAH        → tetap digambar 0 (mis. target sudah tercapai)
 *
 * Semua label status diambil dari SSOT `/api/reference` (`budget_health`, `target_status`,
 * `budget_match_rule`, dst) — layar tidak pernah mengetik ulang label enum.
 */
export const EMPTY_TEXT = "belum ada data";

/** Angka negatif SUNGGUHAN (null bukan negatif). Dipakai untuk memilih warna, sehingga
 *  layar tidak perlu menulis `value ?? 0` — pola yang membuat \"belum ada data\" tergambar
 *  seperti nol dan dilarang gate `verify_budget_target.py`. */
export const isNegative = (value) => typeof value === "number" && value < 0;

export function Money({ value, className, tone }) {
  if (value === null || value === undefined) {
    return <span className="text-[11px] italic text-muted-foreground">{EMPTY_TEXT}</span>;
  }
  return (
    <span className={cn("tabular-nums", tone, className)}>{formatIDR(value)}</span>
  );
}

export function Pct({ value, className }) {
  if (value === null || value === undefined) {
    return <span className="text-[11px] italic text-muted-foreground">{EMPTY_TEXT}</span>;
  }
  return <span className={cn("tabular-nums", className)}>{formatNumber(value)}%</span>;
}

export function Count({ value, suffix }) {
  if (value === null || value === undefined) {
    return <span className="text-[11px] italic text-muted-foreground">{EMPTY_TEXT}</span>;
  }
  return <span className="tabular-nums">{formatNumber(value)}{suffix ? ` ${suffix}` : ""}</span>;
}

const HEALTH_STYLE = {
  aman: "border-emerald-200 bg-emerald-50 text-emerald-800",
  waspada: "border-amber-200 bg-amber-50 text-amber-900",
  overbudget: "border-rose-200 bg-rose-50 text-rose-800",
  kosong: "border-slate-200 bg-slate-50 text-slate-600",
};

/** Lencana status anggaran. Label dari SSOT `budget_health`, warna dari nilainya. */
export function HealthPill({ value, className, testId = BUDGET.healthPill }) {
  const { labelOf } = useReference();
  const key = String(value || "kosong");
  return (
    <span data-testid={testId} data-health={key}
      className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        HEALTH_STYLE[key] || HEALTH_STYLE.kosong, className)}>
      {labelOf("budget_health", key)}
    </span>
  );
}

const STATE_STYLE = {
  lengkap: "border-emerald-200 bg-emerald-50 text-emerald-800",
  sebagian: "border-amber-200 bg-amber-50 text-amber-900",
  kosong: "border-slate-200 bg-slate-50 text-slate-600",
};

/** Lencana kelengkapan angka — kosakata SAMA dengan Analitik & BI (`metric_state`). */
export function StateBadge({ value, className }) {
  const { labelOf } = useReference();
  const key = String(value || "kosong");
  return (
    <span data-state={key}
      className={cn("inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium",
        STATE_STYLE[key] || STATE_STYLE.kosong, className)}>
      {labelOf("metric_state", key)}
    </span>
  );
}

/** Daftar "apa yang belum ada" — ditulis apa adanya, bukan disembunyikan. */
export function MissingNote({ items, testId, title = "Yang belum lengkap" }) {
  const list = (items || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <div data-testid={testId}
      className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
      <p className="font-medium">{title}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-4">
        {list.map((m, i) => <li key={i}>{m}</li>)}
      </ul>
    </div>
  );
}

/** Bar proporsi exposure terhadap rencana. Tanpa rencana → tidak digambar sama sekali. */
export function ExposureBar({ exposure, planned, health }) {
  if (!planned) return null;
  const width = Math.min(100, Math.round((exposure / planned) * 100));
  const color = health === "overbudget" ? "bg-rose-500"
    : health === "waspada" ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-secondary">
      <div className={cn("h-full rounded-full", color)} style={{ width: `${width}%` }} />
    </div>
  );
}
