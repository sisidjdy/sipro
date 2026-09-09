import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatIDR } from "@/utils/formatters";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PROCUREMENT } from "@/constants/testIds";

// Daftar kategori & satuan TIDAK lagi hardcode di sini — sumbernya /api/reference (SSOT).
const EMPTY = { cost_code: "", category: "struktur", description: "", uom: "unit", quantity: "1", unit_price: "0", facility: "", phase_id: "" };

/** `scope`: unit (legacy per proyek) | fasum (wajib fasilitas, opsional fase konstruksi) | umum (jenis biaya). */
export default function AddBoQItemDialog({ projectId, open, onOpenChange, onDone, scope = "unit" }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [opts, setOpts] = useState({ facilities: [], umum_kinds: [] });
  const [phases, setPhases] = useState([]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  useEffect(() => {
    if (!open) return;
    setForm({ ...EMPTY, category: scope === "fasum" ? "infrastruktur" : scope === "umum" ? "lainnya" : "struktur" });
    if (scope !== "unit") {
      api.get("/rab/options").then((r) => setOpts(r.data.data)).catch(() => {});
      if (scope === "fasum") api.get(`/construction/project/${projectId}/phases`).then((r) => setPhases(r.data.data || [])).catch(() => setPhases([]));
    }
  }, [open, scope, projectId]);

  const amount = (Number(form.quantity) || 0) * (Number(form.unit_price) || 0);
  const kinds = scope === "fasum" ? opts.facilities : opts.umum_kinds;

  const submit = async () => {
    if (!form.description.trim()) { toast.error("Isi uraian pekerjaan."); return; }
    if (scope === "fasum" && !form.facility) { toast.error("Pilih fasilitas (fasum/fasos)."); return; }
    setBusy(true);
    try {
      await api.post("/boq/items", {
        project_id: projectId, cost_code: form.cost_code || null, category: form.category,
        description: form.description, uom: form.uom, quantity: Number(form.quantity) || 0,
        unit_price: Math.round(Number(form.unit_price) || 0), scope,
        facility: form.facility || null, phase_id: form.phase_id || null,
      });
      toast.success("Item RAB ditambahkan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah item."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{scope === "fasum" ? "Tambah Item RAB Fasum/Fasos" : scope === "umum" ? "Tambah Item RAB Umum" : "Tambah Item RAB"}</DialogTitle>
          <DialogDescription>Kode biaya, volume, dan harga satuan (Rp).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          {scope !== "unit" ? (
            <div className="space-y-1.5"><Label>{scope === "fasum" ? "Fasilitas" : "Jenis biaya"}</Label>
              <Select value={form.facility} onValueChange={(v) => set("facility", v)}>
                <SelectTrigger data-testid="boq-form-facility"><SelectValue placeholder="Pilih…" /></SelectTrigger>
                <SelectContent>{kinds.map((k) => <SelectItem key={k.code} value={k.code}>{k.label}</SelectItem>)}</SelectContent>
              </Select></div>
          ) : null}
          {scope === "fasum" ? (
            <div className="space-y-1.5"><Label>Fase konstruksi proyek (opsional)</Label>
              <Select value={form.phase_id} onValueChange={(v) => set("phase_id", v === "__none__" ? "" : v)}>
                <SelectTrigger data-testid="boq-form-phase"><SelectValue placeholder="Tanpa fase" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Tanpa fase</SelectItem>
                  {phases.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select></div>
          ) : null}
          <div className="space-y-1.5"><Label htmlFor="addboqitemdialog-kode-biaya">Kode Biaya</Label><Input id="addboqitemdialog-kode-biaya" value={form.cost_code} onChange={(e) => set("cost_code", e.target.value)} placeholder="mis. STR-01" /></div>
          <div className="space-y-1.5"><Label>Kategori</Label>
            <ReferenceSelect group="work_category" value={form.category}
              onChange={(v) => set("category", v)} testId="boq-form-category" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="addboqitemdialog-uraian-pekerjaan">Uraian Pekerjaan</Label><Input id="addboqitemdialog-uraian-pekerjaan" value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="mis. Beton K-300 kolom & balok" /></div>
          <div className="space-y-1.5"><Label>Satuan (UOM)</Label>
            <ReferenceSelect group="uom" value={form.uom} onChange={(v) => set("uom", v)}
              testId="boq-form-uom" /></div>
          <div className="space-y-1.5"><Label htmlFor="boq-qty">Volume</Label><Input id="boq-qty" data-testid="boq-form-qty" type="number" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="boq-price">Harga Satuan (Rp)</Label><RupiahInput id="boq-price" data-testid="boq-form-price" value={form.unit_price} onChange={(e) => set("unit_price", e.target.value)} /></div>
        </div>
        <div className="rounded-lg bg-secondary p-3 text-sm">Jumlah: <span className="font-semibold tabular-nums">{formatIDR(amount)}</span></div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROCUREMENT.boqAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
