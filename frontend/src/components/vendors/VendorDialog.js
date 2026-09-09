import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { VENDOR as T } from "@/constants/testIds";

const EMPTY = {
  code: "", name: "", category: "material", npwp: "", phone: "", email: "",
  address: "", pic_name: "", payment_terms_days: 30, bank_name: "",
  bank_account_no: "", bank_account_holder: "", is_active: true, note: "",
};

/** VendorDialog (Fase 48A) — daftarkan/koreksi master vendor. */
export default function VendorDialog({ open, mode = "create", vendor, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const edit = mode === "edit";

  useEffect(() => {
    if (!open) return;
    setForm(edit && vendor ? { ...EMPTY, ...vendor } : EMPTY);
  }, [open, edit, vendor]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (form.name.trim().length < 3) { toast.error("Nama vendor minimal 3 huruf."); return; }
    setBusy(true);
    try {
      const body = {
        name: form.name.trim(), category: form.category,
        npwp: form.npwp || null, phone: form.phone || null, email: form.email || null,
        address: form.address || null, pic_name: form.pic_name || null,
        payment_terms_days: Number(form.payment_terms_days) || 0,
        bank_name: form.bank_name || null, bank_account_no: form.bank_account_no || null,
        bank_account_holder: form.bank_account_holder || null,
        is_active: !!form.is_active, note: form.note || null,
      };
      if (edit) await api.put(`/vendors/${vendor.id}`, body);
      else await api.post("/vendors", { ...body, code: form.code.trim().toUpperCase() });
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan vendor.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.dialog} className="max-h-[88vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{edit ? "Koreksi vendor" : "Daftarkan vendor"}</DialogTitle>
          <DialogDescription>
            Data ini dipakai PO, tagihan, dan penilaian vendor. Nama diambil sebagai salinan
            saat PO dibuat, jadi mengubah nama di sini tidak mengubah dokumen lama.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="vendor-code">Kode</Label>
            <Input id="vendor-code" data-testid={T.code} value={form.code} disabled={edit}
              onChange={(e) => set("code", e.target.value)} placeholder="otomatis dari aturan penomoran bila kosong" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-name">Nama vendor</Label>
            <Input id="vendor-name" data-testid={T.name} value={form.name}
              onChange={(e) => set("name", e.target.value)} placeholder="PT/CV/UD …" />
          </div>
          <div className="space-y-1.5">
            <Label>Kategori</Label>
            <ReferenceSelect group="vendor_category" value={form.category}
              onChange={(v) => set("category", v)} testId={T.categorySelect} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-terms">Termin bayar (hari)</Label>
            <Input id="vendor-terms" data-testid={T.terms} type="number" min="0" max="180"
              value={form.payment_terms_days}
              onChange={(e) => set("payment_terms_days", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-npwp">NPWP</Label>
            <Input id="vendor-npwp" data-testid={T.npwp} value={form.npwp || ""}
              onChange={(e) => set("npwp", e.target.value)} placeholder="opsional" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-phone">Telepon</Label>
            <Input id="vendor-phone" data-testid={T.phone} value={form.phone || ""}
              onChange={(e) => set("phone", e.target.value)} placeholder="+62…" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-pic">Nama PIC</Label>
            <Input id="vendor-pic" value={form.pic_name || ""}
              onChange={(e) => set("pic_name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-email">Email</Label>
            <Input id="vendor-email" type="email" value={form.email || ""}
              onChange={(e) => set("email", e.target.value)} placeholder="opsional" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-bank">Nama bank</Label>
            <Input id="vendor-bank" value={form.bank_name || ""}
              onChange={(e) => set("bank_name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor-rek">No. rekening</Label>
            <Input id="vendor-rek" value={form.bank_account_no || ""}
              onChange={(e) => set("bank_account_no", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="vendor-address">Alamat</Label>
            <Input id="vendor-address" value={form.address || ""}
              onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="vendor-note">Catatan</Label>
            <Textarea id="vendor-note" rows={2} value={form.note || ""}
              onChange={(e) => set("note", e.target.value)}
              placeholder="mis. syarat kirim, lead time, kebiasaan pembayaran…" />
          </div>
          {edit ? (
            <div className="flex items-center justify-between rounded-lg border p-3 sm:col-span-2">
              <div>
                <p className="text-sm font-medium">Vendor aktif</p>
                <p className="text-xs text-muted-foreground">
                  Vendor nonaktif tidak bisa dipilih pada PO baru, tetapi riwayatnya tetap ada.
                </p>
              </div>
              <Switch checked={!!form.is_active}
                onCheckedChange={(v) => set("is_active", v)} />
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.submit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan vendor"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
