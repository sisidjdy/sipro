import React, { useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/services/apiClient";
import PhoneInput from "@/components/patterns/PhoneInput";
import { CUSTOMERS } from "@/constants/testIds";

const EMPTY = {
  name: "", phone: "", email: "", nik: "", npwp: "", occupation: "",
  monthly_income: "", address: "", spouse_name: "", spouse_nik: "",
  heir_name: "", heir_relation: "", notes: "",
};

export default function AddCustomerDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.name) { toast.error("Nama customer wajib diisi."); return; }
    setBusy(true);
    try {
      const payload = { ...form };
      payload.monthly_income = form.monthly_income ? Number(form.monthly_income) : null;
      Object.keys(payload).forEach((k) => { if (payload[k] === "") payload[k] = null; });
      await api.post("/customers", payload);
      toast.success("Customer ditambahkan.");
      onOpenChange(false);
      setForm(EMPTY);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menambah customer.");
    } finally { setBusy(false); }
  };

  const field = (k, label, props = {}) => (
    <div className="space-y-1.5">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} aria-label={label} value={form[k]} onChange={(e) => set(k, e.target.value)} {...props} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Tambah Customer</DialogTitle>
          <DialogDescription>Data pembeli lengkap (KYC) untuk keperluan legal & KPR.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          {field("name", "Nama Lengkap")}
          <div className="space-y-1.5">
            <Label htmlFor="phone">No. Telepon (WA)</Label>
            <PhoneInput id="phone" value={form.phone} onChange={(v) => set("phone", v)} testId="customer-phone-input" />
          </div>
          {field("email", "Email (opsional)")}
          {field("nik", "NIK (16 digit)")}
          {field("npwp", "NPWP (opsional)")}
          {field("occupation", "Pekerjaan")}
          {field("monthly_income", "Penghasilan / bulan (Rp)", { type: "number" })}
          {field("spouse_name", "Nama Pasangan")}
          {field("spouse_nik", "NIK Pasangan")}
          {field("heir_name", "Nama Ahli Waris")}
          {field("heir_relation", "Hubungan Ahli Waris")}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="address">Alamat</Label>
            <Textarea id="address" rows={2} value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="notes">Catatan (opsional)</Label>
            <Textarea id="notes" rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={CUSTOMERS.addSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan Customer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
