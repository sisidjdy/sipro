import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

const EMPTY = {
  name: "", partner_kind: "agen_perorangan", entity_type: "individual", company: "",
  phone: "", email: "", nik: "", npwp: "", address: "", pic_name: "", pic_phone: "",
  bank_name: "", bank_account: "", bank_account_name: "", note: "",
  contract_number: "", contract_start: "", contract_end: "",
};

/**
 * PartnerFormDialog — daftar/ubah mitra + KONTRAK-nya dalam satu formulir.
 *
 * Kontrak diminta di sini (bukan layar terpisah) karena `partner.require_contract_active`
 * memblokir lead & fee mitra yang kontraknya kedaluwarsa: kalau field-nya disembunyikan,
 * pemakai akan bertemu penolakan tanpa tahu sebabnya.
 */
export default function PartnerFormDialog({ partner, open, onOpenChange, onDone }) {
  const editing = Boolean(partner?.id);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    setForm({
      ...EMPTY,
      ...Object.fromEntries(Object.keys(EMPTY)
        .filter((k) => partner?.[k] !== undefined && partner?.[k] !== null)
        .map((k) => [k, partner[k]])),
      contract_number: partner?.contract?.number || "",
      contract_start: (partner?.contract?.start_date || "").slice(0, 10),
      contract_end: (partner?.contract?.end_date || "").slice(0, 10),
    });
  }, [open, partner]);

  const submit = async () => {
    if (!form.name || form.name.trim().length < 3) {
      toast.error("Nama mitra minimal 3 karakter."); return;
    }
    if (!form.phone || form.phone.trim().length < 6) {
      toast.error("Nomor telepon mitra wajib diisi (dipakai untuk dedup lead)."); return;
    }
    const body = {
      ...Object.fromEntries(Object.entries(form)
        .filter(([k, v]) => !k.startsWith("contract_") && v !== "" && v !== null)),
      contract: {
        number: form.contract_number || null,
        start_date: form.contract_start || null,
        end_date: form.contract_end || null,
        signed_by: form.pic_name || form.name,
        status: form.contract_number ? "active" : "draft",
        file_ids: partner?.contract?.file_ids || [],
      },
    };
    setBusy(true);
    try {
      if (editing) await api.put(`/partners/${partner.id}`, body);
      else await api.post("/partners", body);
      toast.success(editing ? "Data mitra diperbarui." : `Mitra ${form.name} terdaftar.`);
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan mitra.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PARTNERS.form} className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editing ? `Ubah Mitra — ${partner.name}` : "Tambah Mitra"}</DialogTitle>
          <DialogDescription>
            Bentuk badan menentukan jenis PPh bawaan (perorangan → PPh 21, badan → PPh 23).
            Nomor telepon dipakai untuk mendeteksi lead ganda antar mitra.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="pname">Nama mitra</Label>
            <Input id="pname" data-testid={PARTNERS.formName} value={form.name}
              onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Jenis mitra</Label>
            <ReferenceSelect group="partner_kind" value={form.partner_kind}
              onChange={(v) => set("partner_kind", v)} testId={PARTNERS.formKind} />
          </div>
          <div className="space-y-1.5">
            <Label>Bentuk badan (menentukan PPh)</Label>
            <ReferenceSelect group="partner_entity_type" value={form.entity_type}
              onChange={(v) => set("entity_type", v)} testId={PARTNERS.formEntity} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pphone">No. telepon / WA</Label>
            <Input id="pphone" data-testid={PARTNERS.formPhone} value={form.phone}
              placeholder="+62812…" onChange={(e) => set("phone", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pcompany">Perusahaan (opsional)</Label>
            <Input id="pcompany" data-testid={PARTNERS.formCompany} value={form.company}
              onChange={(e) => set("company", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pemail">Email (opsional)</Label>
            <Input id="pemail" data-testid={PARTNERS.formEmail} value={form.email}
              onChange={(e) => set("email", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pnik">NIK (perorangan)</Label>
            <Input id="pnik" data-testid={PARTNERS.formNik} value={form.nik}
              onChange={(e) => set("nik", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pnpwp">NPWP</Label>
            <Input id="pnpwp" data-testid={PARTNERS.formNpwp} value={form.npwp}
              onChange={(e) => set("npwp", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="paddr">Alamat</Label>
            <Input id="paddr" data-testid={PARTNERS.formAddress} value={form.address}
              onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ppic">Nama PIC</Label>
            <Input id="ppic" data-testid={PARTNERS.formPic} value={form.pic_name}
              onChange={(e) => set("pic_name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ppicp">Telepon PIC</Label>
            <Input id="ppicp" data-testid={PARTNERS.formPicPhone} value={form.pic_phone}
              onChange={(e) => set("pic_phone", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pbank">Bank</Label>
            <ReferenceSelect group="financing_bank" value={form.bank_name}
              onChange={(v) => set("bank_name", v)} testId={PARTNERS.formBank} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pacc">No. rekening</Label>
            <Input id="pacc" data-testid={PARTNERS.formAccount} value={form.bank_account}
              onChange={(e) => set("bank_account", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="paccn">Nama pemilik rekening</Label>
            <Input id="paccn" data-testid={PARTNERS.formAccountName}
              value={form.bank_account_name}
              onChange={(e) => set("bank_account_name", e.target.value)} />
          </div>

          <div className="rounded-md border bg-secondary/40 p-3 sm:col-span-2">
            <p className="mb-2 text-sm font-medium">Kontrak kerja sama (PKS)</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="pcno">Nomor kontrak</Label>
                <Input id="pcno" data-testid={PARTNERS.formContractNo}
                  value={form.contract_number}
                  onChange={(e) => set("contract_number", e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pcs">Mulai</Label>
                <Input id="pcs" type="date" data-testid={PARTNERS.formContractStart}
                  value={form.contract_start}
                  onChange={(e) => set("contract_start", e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pce">Berakhir</Label>
                <Input id="pce" type="date" data-testid={PARTNERS.formContractEnd}
                  value={form.contract_end}
                  onChange={(e) => set("contract_end", e.target.value)} />
              </div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Kontrak kedaluwarsa akan MENOLAK lead &amp; tagihan fee baru dari mitra ini
              (aturan <code>partner.require_contract_active</code> di Pusat Konfigurasi).
            </p>
          </div>

          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="pnote">Catatan (opsional)</Label>
            <Textarea id="pnote" rows={2} data-testid={PARTNERS.formNote} value={form.note}
              onChange={(e) => set("note", e.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={PARTNERS.formSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : (editing ? "Simpan Perubahan" : "Simpan Mitra")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
