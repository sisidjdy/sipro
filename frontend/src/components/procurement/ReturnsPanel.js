import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PackageX, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import ProjectSelect from "@/components/construction/ProjectSelect";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { RETURNS as T } from "@/constants/testIds";

/**
 * ReturnsPanel (Fase 48B) — retur barang ke vendor.
 *
 * Sebelum ini penerimaan barang TIDAK BISA dibalik: barang rusak/salah kirim tetap tercatat
 * sebagai “diterima” sehingga stok gudang dan 3-way match sama-sama berbohong. Retur di sini
 * menurunkan stok DAN nilai diterima pada PO — dan ditolak bila akan membuat nilai diterima
 * jatuh di bawah nilai yang sudah ditagih (harus lewat nota koreksi tagihan dulu).
 */
export default function ReturnsPanel() {
  const { can } = useAuth();
  const canCreate = can("procurement", "create");
  const [projectId, setProjectId] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/procurement/returns",
        { params: { project_id: projectId || undefined } });
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data retur.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const s = data?.summary;
  return (
    <div data-testid={T.panel} className="space-y-4">
      {s ? (
        <div className="grid grid-cols-2 gap-3">
          <MetricCard label="Retur tercatat" value={s.total} tone="primary" />
          <MetricCard label="Nilai dikembalikan" value={s.value} tone="rose" format="idr" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <ProjectSelect value={projectId} onChange={setProjectId} testId="returns-project-select" />
        {canCreate ? (
          <Button data-testid={T.addBtn} size="sm" onClick={() => setOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Catat retur
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={2} /> : error ? <ErrorState message={error} onRetry={load} />
        : !data?.data?.length ? (
          <EmptyState icon={PackageX} title="Belum ada retur barang"
            description={"Barang yang rusak, salah kirim, atau kelebihan terima dikembalikan di "
              + "sini — stok gudang dan nilai penerimaan PO ikut turun otomatis."} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Nomor</TableHead><TableHead>PO / GRN</TableHead>
                <TableHead>Vendor</TableHead><TableHead>Sebab</TableHead>
                <TableHead className="text-right">Nilai</TableHead>
                <TableHead>Alasan</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((r) => (
                  <TableRow key={r.id} data-testid={T.row}>
                    <TableCell>
                      <p className="font-mono text-xs">{r.return_number}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {formatDateWIB(r.created_at)}</p>
                    </TableCell>
                    <TableCell className="text-sm">
                      <p className="font-mono text-xs">{r.po_number}</p>
                      <p className="text-[11px] text-muted-foreground">{r.grn_number}</p>
                    </TableCell>
                    <TableCell className="text-sm">{r.vendor}</TableCell>
                    <TableCell className="text-sm">
                      <RefLabel group="return_kind" value={r.kind} /></TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatIDR(r.returned_value)}</TableCell>
                    <TableCell className="max-w-xs text-xs text-muted-foreground">
                      {r.reason}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

      <ReturnDialog open={open} onOpenChange={setOpen} projectId={projectId}
        onDone={() => { setOpen(false); load(); }} />
    </div>
  );
}

function ReturnDialog({ open, onOpenChange, projectId, onDone }) {
  const [pos, setPos] = useState([]);
  const [poId, setPoId] = useState("");
  const [grns, setGrns] = useState([]);
  const [grnId, setGrnId] = useState("");
  const [kind, setKind] = useState("rusak");
  const [qty, setQty] = useState({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPoId(""); setGrnId(""); setQty({}); setReason(""); setKind("rusak");
    api.get("/procurement/pos", { params: { project_id: projectId || undefined } })
      .then((r) => setPos((r.data.data || []).filter(
        (p) => ["partially_received", "received", "closed"].includes(p.status))))
      .catch(() => setPos([]));
  }, [open, projectId]);

  useEffect(() => {
    if (!poId) { setGrns([]); return; }
    api.get("/procurement/grns", { params: { po_id: poId } })
      .then((r) => setGrns(r.data.data || [])).catch(() => setGrns([]));
  }, [poId]);

  const grn = grns.find((g) => g.id === grnId);

  const submit = async () => {
    const items = Object.entries(qty)
      .filter(([, v]) => Number(v) > 0)
      .map(([idx, v]) => ({ grn_item_index: Number(idx), qty_returned: Number(v) }));
    if (!grnId || !items.length) {
      toast.error("Pilih penerimaan dan isi jumlah yang dikembalikan."); return;
    }
    if (reason.trim().length < 10) {
      toast.error("Alasan retur minimal 10 huruf — ini mengubah stok dan nilai penerimaan.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/procurement/returns",
        { grn_id: grnId, kind, items, reason: reason.trim() });
      toast.success("Retur tercatat — stok & nilai penerimaan PO ikut turun.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencatat retur.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.dialog} className="max-h-[88vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Catat retur barang</DialogTitle>
          <DialogDescription>
            Mengembalikan barang yang sudah diterima. Stok keluar, nilai diterima pada PO turun,
            dan seluruhnya berjejak dengan alasan.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Purchase Order</Label>
            <Select value={poId} onValueChange={setPoId}>
              <SelectTrigger data-testid={T.poSelect}>
                <SelectValue placeholder="Pilih PO yang sudah ada penerimaan…" /></SelectTrigger>
              <SelectContent>
                {pos.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.po_number} · {p.vendor} ({formatIDR(p.received_value)} diterima)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {poId && !pos.length ? null : null}
          </div>
          <div className="space-y-1.5">
            <Label>Penerimaan (GRN)</Label>
            <Select value={grnId} onValueChange={setGrnId} disabled={!grns.length}>
              <SelectTrigger data-testid={T.grnSelect}>
                <SelectValue placeholder={grns.length ? "Pilih penerimaan…"
                  : "Pilih PO dulu"} /></SelectTrigger>
              <SelectContent>
                {grns.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.grn_number} · {formatIDR(g.received_value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {grn ? (
            <div className="space-y-1.5 rounded-lg border bg-secondary/40 p-3">
              <p className="text-xs font-medium">Jumlah yang dikembalikan</p>
              {(grn.items || []).map((it, i) => {
                const sisa = Number(it.qty_received || 0) - Number(it.returned_qty || 0);
                return (
                  <div key={i} className="flex items-center justify-between gap-2 text-sm">
                    <div className="min-w-0 flex-1">
                      <p className="truncate">{it.description}</p>
                      <p className="text-[11px] text-muted-foreground">
                        diterima {it.qty_received} {it.uom} · sisa bisa diretur {sisa} {it.uom}
                      </p>
                    </div>
                    <Input data-testid={T.qty} type="number" min="0" max={sisa} step="0.01"
                      className="w-24" value={qty[i] ?? ""}
                      aria-label={`Jumlah retur ${it.description}`}
                      onChange={(e) => setQty((q) => ({ ...q, [i]: e.target.value }))} />
                  </div>
                );
              })}
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>Sebab retur</Label>
            <ReferenceSelect group="return_kind" value={kind} onChange={setKind}
              testId={T.kindSelect} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="return-reason">Alasan (wajib, minimal 10 huruf)</Label>
            <Textarea id="return-reason" data-testid={T.reason} rows={3} value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="mis. 10 sak semen mengeras karena terkena air saat pengiriman" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.submit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan retur"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
