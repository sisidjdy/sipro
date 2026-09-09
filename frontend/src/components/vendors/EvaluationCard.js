import React from "react";
import { Award, HelpCircle } from "lucide-react";

import RefLabel from "@/components/patterns/RefLabel";
import { VENDOR as T } from "@/constants/testIds";

const GRADE_TONE = {
  A: "border-emerald-200 bg-emerald-50 text-emerald-900",
  B: "border-sky-200 bg-sky-50 text-sky-900",
  C: "border-amber-200 bg-amber-50 text-amber-900",
  D: "border-rose-200 bg-rose-50 text-rose-900",
  missing_data: "border-slate-200 bg-slate-50 text-slate-700",
};

/**
 * EvaluationCard (Fase 48D) — rapor vendor/subkon yang DIHITUNG DARI BUKTI.
 *
 * Aturan yang dijaga: komponen tanpa sumber data TIDAK diberi angka 0 (yang akan menghukum
 * rekanan atas data yang memang belum pernah kita kumpulkan). Komponen seperti itu
 * ditampilkan sebagai “belum ada data” beserta sebabnya, dan skor akhir hanya menimbang
 * komponen yang punya bukti.
 */
export default function EvaluationCard({ evaluation, compact = false }) {
  if (!evaluation) return null;
  const grade = evaluation.grade || "missing_data";
  const tone = GRADE_TONE[grade] || GRADE_TONE.missing_data;
  const comps = Object.entries(evaluation.components || {});
  return (
    <div data-testid={T.evalCard} data-grade={grade}
      className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="section-title">
            {evaluation.vendor_name || "Rekanan"}</p>
          <p className="text-xs text-muted-foreground">{evaluation.detail}</p>
        </div>
        <div data-testid={T.evalScore} data-score={evaluation.score ?? ""}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${tone}`}>
          {grade === "missing_data"
            ? <HelpCircle className="h-4 w-4" /> : <Award className="h-4 w-4" />}
          <span className="text-sm font-semibold">
            {evaluation.score === null || evaluation.score === undefined
              ? "Belum ada data"
              : `${evaluation.score} · `}
          </span>
          {evaluation.score !== null && evaluation.score !== undefined ? (
            <RefLabel group="eval_grade" value={grade} />
          ) : null}
        </div>
      </div>

      {compact ? null : (
        <div className="grid gap-2 sm:grid-cols-2">
          {comps.map(([key, c]) => (
            <div key={key}
              className={`rounded-lg border p-3 text-sm ${c.score === null
                ? "border-dashed bg-secondary/40 text-muted-foreground" : "bg-card"}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium">
                  <RefLabel group="eval_criteria" value={key} />
                </span>
                <span className="tabular-nums">
                  {c.score === null ? "belum ada data" : c.score}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{c.detail}</p>
              {(c.late || []).length ? (
                <ul className="mt-1 list-disc pl-4 text-[11px] text-amber-800">
                  {c.late.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {(evaluation.missing || []).length ? (
        <p data-testid={T.evalMissing}
          className="rounded-lg border border-dashed bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          Belum bisa dinilai: {evaluation.missing.join(", ")} — skor akhir hanya menimbang
          komponen yang punya bukti, bukan menganggapnya nol.
        </p>
      ) : null}
    </div>
  );
}
