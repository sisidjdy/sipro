import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Receipt, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { formatDateTimeWIB, formatDateWIB } from "@/utils/formatters";
import { BOOKING_FEE } from "@/constants/testIds";
import { BookingFeeProofs, BookingFeeRefund } from "@/components/sales/BookingFeeExtras";

const STATUS_TONE = { unpaid: "unpaid", partial: "partial", paid: "paid", cancelled: "cancelled" };

/**
 * BookingFeePanel — booking fee sebagai KOMPONEN PEMBAYARAN terpisah (Fase 69B):
 * tagihan INV-BF (status lunas/belum), kwitansi bernomor, dan pencatatan pembayaran (keuangan).
 */
export default function BookingFeePanel({ dealId, compact = false, onChanged }) {
  const { can } = useAuth();
  const { labelOf } = useReference();
  const mayPay = can("finance", "create");
  const [data, setData] = useState(null);
  const [payOpen, setPayOpen] = useState(false);
  const [form, setForm] = useState({ amount: "", method: "transfer", note: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!dealId) return;
    api.get(`/booking-fee/deals/${dealId}`).then((r) => setData(r.data.data)).catch(() => setData({}));
  }, [dealId]);
  useEffect(() => { load(); }, [load]);

  const inv = data?.invoice;
  const openPay = () => { setForm({ amount: String(inv?.outstanding || ""), method: "transfer", note: "" }); setPayOpen(true); };
  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/booking-fee/deals/${dealId}/pay`,
        { amount: Number(form.amount) || 0, method: form.method, note: form.note || null });
      toast.success(res.data.message || "Pembayaran booking fee dicatat.");
      setPayOpen(false); load(); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencatat pembayaran."); }
    finally { setBusy(false); }
  };
  const openPdf = async (url) => {
    try {
      const res = await api.get(url, { responseType: "blob" });
      window.open(URL.createObjectURL(res.data), "_blank", "noopener");
    } catch { toast.error("Gagal membuka PDF."); }
  };

  if (data === null) return <p className="text-xs text-muted-foreground">Memuat booking fee…</p>;
  if (!inv) {
    return (
      <p data-testid={BOOKING_FEE.none} className="text-xs text-muted-foreground">
        Tidak ada tagihan booking fee (reservasi tanpa booking fee atau dibuat sebelum fitur ini).
      </p>
    );
  }

  return (
    <div data-testid={BOOKING_FEE.panel} className={`rounded-lg border bg-card p-3 shadow-[var(--shadow-card)] ${compact ? "" : "space-y-2"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Wallet className="h-4 w-4 text-primary" />
          <div>
            <p className="text-sm font-medium">Booking fee · <span className="font-mono text-xs">{inv.no}</span></p>
            <p className="text-xs text-muted-foreground">
              Jatuh tempo {inv.due_date ? formatDateWIB(inv.due_date) : "-"} · dibayar di awal, dialihkan ke termin saat booking
            </p>
          </div>
        </div>
        <StatusPill data-testid={BOOKING_FEE.status} status={STATUS_TONE[inv.status]}
          label={["cancelled", "refunded", "forfeited"].includes(inv.status)
            ? { cancelled: "Dibatalkan", refunded: "Dikembalikan", forfeited: "Hangus" }[inv.status]
            : labelOf("ar_status", inv.status)} />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
        <div><p className="text-xs text-muted-foreground">Tagihan</p><MoneyText value={inv.amount} className="font-medium" /></div>
        <div><p className="text-xs text-muted-foreground">Dibayar</p><MoneyText value={inv.paid} className="text-emerald-700" /></div>
        <div><p className="text-xs text-muted-foreground">Sisa</p><MoneyText data-testid={BOOKING_FEE.outstanding} value={inv.outstanding} className={inv.outstanding ? "text-rose-700" : ""} /></div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Button size="sm" variant="outline" data-testid={BOOKING_FEE.invoicePdf}
          onClick={() => openPdf(`/booking-fee/deals/${dealId}/invoice/pdf`)}>
          <FileText className="mr-1 h-3.5 w-3.5" /> Tagihan PDF
        </Button>
        {(data.receipts || []).map((r) => (
          <Button key={r.id} size="sm" variant="ghost" data-testid={BOOKING_FEE.receiptPdf}
            onClick={() => openPdf(`/finance/ar/receipts/${r.id}/pdf`)} title={formatDateTimeWIB(r.created_at)}>
            <Receipt className="mr-1 h-3.5 w-3.5" /> {r.receipt_no}
          </Button>
        ))}
        {mayPay && ["unpaid", "partial"].includes(inv.status) ? (
          <Button size="sm" data-testid={BOOKING_FEE.payBtn} onClick={openPay}>Catat pembayaran</Button>
        ) : null}
        {!mayPay && ["unpaid", "partial"].includes(inv.status) ? (
          <span className="text-xs text-muted-foreground">Pencatatan pembayaran oleh Keuangan.</span>
        ) : null}
      </div>
      <BookingFeeProofs dealId={dealId} proofs={data.proofs} mayPay={mayPay}
        onChanged={() => { load(); onChanged?.(); }} />
      <BookingFeeRefund dealId={dealId} refund={data.refund} mayPay={mayPay} openPdf={openPdf}
        onChanged={() => { load(); onChanged?.(); }} />

      <Dialog open={payOpen} onOpenChange={setPayOpen}>
        <DialogContent data-testid={BOOKING_FEE.payDialog} className="max-w-md">
          <DialogHeader>
            <DialogTitle>Catat pembayaran booking fee {inv.no}</DialogTitle>
            <DialogDescription>
              Melahirkan kwitansi bernomor dan dibukukan sebagai titipan pelanggan (2-1450) sampai dialihkan ke termin.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="bf-amount">Nominal diterima (Rp)</Label>
              <RupiahInput id="bf-amount" data-testid={BOOKING_FEE.payAmount} value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              <p className="text-xs text-muted-foreground">Sisa tagihan <MoneyText value={inv.outstanding} />.</p>
            </div>
            <div className="space-y-1.5">
              <Label>Metode pembayaran</Label>
              <ReferenceSelect group="payment_method" value={form.method} testId={BOOKING_FEE.payMethod}
                onChange={(v) => setForm({ ...form, method: v })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bf-note">Catatan</Label>
              <Textarea id="bf-note" rows={2} value={form.note} placeholder="Mis. transfer BCA a.n. pembeli"
                onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPayOpen(false)}>Batal</Button>
            <Button data-testid={BOOKING_FEE.paySubmit} disabled={busy || !Number(form.amount)} onClick={submit}>
              {busy ? "Menyimpan…" : "Simpan kwitansi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
