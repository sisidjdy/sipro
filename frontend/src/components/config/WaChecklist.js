import React from "react";
import { CheckCircle2, Circle, Info } from "lucide-react";

import { P100 } from "@/constants/testIds";

/** WaChecklist — checklist go-live dengan diagnosa: setiap syarat merah menyebut APA yang harus dilakukan. */
export default function WaChecklist({ data }) {
  const items = data?.checklist || [];
  const blockers = items.filter((c) => c.blocking && !c.ok).length;
  return (
    <div className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <h3 className="section-title">Checklist go-live</h3>
      <ul className="space-y-2 text-sm">
        {items.map((c) => (
          <li key={c.key} data-testid={`${P100.checklistItem}-${c.key}`} data-ok={c.ok ? "1" : "0"} className="flex items-start gap-2">
            {c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />}
            <div className="min-w-0">
              <p className={c.ok ? "" : "text-muted-foreground"}>
                {c.label}{!c.blocking ? <span className="ml-1 text-[10px] uppercase text-muted-foreground">(opsional)</span> : null}
              </p>
              {!c.ok && c.fix ? (
                <p data-testid={`${P100.checklistFix}-${c.key}`} className="mt-0.5 flex gap-1 text-[11px] text-amber-800">
                  <Info className="mt-0.5 h-3 w-3 shrink-0" />{c.fix}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      <p data-testid={P100.goLiveState} className={`text-xs ${data?.go_live_ready ? "text-emerald-700" : "text-muted-foreground"}`}>
        {data?.go_live_ready ? "Semua syarat wajib terpenuhi — ubah Mode ke Live lalu Simpan."
          : `${blockers} syarat wajib belum terpenuhi — ikuti petunjuk di tiap baris.`}
      </p>
    </div>
  );
}
