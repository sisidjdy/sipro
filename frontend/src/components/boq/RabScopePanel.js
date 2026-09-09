import React, { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import AddBoQItemDialog from "@/components/boq/AddBoQItemDialog";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { formatIDR, formatNumber } from "@/utils/formatters";
import { P80 } from "@/constants/testIds";

const TITLE = { fasum: "RAB Fasum / Fasos", umum: "RAB Umum (perizinan, land clearing, overhead, pemasaran)" };

/** Item RAB proyek untuk lingkup fasum/fasos atau umum — dikelompokkan per fasilitas / jenis biaya. */
export default function RabScopePanel({ projectId, scope, onChanged }) {
  const { can } = useAuth();
  const { labelOf } = useReference();
  const canManage = can("boq", "create");
  const [items, setItems] = useState([]);
  const [opts, setOpts] = useState({ facilities: [], umum_kinds: [] });
  const [phases, setPhases] = useState({});
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(() => {
    api.get("/boq/items", { params: { project_id: projectId, scope } }).then((r) => setItems(r.data.data || [])).catch(() => {});
    api.get("/rab/options").then((r) => setOpts(r.data.data)).catch(() => {});
    if (scope === "fasum") api.get(`/construction/project/${projectId}/phases`).then((r) => setPhases(Object.fromEntries((r.data.data || []).map((p) => [p.id, p.name])))).catch(() => {});
  }, [projectId, scope]);
  useEffect(() => { load(); }, [load]);

  const kinds = scope === "fasum" ? opts.facilities : opts.umum_kinds;
  const label = (code) => kinds.find((k) => k.code === code)?.label || code || "Lainnya";
  const groups = items.reduce((acc, it) => { (acc[it.facility || "lainnya"] ||= []).push(it); return acc; }, {});
  const total = items.reduce((s, it) => s + (it.amount || 0), 0);
  const del = async (id) => {
    try { await api.delete(`/boq/items/${id}`); toast.success("Item dihapus."); load(); onChanged && onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus item."); }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><p className="text-sm font-semibold">{TITLE[scope]}</p>
          <p className="text-xs text-muted-foreground">Total {formatIDR(total)} · {items.length} item · dialokasikan ke HPP unit sesuai metode alokasi proyek.</p></div>
        {canManage ? <Button data-testid={scope === "fasum" ? P80.fasumAddBtn : P80.umumAddBtn} size="sm" onClick={() => setAddOpen(true)}><Plus className="mr-1.5 h-4 w-4" /> Tambah Item</Button> : null}
      </div>
      {!items.length ? (
        <EmptyState icon={Plus} title={`Belum ada item ${scope === "fasum" ? "fasum/fasos" : "biaya umum"}`}
          description={scope === "fasum" ? "Jalan, drainase, gerbang & pos jaga, taman, masjid, PJU, air bersih, IPAL, TPS — tautkan ke fase konstruksi proyek agar bisa dikendalikan lewat SPK." : "Perizinan, land clearing/cut-fill, overhead proyek, pemasaran."}
          actionLabel={canManage ? "Tambah Item" : undefined} onAction={() => setAddOpen(true)} />
      ) : Object.entries(groups).map(([fac, rows]) => (
        <div key={fac} className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <div className="flex items-center justify-between border-b bg-secondary px-3 py-1.5 text-xs font-semibold">
            <span>{label(fac)}</span><span className="tabular-nums">{formatIDR(rows.reduce((s, r) => s + (r.amount || 0), 0))}</span></div>
          <Table>
            <TableHeader><TableRow><TableHead>Kode</TableHead><TableHead>Uraian</TableHead><TableHead>Kategori</TableHead>
              {scope === "fasum" ? <TableHead>Fase proyek</TableHead> : null}
              <TableHead className="text-right">Volume</TableHead><TableHead className="text-right">Harga satuan</TableHead><TableHead className="text-right">Jumlah</TableHead>{canManage ? <TableHead /> : null}</TableRow></TableHeader>
            <TableBody>
              {rows.map((it) => (
                <TableRow key={it.id} data-testid={P80.scopeRow}>
                  <TableCell className="font-medium">{it.cost_code || "-"}</TableCell>
                  <TableCell className="text-sm">{it.description}</TableCell>
                  <TableCell className="text-sm">{labelOf("work_category", it.category)}</TableCell>
                  {scope === "fasum" ? <TableCell className="text-xs">{it.phase_id ? phases[it.phase_id] || "fase" : <span className="text-amber-700">tanpa fase</span>}</TableCell> : null}
                  <TableCell className="text-right tabular-nums text-sm">{formatNumber(it.quantity)} {it.uom}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(it.unit_price)}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{formatIDR(it.amount)}</TableCell>
                  {canManage ? <TableCell><Button variant="ghost" size="icon" className="h-8 w-8 text-rose-600" aria-label={`Hapus ${it.description}`} onClick={() => del(it.id)}><Trash2 className="h-4 w-4" /></Button></TableCell> : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
      <AddBoQItemDialog projectId={projectId} scope={scope} open={addOpen} onOpenChange={setAddOpen} onDone={() => { load(); onChanged && onChanged(); }} />
    </div>
  );
}
