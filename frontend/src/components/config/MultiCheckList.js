import React from "react";

import { Checkbox } from "@/components/ui/checkbox";

/**
 * MultiCheckList — pilih BANYAK nilai (proyek / tipe unit) untuk aturan harga.
 * Kosong = berlaku untuk semua; itu disebut jelas di layar, bukan dibiarkan tersirat.
 */
export default function MultiCheckList({ options = [], value = [], onChange, testId, allLabel, emptyText }) {
  const set = new Set(value || []);
  const toggle = (v) => {
    const next = new Set(set);
    if (next.has(v)) next.delete(v); else next.add(v);
    onChange([...next]);
  };
  return (
    <div data-testid={testId} className="rounded-md border bg-background">
      <div className="flex items-center justify-between border-b px-2.5 py-1.5 text-xs">
        <span className={set.size ? "text-muted-foreground" : "font-medium text-emerald-700"}>
          {set.size ? `${set.size} dipilih` : allLabel}
        </span>
        {set.size ? (
          <button type="button" className="text-primary hover:underline" onClick={() => onChange([])}>
            Pilih semua
          </button>
        ) : null}
      </div>
      <div className="max-h-36 overflow-y-auto p-1.5">
        {options.length ? options.map((o) => (
          <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-secondary/60">
            <Checkbox checked={set.has(o.value)} onCheckedChange={() => toggle(o.value)}
              aria-label={o.label} data-testid={`${testId}-${o.value}`} />
            <span className="truncate">{o.label}</span>
          </label>
        )) : <p className="px-1.5 py-1 text-xs text-muted-foreground">{emptyText}</p>}
      </div>
    </div>
  );
}
