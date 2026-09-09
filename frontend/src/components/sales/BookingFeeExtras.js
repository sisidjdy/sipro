import React, { useState } from "react";
import { toast } from "sonner";
import { Check, FileText, Undo2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import MoneyText from "@/components/patterns/MoneyText";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import { BOOKING_FEE } from "@/constants/testIds";

/** Bukti transfer booking fee dari portal → verifikasi/tolak satu klik (Keuangan). */
export function BookingFeeProofs({ dealId, proofs = [], mayPay, onChanged }) {
  const [busy, setBusy] = useState("");
  const pending = proofs.filter((p) => p.state === "pending");
  if (!pending.length) return null;
  const act = async (p, action) => {
    let body = {};
    if (action === "reject") {
      const reason = window.prompt("Alasan penolakan (dibaca pembeli, minimal 10 huruf):");
      if (!reason) return;
      body = { reason };
    }
    setBusy(p.id);
    try {
      const res = await api.post(`/booking-fee/deals/${dealId}/proofs/${p.id}/${action}`, body);
      toast.success(res.data.message); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memproses bukti."); }
    finally { setBusy(""); }
  };
  return (
    <div className="mt-2 space-y-1.5">
      {pending.map((p) => (
        <div key={p.id} data-testid={BOOKING_FEE.proofRow}
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-xs">
          <span>Bukti dari pembeli <b>{formatIDR(p.amount)}</b> · transfer {formatDateWIB(p.transfer_date)}{p.bank_name ? ` · ${p.bank_name}` : ""}</span>
          {mayPay ? (
            <span className="flex gap-1">
              <Button size="sm" data-testid={BOOKING_FEE.proofVerifyBtn} disabled={busy === p.id} onClick={() => act(p, "verify")}>
                <Check className="mr-1 h-3.5 w-3.5" /> Verifikasi
              </Button>
              <Button size="sm" variant="ghost" data-testid={BOOKING_FEE.proofRejectBtn} disabled={busy === p.id} onClick={() => act(p, "reject")}>
                <X className="h-3.5 w-3.5" />
              </Button>
            </span>
          ) : <span className="text-muted-foreground">menunggu verifikasi keuangan</span>}
        </div>
      ))}
    </div>
  );
}

/** Refund booking fee untuk deal yang batal: berapa dikembalikan, berapa hangus, cetak bukti. */
export function BookingFeeRefund({ dealId, refund, mayPay, onChanged, openPdf }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ amount: "", method: "transfer", note: "", finalize: true });
  const [busy, setBusy] = useState(false);
  if (!refund || (!refund.eligible && !(refund.refunds || []).length)) return null;
  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/booking-fee/deals/${dealId}/refund`,
        { amount: Number(form.amount) || 0, method: form.method, note: form.note || null, finalize: form.finalize });
      toast.success(res.data.message); setOpen(false); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencatat refund."); }
    finally { setBusy(false); }
  };
  return (
    <div data-testid={BOOKING_FEE.refundBox} className="mt-2 rounded-md border border-amber-200 bg-amber-50/70 p-2.5 text-xs space-y-1.5">
      <p className="font-medium text-amber-900 flex items-center gap-1"><Undo2 className="h-3.5 w-3.5" /> Pengembalian booking fee (deal batal)</p>
      <div className="grid grid-cols-3 gap-2">
        <div><p className="text-muted-foreground">Dibayar</p><MoneyText value={refund.paid} /></div>
        <div><p className="text-muted-foreground">Dikembalikan</p><MoneyText value={refund.refunded_total} className="text-sky-700" /></div>
        <div><p className="text-muted-foreground">Hangus</p><MoneyText value={refund.forfeited_total} className="text-rose-700" /></div>
      </div>
      {(refund.refunds || []).map((r) => (
        <div key={r.id} className="flex items-center justify-between rounded border bg-white px-2 py-1">
          <span>{r.receipt_no} · {formatIDR(r.amount)} dikembalikan{r.forfeited ? ` · ${formatIDR(r.forfeited)} hangus` : ""}</span>
          <Button size="sm" variant="ghost" data-testid={BOOKING_FEE.refundPdf} onClick={() => openPdf(`/booking-fee/deals/${dealId}/refunds/${r.id}/pdf`)}>
            <FileText className="mr-1 h-3.5 w-3.5" /> Cetak
          </Button>
        </div>
      ))}
      {refund.eligible && mayPay ? (
        <Button size="sm" data-testid={BOOKING_FEE.refundBtn}
          onClick={() => { setForm({ amount: String(refund.refundable), method: "transfer", note: "", finalize: true }); setOpen(true); }}>
          Proses refund <MoneyText value={refund.refundable} className="ml-1" />
        </Button>
      ) : refund.eligible ? <p className="text-muted-foreground">Sisa {formatIDR(refund.refundable)} menunggu Keuangan.</p> : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid={BOOKING_FEE.refundDialog} className="max-w-md">
          <DialogHeader>
            <DialogTitle>Refund booking fee</DialogTitle>
            <DialogDescription>Kas keluar dibukukan (titipan turun). Sisa yang tidak dikembalikan dicatat hangus bila ditandai.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="bf-rf-amount">Jumlah dikembalikan (Rp) — maks {formatIDR(refund.refundable)}</Label>
              <RupiahInput id="bf-rf-amount" data-testid={BOOKING_FEE.refundAmount} value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Metode pembayaran</Label>
              <ReferenceSelect group="payment_method" value={form.method} onChange={(v) => setForm({ ...form, method: v })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bf-rf-note">Catatan</Label>
              <Textarea id="bf-rf-note" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox data-testid={BOOKING_FEE.refundFinalize} checked={form.finalize} onCheckedChange={(v) => setForm({ ...form, finalize: !!v })} />
              Tandai sisa {formatIDR(Math.max(0, refund.refundable - (Number(form.amount) || 0)))} sebagai hangus (selesai)
            </label>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Batal</Button>
            <Button data-testid={BOOKING_FEE.refundSubmit} disabled={busy} onClick={submit}>{busy ? "Menyimpan…" : "Simpan refund"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
