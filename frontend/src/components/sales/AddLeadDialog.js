import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import PhoneInput from "@/components/patterns/PhoneInput";
import api from "@/services/apiClient";
import { LEADS } from "@/constants/testIds";


export default function AddLeadDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState({ name: "", phone: "", email: "", source: "manual", interest_unit_type: "", notes: "", partner_id: "" });
  const [partners, setPartners] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  // Fase 42: lead bersumber mitra WAJIB menyebut mitranya (backend menolak bila kosong),
  // karena dari situlah hak fee & analitik mitra dihitung. Daftar mitra hanya diambil saat
  // dialog dibuka supaya halaman lead tidak menanggung request tambahan.
  useEffect(() => {
    if (!open) return;
    api.get("/partners", { params: { status: "active", limit: 200 } })
      .then((r) => setPartners(r.data.data || []))
      .catch(() => setPartners([]));
  }, [open]);

  const submit = async () => {
    if (!form.name || !form.phone) { toast.error("Nama & telepon wajib diisi."); return; }
    if (form.source === "partner" && !form.partner_id) {
      toast.error("Lead dari mitra wajib memilih mitranya (dasar hak fee).");
      return;
    }
    setBusy(true);
    try {
      const payload = { ...form };
      if (!payload.partner_id) delete payload.partner_id;
      const res = await api.post("/leads", payload);
      if (res.data?.attribution_conflict) {
        toast.warning("Nomor ini sudah pernah dikirim mitra lain — atribusi mengikuti "
          + "aturan dan sengketanya dicatat untuk ditinjau.");
      } else {
        toast.success("Lead ditambahkan.");
      }
      onOpenChange(false);
      setForm({ name: "", phone: "", email: "", source: "manual", interest_unit_type: "", notes: "", partner_id: "" });
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menambah lead.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tambah Lead</DialogTitle>
          <DialogDescription>Lead baru akan otomatis membuat task “Hubungi ≤5 menit”.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="n">Nama</Label>
            <Input id="n" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p">No. Telepon (WA)</Label>
            <PhoneInput id="p" value={form.phone} onChange={(v) => set("phone", v)} testId="lead-phone-input" />
            <p className="text-xs text-muted-foreground">Ketik nomor lokal saja (mis. 812…); awalan +62 ditambahkan otomatis.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e">Email (opsional)</Label>
            <Input id="e" value={form.email} onChange={(e) => set("email", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Sumber</Label>
            <ReferenceSelect group="lead_source" value={form.source}
              onChange={(v) => set("source", v)} testId="lead-form-source" />
          </div>
          {form.source === "partner" ? (
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Mitra pengirim lead (wajib)</Label>
              <Select value={form.partner_id} onValueChange={(v) => set("partner_id", v)}>
                <SelectTrigger data-testid="lead-form-partner" aria-label="Mitra pengirim lead">
                  <SelectValue placeholder="Pilih mitra" />
                </SelectTrigger>
                <SelectContent>
                  {partners.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Mitra harus aktif &amp; kontraknya berlaku. Bila nomor ini sudah pernah dikirim
                mitra lain, kepemilikan ditentukan model atribusi di Pusat Konfigurasi dan
                sengketanya dicatat.
              </p>
            </div>
          ) : null}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="i">Minat Unit (opsional)</Label>
            <ReferenceSelect group="unit_type" value={form.interest_unit_type}
              onChange={(v) => set("interest_unit_type", v)} testId="lead-form-unit-type"
              placeholder="Pilih tipe unit yang diminati" />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="nt">Catatan (opsional)</Label>
            <Textarea id="nt" rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={LEADS.createSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan..." : "Simpan Lead"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
