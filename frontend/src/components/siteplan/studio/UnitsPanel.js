import React, { useState } from "react";
import { ArrowRight } from "lucide-react";

import { Input } from "@/components/ui/input";
import { STUDIO } from "@/constants/testIds";

/** Daftar unit yang belum punya bentuk — klik untuk menjadikannya giliran berikutnya
 *  pada mode berurutan, atau memetakan langsung ke bentuk yang sedang dipilih. */
export default function UnitsPanel({ s }) {
  const [q, setQ] = useState("");
  const rows = s.unmappedUnits.filter((u) => !q || String(u.code).toLowerCase().includes(q.toLowerCase()));
  const next = s.seqQueue[0] || s.unmappedUnits[0];
  const sel = s.selected;
  const canDirect = sel && sel.kind === "lot" && !sel.unit_id;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span data-testid={STUDIO.statUnmappedUnits}>{s.unmappedUnits.length} unit belum punya bentuk</span>
        {s.tool === "sequence" && next ? (
          <span data-testid={STUDIO.seqNext} className="rounded bg-blue-50 px-1.5 py-0.5 font-semibold text-blue-700">
            berikutnya: {next.code}
          </span>
        ) : null}
      </div>
      <Input data-testid={STUDIO.unitSearch} value={q} placeholder="Cari kode unit…" onChange={(e) => setQ(e.target.value)} />
      <p className="text-[11px] text-muted-foreground">
        {canDirect ? `Klik unit untuk memetakan ke bentuk terpilih (${sel.label || sel.shape_id}).`
          : "Klik unit untuk menjadikannya giliran berikutnya di mode Berurutan."}
      </p>
      <div className="max-h-[48vh] space-y-1 overflow-y-auto pr-1">
        {rows.map((u) => (
          <button key={u.id} type="button" data-testid={STUDIO.unitRow}
            onClick={() => (canDirect ? s.assignUnit(sel.shape_id, u.id)
              : s.setSeqQueue((qq) => [u, ...qq.filter((x) => x.id !== u.id)]))}
            className={`flex w-full items-center justify-between rounded-md border px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent ${
              next?.id === u.id ? "border-blue-300 bg-blue-50" : ""}`}>
            <span className="font-mono font-semibold">{u.code}</span>
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">{u.type || "-"}<ArrowRight className="h-3 w-3" /></span>
          </button>
        ))}
        {!rows.length ? <p className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">Semua unit sudah terpetakan.</p> : null}
      </div>
    </div>
  );
}
