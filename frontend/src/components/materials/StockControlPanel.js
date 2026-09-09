import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowLeftRight, PackageSearch, TriangleAlert } from "lucide-react";

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
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { STOCK as T } from "@/constants/testIds";

const ALERT_TONE = {
  empty: "rose", below_min: "amber", no_min: "muted", ok: "emerald",
};

/**
 * StockControlPanel (Fase 48E) — peringatan stok, transfer antar proyek, dan NILAI persediaan.
 *
 * Tiga hal yang sebelumnya tidak ada: (1) gudang tidak pernah diperingatkan sebelum barang
 * habis; (2) memindahkan material antar proyek hanya bisa lewat dua transaksi terpisah yang
 * tidak terikat — barang bisa “tercipta”; (3) nilai persediaan tidak diketahui. Material yang
 * belum punya harga masuk dilaporkan apa adanya, bukan dinilai nol.
 */
export default function StockControlPanel({ projectId, onChanged }) {
  const { can } = useAuth();
  const canSetMin = can("materials", "update");
  const canTransfer = can("materials", "approve");
  const [alerts, setAlerts] = useState(null);
  const [valuation, setValuation] = useState(null);
  const [transfers, setTransfers] = useState(null);
  const [loading, setLoading] = useState(true);
  const [minDraft, setMinDraft] = useState({});
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [a, v, t] = await Promise.all([
        api.get("/materials/stock-alerts", { params: { project_id: projectId } }),
        api.get("/materials/valuation", { params: { project_id: projectId } }),
        api.get("/materials/transfers", { params: { project_id: projectId } }),
      ]);
      setAlerts(a.data); setValuation(v.data); setTransfers(t.data);
      setMinDraft({});
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat kendali stok.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const saveMin = async (row) => {
    const value = minDraft[row.material_id];
    if (value === undefined || value === "" || Number(value) < 0) {
      toast.error("Isi batas minimum (0 atau lebih)."); return;
    }
    try {
      await api.put(`/materials/${row.material_id}/min-stock`, { min_qty: Number(value) });
      toast.success(`Batas minimum ${row.name} disetel ${value} ${row.uom}.`);
      load(); onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan batas minimum.");
    }
  };

  if (loading) return <LoadingCards count={4} />;
  const sa = alerts?.summary || {};
  const sv = valuation?.summary || {};

  return (
    <div data-testid={T.panel} className="space-y-6">
      <section className="space-y-3">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Stok habis" value={sa.empty ?? 0} tone="rose" />
          <MetricCard label="Di bawah minimum" value={sa.below_min ?? 0} tone="amber" />
          <MetricCard label="Batas belum diatur" value={sa.no_min ?? 0} tone="muted" />
          <MetricCard label="Nilai persediaan" value={sv.total_value ?? 0} tone="indigo"
            format="idr" />
        </div>
        <p className="rounded-lg border border-dashed bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          {sv.detail}
        </p>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="section-title">Peringatan stok &amp; nilai</h3>
          {canTransfer ? (
            <Button data-testid={T.transferBtn} size="sm" onClick={() => setOpen(true)}>
              <ArrowLeftRight className="mr-1.5 h-4 w-4" /> Transfer antar proyek
            </Button>
          ) : null}
        </div>
        {!alerts?.data?.length ? (
          <EmptyState icon={PackageSearch} title="Belum ada material di proyek ini"
            description="Tambahkan material pada tab Stok &amp; Buku Besar terlebih dahulu." />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Material</TableHead>
                <TableHead className="text-right">Stok</TableHead>
                <TableHead>Batas minimum</TableHead>
                <TableHead>Keadaan</TableHead>
                <TableHead className="text-right">Harga rata-rata</TableHead>
                <TableHead className="text-right">Nilai</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {alerts.data.map((r) => {
                  const val = (valuation?.data || []).find(
                    (v) => v.material_id === r.material_id) || {};
                  return (
                    <TableRow key={r.material_id} data-testid={T.alertRow} data-state={r.state}>
                      <TableCell>
                        <p className="font-medium">{r.name}</p>
                        <p className="font-mono text-[11px] text-muted-foreground">{r.code}</p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.stock} {r.uom}</TableCell>
                      <TableCell>
                        {canSetMin ? (
                          <div className="flex items-center gap-1.5">
                            <Input data-testid={T.minInput} type="number" min="0" step="0.01"
                              className="h-8 w-24"
                              aria-label={`Batas minimum ${r.name}`}
                              value={minDraft[r.material_id] ?? (r.min_qty ?? "")}
                              onChange={(e) => setMinDraft((d) => ({
                                ...d, [r.material_id]: e.target.value }))} />
                            <Button data-testid={T.minSaveBtn} size="sm" variant="outline"
                              className="h-8" onClick={() => saveMin(r)}>Simpan</Button>
                          </div>
                        ) : (
                          <span className="text-sm tabular-nums">
                            {r.min_qty ?? <span className="text-muted-foreground">belum diatur</span>}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusPill status={r.state} group="stock_alert_state"
                          tone={ALERT_TONE[r.state]} />
                        {r.shortfall ? (
                          <p className="mt-0.5 text-[11px] text-amber-700">
                            kurang {r.shortfall} {r.uom}</p>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {val.avg_cost === null || val.avg_cost === undefined
                          ? <span className="text-xs text-muted-foreground">belum ada data</span>
                          : formatIDR(val.avg_cost)}
                      </TableCell>
                      <TableCell data-testid={T.valuationRow} className="text-right tabular-nums">
                        {val.value === null || val.value === undefined
                          ? <span className="text-xs text-muted-foreground">—</span>
                          : formatIDR(val.value)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section className="space-y-3 border-t pt-6">
        <h3 className="section-title">Riwayat transfer antar proyek</h3>
        {!transfers?.data?.length ? (
          <EmptyState icon={ArrowLeftRight} title="Belum ada transfer material"
            description={"Transfer menulis sepasang mutasi bertaut satu nomor: keluar dari "
              + "proyek asal, masuk ke proyek tujuan — barang tidak pernah tercipta."} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Nomor</TableHead><TableHead>Material</TableHead>
                <TableHead>Dari → Ke</TableHead>
                <TableHead className="text-right">Jumlah</TableHead>
                <TableHead className="text-right">Nilai</TableHead>
                <TableHead>Alasan</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {transfers.data.map((t) => (
                  <TableRow key={t.id} data-testid={T.transferRow}>
                    <TableCell>
                      <p className="font-mono text-xs">{t.transfer_number}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {formatDateWIB(t.created_at)}</p>
                    </TableCell>
                    <TableCell className="text-sm">{t.material_name}</TableCell>
                    <TableCell className="text-xs">
                      {t.from_project_name} → {t.to_project_name}</TableCell>
                    <TableCell className="text-right tabular-nums">{t.qty} {t.uom}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {t.value === null ? <span className="text-xs text-muted-foreground">
                        belum ada harga</span> : formatIDR(t.value)}</TableCell>
                    <TableCell className="max-w-xs text-xs text-muted-foreground">{t.reason}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <TransferDialog open={open} onOpenChange={setOpen} projectId={projectId}
        materials={alerts?.data || []}
        onDone={() => { setOpen(false); load(); onChanged && onChanged(); }} />
    </div>
  );
}

function TransferDialog({ open, onOpenChange, projectId, materials, onDone }) {
  const [projects, setProjects] = useState([]);
  const [materialId, setMaterialId] = useState("");
  const [target, setTarget] = useState("");
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMaterialId(""); setTarget(""); setQty(""); setReason("");
    api.get("/projects").then((r) => setProjects(
      (r.data.data || []).filter((p) => p.id !== projectId))).catch(() => setProjects([]));
  }, [open, projectId]);

  const mat = materials.find((m) => m.material_id === materialId);

  const submit = async () => {
    if (!materialId || !target) { toast.error("Pilih material dan proyek tujuan."); return; }
    if (!(Number(qty) > 0)) { toast.error("Jumlah transfer harus lebih dari 0."); return; }
    if (reason.trim().length < 10) {
      toast.error("Alasan transfer minimal 10 huruf — barang berpindah pusat biaya."); return;
    }
    setBusy(true);
    try {
      const r = await api.post("/materials/transfers", {
        from_project_id: projectId, to_project_id: target, material_id: materialId,
        qty: Number(qty), reason: reason.trim(),
      });
      const d = r.data.data;
      toast.success(`Transfer ${d.transfer_number} tercatat — sisa di proyek asal `
        + `${d.stock_from_after} ${d.uom}.`);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal melakukan transfer.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.transferDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Transfer material antar proyek</DialogTitle>
          <DialogDescription>
            Menulis dua mutasi bertaut satu nomor. Bila material belum ada di proyek tujuan,
            master-nya dibuat otomatis dengan kode &amp; satuan yang sama.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Material</Label>
            <Select value={materialId} onValueChange={setMaterialId}>
              <SelectTrigger data-testid={T.transferMaterial}>
                <SelectValue placeholder="Pilih material…" /></SelectTrigger>
              <SelectContent>
                {materials.map((m) => (
                  <SelectItem key={m.material_id} value={m.material_id}>
                    {m.code} · {m.name} (stok {m.stock} {m.uom})</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {mat ? (
              <p className="text-[11px] text-muted-foreground">
                Stok tersedia {mat.stock} {mat.uom} — transfer melebihi ini akan ditolak.</p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label>Proyek tujuan</Label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger data-testid={T.transferTarget}>
                <SelectValue placeholder={projects.length ? "Pilih proyek tujuan…"
                  : "Belum ada proyek lain"} /></SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="trf-qty">Jumlah</Label>
            <Input id="trf-qty" data-testid={T.transferQty} type="number" min="0" step="0.01"
              value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="trf-reason">Alasan</Label>
            <Textarea id="trf-reason" data-testid={T.transferReason} rows={3} value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="mis. pengecoran proyek sebelah dimajukan, stok dipinjam sementara" />
          </div>
          <p className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5" />
            Transfer memindahkan NILAI antar pusat biaya proyek — karena itu hanya bisa
            dilakukan peran yang berwenang dan selalu berjejak.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.transferSubmit} onClick={submit} disabled={busy}>
            {busy ? "Memproses…" : "Transfer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
