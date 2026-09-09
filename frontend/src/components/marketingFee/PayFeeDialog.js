import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { MFEE } from "@/constants/testIds";

/** Pembayaran marketing fee (Dr 2-1500 / Cr kas atau bank), dibatasi sisa utang fee. */
export default function PayFeeDialog({ fee, onClose, onSaved }) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("bank");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const remaining = fee ? Number(fee.amount_net || 0) - Number(fee.paid_amount || 0) : 0;

  useEffect(() => {
    if (fee) { setAmount(String(remaining)); setSource("bank"); setErr(""); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fee]);

  if (!fee) return null;
  const over = Number(amount) > remaining;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post(`/marketing/fees/${fee.id}/pay`, {
        amount: Number(amount), source, note: null,
      });
      toast.success(`Fee ${fee.no} dibayar ${formatIDR(Number(amount))} ke ${fee.agent_name}.`);
      onClose(); onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal membukukan pembayaran fee.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent data-testid={MFEE.payDialog} className="max-w-md">
        <DialogHeader>
          <DialogTitle>Bayar Marketing Fee {fee.no}</DialogTitle>
          <DialogDescription>
            {fee.agent_name} · unit {fee.unit_code || "—"} · sisa utang fee {formatIDR(remaining)}.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="mf-pay-amount">Nominal pembayaran (Rp)</Label>
            <RupiahInput id="mf-pay-amount" data-testid={MFEE.payAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
            {over ? (
              <p className="rounded-md bg-rose-50 p-2 text-xs text-rose-700">
                Melebihi sisa utang fee ({formatIDR(remaining)}). Turunkan nominalnya.
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label>Sumber kas</Label>
            <ReferenceSelect group="cash_source" value={source} onChange={setSource}
              testId={MFEE.paySource} />
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button data-testid={MFEE.payConfirm} disabled={saving || over || !(Number(amount) > 0)}
            onClick={submit}>
            {saving ? "Memproses…" : "Bayar Fee"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
