import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { CASHBANK, PETTYX } from "@/constants/testIds";

const EMPTY = { kind: "bank", name: "", bank_name: "", account_no: "", holder: "", opening_balance: "", opening_date: "", note: "", is_default: false, imprest_limit: "" };

/** Tambah / ubah rekening bank atau kas. Saldo awal dijurnal otomatis (Dr sub-akun / Cr 3-1950). */
export default function AccountDialog({ open, account, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const editing = !!account;

  useEffect(() => {
    if (!open) return;
    setErr("");
    setForm(account ? {
      kind: account.kind, name: account.name || "", bank_name: account.bank_name || "", account_no: account.account_no || "",
      holder: account.holder || "", opening_balance: String(account.opening_balance || ""), opening_date: account.opening_date || "",
      note: account.note || "", is_default: !!account.is_default, imprest_limit: account.imprest_limit ? String(account.imprest_limit) : "",
    } : { ...EMPTY, opening_date: new Date().toISOString().slice(0, 10) });
  }, [open, account]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setSaving(true); setErr("");
    const body = { ...form, opening_balance: Number(form.opening_balance || 0), holder: form.holder || null,
      note: form.note || null, opening_date: form.opening_date || null,
      imprest_limit: form.kind === "cash" ? Number(form.imprest_limit || 0) : null,
      bank_name: form.kind === "cash" ? (form.bank_name || "Kas") : form.bank_name };
    if (body.imprest_limit === null) delete body.imprest_limit;
    try {
      if (editing) {
        const { kind, is_default, ...upd } = body;
        if (account.opening_posted) { delete upd.opening_balance; delete upd.opening_date; }
        await api.put(`/cash-bank/accounts/${account.id}`, upd);
        toast.success(`${form.name} diperbarui.`);
      } else {
        const r = await api.post("/cash-bank/accounts", body);
        toast.success(`${r.data.data.name} terdaftar → akun GL ${r.data.data.gl_account_code}.`);
      }
      onSaved?.(); onClose();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(typeof d === "string" ? d : (Array.isArray(d) ? d.map((x) => x.msg).join("; ") : "Gagal menyimpan."));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid={CASHBANK.accountDialog}>
        <DialogHeader>
          <DialogTitle>{editing ? "Ubah Rekening / Kas" : "Rekening / Kas Baru"}</DialogTitle>
          <DialogDescription>Setiap rekening mendapat sub-akun GL sendiri di bawah 1-1200 (bank) atau 1-1100 (kas).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Jenis</Label>
              <Select value={form.kind} onValueChange={(v) => set("kind", v)} disabled={editing}>
                <SelectTrigger data-testid={CASHBANK.accountKind} className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="bank">Rekening Bank</SelectItem>
                  <SelectItem value="cash">Kas Tunai / Kas Kecil</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nama</Label>
              <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder={form.kind === "cash" ? "Kas Kecil Site A" : "Rekening Escrow"} className="h-9" data-testid={CASHBANK.accountName} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {form.kind === "bank" ? (
              <div className="space-y-1.5">
                <Label className="text-xs">Bank</Label>
                <ReferenceSelect group="financing_bank" value={form.bank_name} onChange={(v) => set("bank_name", v)} testId={CASHBANK.accountBank} />
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label className="text-xs">{form.kind === "cash" ? "Kode kas" : "Nomor rekening"}</Label>
              <Input value={form.account_no} onChange={(e) => set("account_no", e.target.value)} placeholder={form.kind === "cash" ? "KAS-02" : "1234567890"} className="h-9" data-testid={CASHBANK.accountNo} />
            </div>
            {form.kind === "bank" ? (
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-xs">Atas nama</Label>
                <Input value={form.holder} onChange={(e) => set("holder", e.target.value)} className="h-9" />
              </div>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Saldo awal {account?.opening_posted ? "(sudah dijurnal)" : ""}</Label>
              <RupiahInput value={form.opening_balance} onChange={(e) => set("opening_balance", e.target.value)} disabled={!!account?.opening_posted} data-testid={CASHBANK.accountOpening} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Tanggal saldo awal</Label>
              <Input type="date" value={form.opening_date} onChange={(e) => set("opening_date", e.target.value)} disabled={!!account?.opening_posted} className="h-9" />
            </div>
          </div>
          {form.kind === "cash" ? (
            <div className="space-y-1.5">
              <Label className="text-xs">Batas dana tetap (imprest) — kosongkan untuk memakai bawaan organisasi</Label>
              <RupiahInput value={form.imprest_limit} onChange={(e) => set("imprest_limit", e.target.value)} data-testid={PETTYX.accountImprest} />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label className="text-xs">Catatan</Label>
            <Textarea rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} />
          </div>
          {!editing ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_default} onChange={(e) => set("is_default", e.target.checked)} />
              Jadikan rekening/kas default untuk jenis ini
            </label>
          ) : null}
          {err ? <p className="text-sm text-rose-600" data-testid="cashbank-account-error">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving || form.name.length < 3 || !form.account_no} data-testid={CASHBANK.accountSubmit}>
            {saving ? "Menyimpan…" : editing ? "Simpan" : "Daftarkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
