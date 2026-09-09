import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Scale, Tag } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
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
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import ProjectSelect from "@/components/construction/ProjectSelect";
import { LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { VENDOR as T } from "@/constants/testIds";

const today = () => new Date().toISOString().slice(0, 10);

/**
 * PriceListPanel (Fase 48A) — daftar harga vendor + PEMBANDING lintas vendor.
 *
 * Ini yang membuat harga PO punya dasar. Tanpa daftar harga, uji kewajaran harga hanya bisa
 * menjawab “belum ada acuan” — dan itu memang yang ditampilkan, bukan tebakan.
 */
export default function PriceListPanel() {
  const { can } = useAuth();
  const canUpdate = can("vendors", "update");
  const [projectId, setProjectId] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [materialId, setMaterialId] = useState("");
  const [rows, setRows] = useState([]);
  const [compare, setCompare] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!projectId) { setMaterials([]); return; }
    api.get(`/materials/project/${projectId}`)
      .then((r) => setMaterials(r.data.data || []))
      .catch(() => setMaterials([]));
  }, [projectId]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/vendors/price-list",
        { params: { material_id: materialId || undefined } });
      setRows(r.data.data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat daftar harga.");
    } finally { setLoading(false); }
  }, [materialId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!materialId) { setCompare(null); return; }
    api.get("/vendors/price-compare", { params: { material_id: materialId, qty: 1 } })
      .then((r) => setCompare(r.data.data))
      .catch(() => setCompare(null));
  }, [materialId, rows]);

  const materialName = useMemo(
    () => materials.find((m) => m.id === materialId)?.name, [materials, materialId]);

  return (
    <div data-testid={T.pricePanel} className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ProjectSelect value={projectId} onChange={setProjectId}
            testId={T.priceProjectSelect} />
          <Select value={materialId} onValueChange={setMaterialId}>
            <SelectTrigger data-testid={T.priceMaterialSelect} className="w-64">
              <SelectValue placeholder="Semua material" />
            </SelectTrigger>
            <SelectContent>
              {materials.map((m) => (
                <SelectItem key={m.id} value={m.id}>{m.code} · {m.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {canUpdate ? (
          <Button data-testid={T.priceAddBtn} size="sm" onClick={() => setOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Catat harga vendor
          </Button>
        ) : null}
      </div>

      {compare ? (
        <div data-testid={T.compareBox}
          className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
          <p className="flex items-center gap-2 font-heading text-sm font-semibold">
            <Scale className="h-4 w-4 text-primary" />
            Pembanding harga{materialName ? ` — ${materialName}` : ""}
          </p>
          {compare.state === "missing_data" ? (
            <p className="mt-2 rounded-lg border border-dashed bg-secondary/40 p-3 text-sm text-muted-foreground">
              {compare.detail}
            </p>
          ) : (
            <div className="mt-2 space-y-1.5">
              {compare.rows.map((r) => (
                <div key={r.price_id} data-testid={T.compareRow}
                  className={`flex items-center justify-between rounded-lg border p-2 text-sm ${
                    r.is_best ? "border-emerald-200 bg-emerald-50" : "bg-card"}`}>
                  <div>
                    <span className="font-medium">{r.vendor_name}</span>
                    {r.is_best ? (
                      <span className="ml-2 rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                        TERMURAH
                      </span>
                    ) : null}
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="price_source" value={r.source} /> · berlaku {r.valid_from}
                      {r.valid_until ? ` s/d ${r.valid_until}` : ""}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium tabular-nums">{formatIDR(r.unit_price)}/{r.uom}</p>
                    {r.delta_vs_best ? (
                      <p className="text-[11px] text-rose-600 tabular-nums">
                        +{formatIDR(r.delta_vs_best)} ({r.delta_pct}%)
                      </p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {loading ? <LoadingCards count={2} /> : !rows.length ? (
        <EmptyState icon={Tag} title="Belum ada harga vendor tercatat"
          description={"Catat harga penawaran vendor supaya harga PO punya pembanding dan "
            + "kenaikan harga bisa terlihat — sistem tidak akan menebak harga wajar."} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Barang</TableHead><TableHead>Vendor</TableHead>
              <TableHead className="text-right">Harga satuan</TableHead>
              <TableHead>Sumber</TableHead><TableHead>Berlaku</TableHead>
              <TableHead className="text-right">Koreksi</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id} data-testid={T.priceRow}>
                  <TableCell className="font-medium">{p.item_name}</TableCell>
                  <TableCell className="text-sm">{p.vendor_name}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatIDR(p.unit_price)}/{p.uom}</TableCell>
                  <TableCell className="text-sm">
                    <RefLabel group="price_source" value={p.source} /></TableCell>
                  <TableCell className="text-sm">
                    {p.valid_from}{p.valid_until ? ` s/d ${p.valid_until}` : ""}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                    {(p.history || []).length ? `${p.history.length}×` : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <PriceDialog open={open} onOpenChange={setOpen} materials={materials}
        projectId={projectId} onDone={() => { setOpen(false); load(); }} />
    </div>
  );
}

function PriceDialog({ open, onOpenChange, materials, projectId, onDone }) {
  const [vendors, setVendors] = useState([]);
  const [vendorId, setVendorId] = useState("");
  const [materialId, setMaterialId] = useState("");
  const [price, setPrice] = useState("");
  const [source, setSource] = useState("penawaran");
  const [from, setFrom] = useState(today());
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setVendorId(""); setMaterialId(""); setPrice(""); setFrom(today()); setUntil("");
    api.get("/vendors", { params: { active: true } })
      .then((r) => setVendors(r.data.data || [])).catch(() => setVendors([]));
  }, [open]);

  const submit = async () => {
    if (!vendorId) { toast.error("Pilih vendor."); return; }
    if (!materialId) { toast.error("Pilih material."); return; }
    if (!(Number(price) > 0)) { toast.error("Harga satuan harus lebih dari 0."); return; }
    const mat = materials.find((m) => m.id === materialId);
    setBusy(true);
    try {
      await api.post("/vendors/price-list", {
        vendor_id: vendorId, material_id: materialId, uom: mat?.uom || null,
        unit_price: Math.round(Number(price)), source, valid_from: from,
        valid_until: until || null,
      });
      toast.success("Harga vendor tercatat.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan harga.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.priceDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Catat harga vendor</DialogTitle>
          <DialogDescription>
            Mengirim harga untuk vendor + barang + tanggal berlaku yang sama akan MENGOREKSI
            baris yang ada (berjejak), bukan membuat harga kembar.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Vendor</Label>
            <Select value={vendorId} onValueChange={setVendorId}>
              <SelectTrigger data-testid={T.priceVendorSelect}>
                <SelectValue placeholder="Pilih vendor…" /></SelectTrigger>
              <SelectContent>
                {vendors.map((v) => (
                  <SelectItem key={v.id} value={v.id}>{v.name} ({v.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Material</Label>
            <Select value={materialId} onValueChange={setMaterialId}>
              <SelectTrigger data-testid={`${T.priceMaterialSelect}-dialog`}>
                <SelectValue placeholder={projectId ? "Pilih material…"
                  : "Pilih proyek dulu di atas"} /></SelectTrigger>
              <SelectContent>
                {materials.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.code} · {m.name} ({m.uom})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="price-value">Harga satuan (Rp)</Label>
              <RupiahInput id="price-value" data-testid={T.priceValue}
                value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Sumber harga</Label>
              <ReferenceSelect group="price_source" value={source} onChange={setSource}
                testId="vendor-price-source" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="price-from">Berlaku sejak</Label>
              <Input id="price-from" data-testid={T.priceFrom} type="date" value={from}
                onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="price-until">Berlaku sampai</Label>
              <Input id="price-until" type="date" value={until}
                onChange={(e) => setUntil(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.priceSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan harga"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
