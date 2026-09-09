import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PROCUREMENT } from "@/constants/testIds";

const EMPTY = {
  code: "", name: "", specialty: "", phone: "", email: "", npwp: "", address: "", pic_name: "",
};

export default function AddSubcontractorDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  useEffect(() => { if (open) setForm(EMPTY); }, [open]);

  const submit = async () => {
    if (!form.name.trim()) { toast.error("Isi nama subkontraktor."); return; }
    setBusy(true);
    try {
      await api.post("/subcon/subcontractors", {
        code: form.code, name: form.name, specialty: form.specialty || null,
        phone: form.phone || null, email: form.email || null, npwp: form.npwp || null,
        address: form.address || null, pic_name: form.pic_name || null,
      });
      toast.success("Subkontraktor ditambahkan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah subkontraktor."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Tambah Subkontraktor</DialogTitle>
          <DialogDescription>Data vendor/subkontraktor untuk SPK & pengadaan.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="addsubcontractordialog-kode">Kode</Label><Input id="addsubcontractordialog-kode" data-testid="subcon-form-code" value={form.code} onChange={(e) => set("code", e.target.value)} placeholder="otomatis dari aturan penomoran bila kosong" /></div>
          <div className="space-y-1.5"><Label htmlFor="addsubcontractordialog-nama">Nama</Label><Input id="addsubcontractordialog-nama" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="CV / PT …" /></div>
          <div className="space-y-1.5"><Label>Bidang</Label>
            <ReferenceSelect group="subcon_specialty" value={form.specialty}
              onChange={(v) => set("specialty", v)} testId="subcon-form-specialty" /></div>
          <div className="space-y-1.5"><Label htmlFor="addsubcontractordialog-nama-pic-kontak-vendor">Nama PIC (kontak vendor)</Label><Input id="addsubcontractordialog-nama-pic-kontak-vendor" value={form.pic_name} onChange={(e) => set("pic_name", e.target.value)} placeholder="mis. Bpk. Andi" /></div>
          <div className="space-y-1.5"><Label htmlFor="addsubcontractordialog-telepon">Telepon</Label><Input id="addsubcontractordialog-telepon" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="08…" /></div>
          <div className="space-y-1.5"><Label htmlFor="subcon-email">Email</Label><Input id="subcon-email" data-testid="subcon-form-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="nama@perusahaan.co.id" /></div>
          <div className="space-y-1.5"><Label htmlFor="subcon-npwp">NPWP</Label><Input id="subcon-npwp" data-testid="subcon-form-npwp" value={form.npwp} onChange={(e) => set("npwp", e.target.value)} placeholder="00.000.000.0-000.000" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="subcon-address">Alamat</Label><Textarea id="subcon-address" data-testid="subcon-form-address" rows={2} value={form.address} onChange={(e) => set("address", e.target.value)} placeholder="alamat kantor / domisili vendor" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROCUREMENT.subAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
