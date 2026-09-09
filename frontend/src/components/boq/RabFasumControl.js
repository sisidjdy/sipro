import React from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatIDR } from "@/utils/formatters";
import { P81 } from "@/constants/testIds";

/** Kendali SPK fasum: termin kumulatif (disetujui/diajukan) vs progres fase konstruksi yang tertaut (= batas termin). */
export default function RabFasumControl({ rows }) {
  if (!rows?.length) return null;
  return (
    <div data-testid={P81.fasumControl} className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <p className="border-b bg-secondary px-3 py-1.5 text-xs font-semibold">Kendali fasum/fasos: termin SPK mengikuti progres fase konstruksi ({rows.length} SPK)</p>
      <Table>
        <TableHeader><TableRow>
          <TableHead>SPK</TableHead><TableHead>Fasilitas · fase tertaut</TableHead>
          <TableHead className="text-right">Nilai kontrak</TableHead><TableHead className="text-right">Progres fase (batas)</TableHead>
          <TableHead className="text-right">Termin disetujui</TableHead><TableHead>Keadaan</TableHead>
        </TableRow></TableHeader>
        <TableBody>{rows.map((r) => {
          const noPhase = !r.covered_value;
          return (
            <TableRow key={r.spk_id} data-testid={P81.fasumRow} data-spk={r.spk_number} data-over={r.over ? "1" : "0"} className={r.over ? "bg-rose-50/60" : ""}>
              <TableCell className="text-xs"><span className="font-medium">{r.spk_number}</span><br /><span className="text-muted-foreground">{r.subcontractor_name}</span></TableCell>
              <TableCell className="text-xs">
                {r.facilities.join(", ") || "—"}
                <div className="text-muted-foreground">
                  {r.phases.length ? r.phases.map((p) => <span key={p.phase_id} className="mr-2">{p.name} <b>{p.progress}%</b></span>) : "tanpa tautan fase — tidak dibatasi"}
                  {r.uncovered_value && r.covered_value ? <span className="text-amber-700"> · {formatIDR(r.uncovered_value)} tanpa fase</span> : null}
                </div>
              </TableCell>
              <TableCell className="text-right tabular-nums text-xs">{formatIDR(r.contract_value)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs">{noPhase ? "—" : `${r.cap_pct}%`}</TableCell>
              <TableCell className="text-right tabular-nums text-xs">{r.billed_pct}% <span className="text-muted-foreground">({formatIDR(r.billed_value)})</span>
                {r.pending_pct != null ? <div className="text-[10px] text-amber-700">diajukan {r.pending_pct}% · {r.pending_claim}</div> : null}</TableCell>
              <TableCell className="text-xs">
                {noPhase ? <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px]">tanpa kendali fase</span>
                  : r.over ? <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-800">melampaui progres fase</span>
                    : <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">sesuai · sisa {r.headroom_pct}%</span>}
              </TableCell>
            </TableRow>
          );
        })}</TableBody>
      </Table>
    </div>
  );
}
