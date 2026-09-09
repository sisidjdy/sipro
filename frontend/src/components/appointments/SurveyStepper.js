import React from "react";
import { Check } from "lucide-react";
import { SURVEY_STAGES } from "@/constants/testIds";

/** Kelompokkan checklist survey per tahap (survey lama tanpa stage_key → satu tahap umum). */
export function groupByStage(survey) {
  const stages = (survey?.stages || []).length
    ? [...survey.stages].sort((a, b) => a.order - b.order)
    : [{ key: "__all__", order: 1, name: "Pemeriksaan lokasi", description: null }];
  const items = survey?.checklist || [];
  return stages.map((s) => ({
    ...s,
    items: items.map((c, idx) => ({ ...c, idx }))
      .filter((c) => (s.key === "__all__" ? true : c.stage_key === s.key)),
  }));
}

export function stageDone(stage) {
  return stage.items.length > 0 && stage.items.every((c) => c.status !== "na");
}

export function SurveyStepper({ groups, current, onSelect }) {
  return (
    <ol data-testid={SURVEY_STAGES.stepper} className="flex flex-wrap items-center gap-1.5">
      {groups.map((g, i) => {
        const active = i === current;
        const done = stageDone(g);
        return (
          <li key={g.key} className="flex items-center gap-1.5">
            <button type="button" data-testid={SURVEY_STAGES.step} data-stage={g.key} aria-current={active ? "step" : undefined}
              onClick={() => onSelect(i)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                active ? "border-primary bg-primary text-primary-foreground" : done ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "bg-card text-muted-foreground hover:bg-secondary"}`}>
              <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${active ? "bg-primary-foreground text-primary" : done ? "bg-emerald-600 text-white" : "bg-secondary"}`}>
                {done && !active ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              <span className="max-w-[9rem] truncate">{g.name}</span>
            </button>
            {i < groups.length - 1 ? <span className="h-px w-3 bg-border" /> : null}
          </li>
        );
      })}
    </ol>
  );
}
