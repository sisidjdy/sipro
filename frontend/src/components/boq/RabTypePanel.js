import React, { useCallback, useEffect, useState } from "react";
import { Home, Package, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P80 } from "@/constants/testIds";
import RabTemplateDialog from "./RabTemplateDialog";

function TemplateTable({ kind, rows, canManage, onEdit }) {
  const isType = kind === "unit_type";
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <Table>
        <TableHeader><TableRow>
          <TableHead>{isType ? "Tipe unit" : "Add-on"}</TableHead>
          {isType ? <TableHead className="text-right">Unit terdaftar</TableHead> : <TableHead>Mode harga</TableHead>}
          <TableHead className="text-right">RAB / {isType ? "unit" : "add-on"}</TableHead>
          <TableHead className="text-right">Harga jual</TableHead>
          <TableHead className="text-right">Margin</TableHead>
          {canManage ? <TableHead /> : null}
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.ref_code} data-testid={isType ? P80.typeRow : P80.addonRow} data-code={r.ref_code}>
              <TableCell><span className="font-medium">{r.ref_code}</span> <span className="text-sm text-muted-foreground">{r.name}</span>
                {!r.items ? <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-800">belum ada RAB</span> : null}
                {isType && r.step_mismatch ? (
                  <span data-testid={P80.typeMismatchBadge} data-code={r.ref_code} className="ml-2 rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-800"
                    title={r.has_schedule_template ? "Kode langkah baris RAB tidak ada di template jadwal tipe ini" : "Tipe ini belum punya template jadwal aktif, padahal RAB menautkan kode langkah"}>
                    {r.step_mismatch} langkah tak sinkron jadwal
                  </span>
                ) : null}
                {isType && r.steps_without_rab ? (
                  <span data-testid={P80.typeNoRabBadge} data-code={r.ref_code} className="ml-2 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-800"
                    title="Langkah jadwal tipe ini belum punya baris RAB — biaya langkah itu tidak masuk anggaran unit">
                    {r.steps_without_rab} langkah tanpa RAB
                  </span>
                ) : null}</TableCell>
              {isType ? <TableCell className="text-right tabular-nums text-sm">{r.units_count}</TableCell>
                : <TableCell className="text-sm">{r.pricing_mode} {r.uom ? `· ${r.uom}` : ""}</TableCell>}
              <TableCell className="text-right tabular-nums font-medium">{formatIDR(r.total)}{r.version > 1 ? <span className="ml-1 rounded bg-secondary px-1 text-[10px] font-normal text-muted-foreground" title="Versi RAB">v{r.version}</span> : null}</TableCell>
              <TableCell className="text-right tabular-nums text-sm">{formatIDR(isType ? r.base_price : r.unit_price)}</TableCell>
              <TableCell className={`text-right tabular-nums text-sm ${r.margin != null && r.margin < 0 ? "text-rose-600" : ""}`}>{r.margin == null ? "—" : formatIDR(r.margin)}</TableCell>
              {canManage ? <TableCell className="text-right">
                <Button data-testid={isType ? P80.typeEditBtn : P80.addonEditBtn} size="sm" variant="outline" onClick={() => onEdit(r)}><Pencil className="mr-1 h-3.5 w-3.5" /> RAB</Button>
              </TableCell> : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** RAB tertempel pada TIPE unit + RAB add-on: satu sumber untuk semua proyek. */
export default function RabTypePanel({ onChanged }) {
  const { can } = useAuth();
  const canManage = can("boq", "update");
  const [types, setTypes] = useState([]);
  const [addons, setAddons] = useState([]);
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => {
    api.get("/rab/templates/unit_type").then((r) => setTypes(r.data.data || [])).catch(() => {});
    api.get("/rab/templates/addon").then((r) => setAddons(r.data.data || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Home className="h-4 w-4" /> RAB per tipe unit</h3>
        <p className="text-xs text-muted-foreground">Angka RAB hidup di tipe (satu sumber). Ringkasan proyek = RAB tipe × jumlah unit tipe itu; SPK unit mengambil baris dari sini.</p>
        <TemplateTable kind="unit_type" rows={types} canManage={canManage} onEdit={(r) => setEdit({ kind: "unit_type", target: r })} />
      </section>
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Package className="h-4 w-4" /> RAB add-on (spek tambahan)</h3>
        <p className="text-xs text-muted-foreground">HPP tiap add-on. Saat pembeli menambah add-on, SPK add-on (atau SPK unit + add-on) mengambil biaya dari sini.</p>
        <TemplateTable kind="addon" rows={addons} canManage={canManage} onEdit={(r) => setEdit({ kind: "addon", target: r })} />
      </section>
      <RabTemplateDialog kind={edit?.kind} target={edit?.target} candidates={edit?.kind === "unit_type" ? types : addons} open={!!edit} onOpenChange={(v) => !v && setEdit(null)}
        onDone={() => { load(); onChanged && onChanged(); }} />
    </div>
  );
}
