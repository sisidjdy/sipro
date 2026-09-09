import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
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
import ReferenceItems from "@/components/patterns/ReferenceItems";

const NEW_LINE = () => ({ material_id: "", description: "", uom: "unit", qty: "1", unit_price: "0" });

export default function AddPODialog({ open, onOpenChange, onDone, defaultProjectId }) {
  const [projectId, setProjectId] = useState("");
  const [poType, setPoType] = useState("material");
  const [vendor, setVendor] = useState("");
  const [subId, setSubId] = useState("");
  const [spkId, setSpkId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState([NEW_LINE()]);
  const [projects, setProjects] = useState([]);
  const [subs, setSubs] = useState([]);
  const [spks, setSpks] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPoType("material"); setVendor(""); setSubId(""); setSpkId(""); setDueDate(""); setNote(""); setLines([NEW_LINE()]);
    setProjectId(defaultProjectId || "");
    Promise.all([api.get("/projects"), api.get("/subcon/subcontractors", { params: { active: "true" } })])
      .then(([rp, rs]) => {
        const pl = rp.data.data || []; setProjects(pl); setSubs(rs.data.data || []);
        if (!defaultProjectId && pl.length) setProjectId(pl[0].id);
      }).catch(() => {});
  }, [open, defaultProjectId]);

  useEffect(() => {
    if (!open || !projectId) return;
    api.get(`/materials/project/${projectId}`).then((r) => setMaterials(r.data.data || [])).catch(() => setMaterials([]));
  }, [open, projectId]);

  useEffect(() => {
    if (!open || !subId) { setSpks([]); return; }
    const sub = subs.find((s) => s.id === subId);
    if (sub) setVendor(sub.name);
    api.get("/subcon/spk", { params: { subcontractor_id: subId } }).then((r) => setSpks(r.data.data || [])).catch(() => setSpks([]));
  }, [subId, open, subs]);

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, [k]: v } : l)));
  const onMaterial = (i, mid) => {
    const m = materials.find((x) => x.id === mid);
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, material_id: mid, description: m?.name || l.description, uom: m?.uom || l.uom } : l)));
  };
  const total = lines.reduce((s, l) => s + (Number(l.qty) || 0) * (Number(l.unit_price) || 0), 0);

  const submit = async () => {
    if (!projectId) { toast.error("Pilih proyek."); return; }
    if (!vendor.trim()) { toast.error("Isi/pilih vendor."); return; }
    const items = lines.filter((l) => l.description.trim() && Number(l.qty) > 0).map((l) => ({
      description: l.description, material_id: l.material_id || null, uom: l.uom,
      qty: Number(l.qty) || 0, unit_price: Math.round(Number(l.unit_price) || 0),
    }));
    if (!items.length) { toast.error("Tambahkan minimal 1 item valid."); return; }
    setBusy(true);
    try {
      await api.post("/procurement/pos", {
        project_id: projectId, po_type: poType, vendor,
        subcontractor_id: poType === "subcon" ? (subId || null) : null,
        spk_id: poType === "subcon" ? (spkId || null) : null,
        due_date: dueDate ? new Date(dueDate).toISOString() : null, note: note || null, items,
      });
      toast.success("PO dibuat (status draft, menunggu approval).");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat PO."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Buat Purchase Order</DialogTitle>
          <DialogDescription>PO material/subkontraktor. Perlu persetujuan sebelum penerimaan & penagihan.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Proyek</Label>
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger data-testid="po-form-project"><SelectValue placeholder="Pilih…" /></SelectTrigger>
              <SelectContent>{projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1.5"><Label>Jenis PO</Label>
            <Select value={poType} onValueChange={(v) => { setPoType(v); setSubId(""); setSpkId(""); }}>
              <SelectTrigger data-testid="po-form-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <ReferenceItems group="po_type" />
              </SelectContent>
            </Select></div>
          {poType === "subcon" ? (
            <>
              <div className="space-y-1.5"><Label>Subkontraktor</Label>
                <Select value={subId} onValueChange={setSubId}>
                  <SelectTrigger><SelectValue placeholder="Pilih…" /></SelectTrigger>
                  <SelectContent>{subs.map((s) => <SelectItem key={s.id} value={s.id}>{s.name} ({s.code})</SelectItem>)}</SelectContent>
                </Select></div>
              <div className="space-y-1.5"><Label>SPK (opsional)</Label>
                <Select value={spkId} onValueChange={setSpkId}>
                  <SelectTrigger><SelectValue placeholder="Pilih SPK…" /></SelectTrigger>
                  <SelectContent>{spks.map((s) => <SelectItem key={s.id} value={s.id}>{s.spk_number}</SelectItem>)}</SelectContent>
                </Select></div>
            </>
          ) : null}
          <div className="space-y-1.5"><Label>Vendor</Label>
            <ReferenceSelect group="vendor" value={vendor} onChange={setVendor}
              testId="po-form-vendor" placeholder="Pilih vendor / toko…" /></div>
          <div className="space-y-1.5"><Label htmlFor="po-due">Jatuh Tempo</Label><Input id="po-due" data-testid="po-form-due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} /></div>
        </div>

        <div className="mt-2 space-y-2">
          <div className="flex items-center justify-between">
            <Label>Item</Label>
            <Button data-testid={PROCUREMENT.poItemAdd} type="button" variant="outline" size="sm" onClick={() => setLines((l) => [...l, NEW_LINE()])}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Baris
            </Button>
          </div>
          {lines.map((l, i) => (
            <div key={i} className="grid grid-cols-12 items-end gap-2 rounded-lg border bg-secondary/40 p-2">
              {poType === "material" && materials.length ? (
                <div className="col-span-12 sm:col-span-5">
                  <Select value={l.material_id} onValueChange={(v) => onMaterial(i, v)}>
                    <SelectTrigger className="h-9"><SelectValue placeholder="Pilih material / ketik…" /></SelectTrigger>
                    <SelectContent>{materials.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} ({m.uom})</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              ) : null}
              <div className={poType === "material" && materials.length ? "col-span-12 sm:col-span-7" : "col-span-12 sm:col-span-6"}>
                <Input className="h-9" value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} placeholder="Uraian item" />
              </div>
              <div className="col-span-3 sm:col-span-2">
                <ReferenceSelect group="uom" value={l.uom} onChange={(v) => setLine(i, "uom", v)}
                  testId={`po-line-uom-${i}`} className="h-9" /></div>
              <div className="col-span-4 sm:col-span-2"><Input className="h-9" type="number" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)} placeholder="Qty" /></div>
              <div className="col-span-4 sm:col-span-2"><RupiahInput className="h-9" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} placeholder="Harga" /></div>
              <div className="col-span-1">
                {lines.length > 1 ? (
                  <Button type="button" variant="ghost" size="icon" className="h-9 w-9 text-rose-600" onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className="rounded-lg bg-secondary p-3 text-sm">Total PO: <span className="font-semibold tabular-nums">{formatIDR(total)}</span>{total > 500000000 ? <span className="ml-2 text-xs font-semibold text-rose-600">Nilai tinggi — perlu approval Owner</span> : null}</div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROCUREMENT.poAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan PO"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
