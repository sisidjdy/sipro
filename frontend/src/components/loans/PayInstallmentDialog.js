import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOANS } from "@/constants/testIds";

/** Bayar angsuran: alokasi otomatis bunga dulu lalu pokok, dengan guard sisa angsuran. */
export default function PayInstallmentDialog({ data, onClose, onSaved }) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("bank");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const item = data?.item;
  // `amount_due` datang dari backend (sisa angsuran) — satu sumber kebenaran;
  // fallback dihitung lokal agar tetap aman bila field belum ada.
  const remaining = item
    ? Number(item.amount_due ?? (Number(item.total || 0) - Number(item.paid_total || 0)))
    : 0;

  useEffect(() => {
    if (item) { setAmount(String(remaining)); setSource("bank"); setErr(""); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (!data) return null;
  const over = Number(amount) > remaining;
  // Pratinjau alokasi selalu dihitung dari nominal yang SAH (dibatasi sisa angsuran),
  // supaya angka yang ditampilkan tidak pernah menyesatkan saat pengguna salah ketik.
  const effective = Math.min(Math.max(0, Number(amount) || 0), remaining);
  const remInterest = Math.max(0, Number(item.interest || 0) - Number(item.paid_interest || 0));
  const payInterest = Math.min(effective, remInterest);
  const payPrincipal = Math.max(0, effective - payInterest);

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post(`/corp-financing/loans/${data.loan.id}/pay`, {
        installment_no: item.no, amount: Number(amount), source, note: null,
      });
      toast.success(`Angsuran ke-${item.no} dibayar ${formatIDR(Number(amount))}.`);
      onClose(); onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal membukukan pembayaran angsuran.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent data-testid={LOANS.payDialog} className="max-w-md">
        <DialogHeader>
          <DialogTitle>Bayar Angsuran ke-{item.no}</DialogTitle>
          <DialogDescription>
            {data.loan.lender} · jatuh tempo {formatDateWIB(item.due_date)} · sisa angsuran{" "}
            {formatIDR(remaining)}.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ln-pay-amount">Nominal pembayaran (Rp)</Label>
            <RupiahInput id="ln-pay-amount" data-testid={LOANS.payAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
            {over ? (
              <p className="rounded-md bg-rose-50 p-2 text-xs text-rose-700">
                Melebihi sisa angsuran ({formatIDR(remaining)}). Turunkan nominalnya.
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label>Sumber kas</Label>
            <ReferenceSelect group="cash_source" value={source} onChange={setSource}
              testId={LOANS.paySource} />
          </div>
          <div className="rounded-lg border bg-secondary/40 p-3 text-sm">
            <p>Alokasi: bunga <span className="font-semibold tabular-nums">{formatIDR(payInterest)}</span>
              {" "}· pokok <span className="font-semibold tabular-nums">{formatIDR(payPrincipal)}</span></p>
            <p className="mt-1 text-xs text-muted-foreground">
              Dr 2-2100 (pokok) + Dr 6-1600 (bunga) / Cr kas atau bank.
            </p>
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button data-testid={LOANS.paySubmit} disabled={saving || over || !(Number(amount) > 0)}
            onClick={submit}>
            {saving ? "Memproses…" : "Bayar Angsuran"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
