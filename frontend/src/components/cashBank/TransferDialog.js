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
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";
import api from "@/services/apiClient";
import { CASHBANK } from "@/constants/testIds";

const KIND_RULE = {
  transfer: { from: null, to: null, help: "Pindah dana antar rekening bank / kas." },
  setor_tunai: { from: "cash", to: "bank", help: "Uang tunai kas disetor ke rekening bank." },
  tarik_tunai: { from: "bank", to: "cash", help: "Tarik dana dari bank ke kas tunai." },
  isi_kas_kecil: { from: null, to: "cash", help: "Pengisian (replenish) kas kecil dari bank/kas besar." },
};

/** Ajukan transaksi internal (transfer/setor/tarik/isi kas kecil). Diposting setelah disetujui (SoD). */
export default function TransferDialog({ open, kinds, onClose, onSaved }) {
  const [form, setForm] = useState({ kind: "transfer", from_account_id: "", to_account_id: "", amount: "", fee: "", date: "", reference: "", note: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (open) {
      setForm({ kind: "transfer", from_account_id: "", to_account_id: "", amount: "", fee: "",
        date: new Date().toISOString().slice(0, 10), reference: "", note: "" });
      setErr("");
    }
  }, [open]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const rule = KIND_RULE[form.kind] || KIND_RULE.transfer;
  const same = form.from_account_id && form.from_account_id === form.to_account_id;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      const r = await api.post("/cash-bank/transfers", {
        ...form, amount: Number(form.amount || 0), fee: Number(form.fee || 0),
        reference: form.reference || null, note: form.note || null,
      });
      toast.success(`${r.data.data.no} diajukan — menunggu persetujuan.`);
      onSaved?.(); onClose();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal mengajukan transaksi.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid={CASHBANK.transferDialog}>
        <DialogHeader>
          <DialogTitle>Transaksi Internal Kas & Bank</DialogTitle>
          <DialogDescription>{rule.help} Jurnal diposting setelah disetujui supervisor keuangan.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Jenis</Label>
            <Select value={form.kind} onValueChange={(v) => setForm((f) => ({ ...f, kind: v, from_account_id: "", to_account_id: "" }))}>
              <SelectTrigger data-testid={CASHBANK.transferKind} className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {(kinds || []).map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <CashAccountSelect key={`from-${form.kind}`} label="Dari" kind={rule.from} value={form.from_account_id}
              onChange={(v) => set("from_account_id", v)} testId={CASHBANK.transferFrom} />
            <CashAccountSelect key={`to-${form.kind}`} label="Ke" kind={rule.to} value={form.to_account_id}
              exclude={form.from_account_id}
              onChange={(v) => set("to_account_id", v)} testId={CASHBANK.transferTo} />
          </div>
          {same ? <p className="text-xs text-rose-600">Rekening asal dan tujuan tidak boleh sama.</p> : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Nominal</Label>
              <RupiahInput value={form.amount} onChange={(e) => set("amount", e.target.value)} data-testid={CASHBANK.transferAmount} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Biaya transfer/admin (opsional)</Label>
              <RupiahInput value={form.fee} onChange={(e) => set("fee", e.target.value)} data-testid={CASHBANK.transferFee} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Tanggal</Label>
              <Input type="date" value={form.date} onChange={(e) => set("date", e.target.value)} className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Referensi (no. bukti)</Label>
              <Input value={form.reference} onChange={(e) => set("reference", e.target.value)} className="h-9" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Catatan</Label>
            <Textarea rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} data-testid={CASHBANK.transferNote} />
          </div>
          {err ? <p className="text-sm text-rose-600" data-testid="cashbank-transfer-error">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} data-testid={CASHBANK.transferSubmit}
            disabled={saving || same || !form.from_account_id || !form.to_account_id || Number(form.amount) <= 0}>
            {saving ? "Menyimpan…" : "Ajukan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
