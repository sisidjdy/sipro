import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PETTY } from "@/constants/testIds";

/** Pencairan kas bon oleh finance: kas keluar → uang muka karyawan (1-1500). */
export default function DisburseAdvanceDialog({ advance, onClose, onSaved }) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("bank");
  const [cashAccountId, setCashAccountId] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (advance) {
      setAmount(String(advance.amount_requested || ""));
      setSource("bank"); setNote(""); setErr("");
    }
  }, [advance]);

  if (!advance) return null;
  const requested = Number(advance.amount_requested || 0);
  const over = Number(amount) > requested;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post(`/petty-cash/advances/${advance.id}/disburse`, {
        amount: Number(amount), source, note: note || null, cash_account_id: cashAccountId || null,
      });
      toast.success(`Kas bon ${advance.no} dicairkan ${formatIDR(Number(amount))}.`);
      onClose(); onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal mencairkan kas bon.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent data-testid={PETTY.disburseDialog} className="max-w-md">
        <DialogHeader>
          <DialogTitle>Cairkan Kas Bon {advance.no}</DialogTitle>
          <DialogDescription>
            {advance.purpose} · disetujui {formatIDR(requested)}. Jurnal: Dr 1-1500 Uang Muka
            Karyawan / Cr kas atau bank.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="pc-dis-amount">Nominal dicairkan (Rp)</Label>
            <RupiahInput id="pc-dis-amount" data-testid={PETTY.disburseAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
            {over ? (
              <p className="rounded-md bg-rose-50 p-2 text-xs text-rose-700">
                Nominal melebihi yang disetujui ({formatIDR(requested)}). Turunkan nominalnya.
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label>Sumber kas</Label>
            <ReferenceSelect group="cash_source" value={source} onChange={setSource}
              testId={PETTY.disburseSource} />
          </div>
          <CashAccountSelect value={cashAccountId} onChange={setCashAccountId}
            kind={["kas", "cash", "tunai"].includes(source) ? "cash" : "bank"} label="Dari rekening / kas"
            testId="pc-dis-cash-account" />
          <div className="space-y-1.5">
            <Label htmlFor="pc-dis-note">Catatan</Label>
            <Textarea id="pc-dis-note" value={note} rows={2} placeholder="Mis. tunai via kasir"
              onChange={(e) => setNote(e.target.value)} />
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button data-testid={PETTY.disburseSubmit} onClick={submit}
            disabled={saving || over || !(Number(amount) > 0)}>
            {saving ? "Memproses…" : "Cairkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
