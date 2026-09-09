import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { BANK } from "@/constants/testIds";

/**
 * BankAccountDialog — daftarkan/ubah rekening bank perusahaan.
 *
 * Rekening WAJIB menunjuk akun kas/bank di Bagan Akun: tanpa itu saldo buku tidak punya
 * pembanding dan "rekonsiliasi" hanya menjadi daftar mutasi. Karena itu akun GL diambil dari
 * Bagan Akun NYATA (dropdown), bukan diketik bebas.
 */
export default function BankAccountDialog({ open, onOpenChange, account, onDone }) {
  const [form, setForm] = useState({
    name: "", bank_name: "", account_no: "", holder: "", gl_account_code: "",
    opening_balance: 0, note: "", is_active: true,
  });
  const [accounts, setAccounts] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      name: account?.name || "", bank_name: account?.bank_name || "",
      account_no: account?.account_no || "", holder: account?.holder || "",
      gl_account_code: account?.gl_account_code || "1-1200",
      opening_balance: account?.opening_balance || 0, note: account?.note || "",
      is_active: account?.is_active !== false,
    });
    api.get("/gl/accounts")
      .then((r) => setAccounts((r.data.data || [])
        .filter((a) => String(a.code || "").startsWith("1-1"))))
      .catch(() => setAccounts([]));
  }, [open, account]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...form, opening_balance: Number(form.opening_balance) || 0 };
      if (account?.id) await api.put(`/bank/accounts/${account.id}`, body);
      else await api.post("/bank/accounts", body);
      toast.success(account?.id ? "Rekening diperbarui." : "Rekening terdaftar.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan rekening.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{account?.id ? "Ubah rekening bank" : "Daftarkan rekening bank"}</DialogTitle>
          <DialogDescription>
            Rekening ini menjadi pembanding saldo buku (GL) saat rekonsiliasi.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="bank-acc-name">Nama rekening</Label>
            <Input id="bank-acc-name" data-testid={BANK.accountName} value={form.name}
              placeholder="Rekening Operasional" onChange={(e) => set({ name: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bank-acc-bank">Nama bank</Label>
            <Input id="bank-acc-bank" data-testid={BANK.accountBankName} value={form.bank_name}
              placeholder="Bank Mandiri" onChange={(e) => set({ bank_name: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bank-acc-no">Nomor rekening</Label>
            <Input id="bank-acc-no" data-testid={BANK.accountNo} value={form.account_no}
              placeholder="1440012345678" onChange={(e) => set({ account_no: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bank-acc-holder">Nama pemilik rekening</Label>
            <Input id="bank-acc-holder" value={form.holder} placeholder="Nama pemilik rekening"
              onChange={(e) => set({ holder: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label>Akun kas/bank di Bagan Akun</Label>
            <Select value={form.gl_account_code}
              onValueChange={(v) => set({ gl_account_code: v })}>
              <SelectTrigger data-testid={BANK.accountGlSelect}
                aria-label="Akun kas/bank di Bagan Akun">
                <SelectValue placeholder="Pilih akun" />
              </SelectTrigger>
              <SelectContent>
                {accounts.map((a) => (
                  <SelectItem key={a.code} value={a.code}>{a.code} · {a.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bank-acc-open">Saldo awal (Rp)</Label>
            <RupiahInput id="bank-acc-open" value={form.opening_balance}
              onChange={(e) => set({ opening_balance: e.target.value })} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="bank-acc-note">Keterangan</Label>
            <Textarea id="bank-acc-note" rows={2} value={form.note}
              placeholder="Dipakai untuk penerimaan pembeli & pembayaran operasional."
              onChange={(e) => set({ note: e.target.value })} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={BANK.accountSubmit} disabled={busy} onClick={save}>
            {busy ? "Menyimpan…" : "Simpan rekening"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
