import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";

/**
 * Terima pembayaran pembeli.
 *
 * Fase 26 (kebenaran uang): metode pembayaran diambil dari SSOT `/api/reference`
 * (dulu daftar lokal memuat nilai "other" yang tidak dikenal backend), dan bila jumlah
 * melebihi sisa tagihan, kasir HARUS menyetujui secara sadar bahwa kelebihannya dicatat
 * sebagai **titipan pelanggan** (akun 2-1450). Sebelumnya kelebihan bayar hilang tanpa jejak.
 *
 * deal: { deal_id, unit_code, outstanding }
 */
export default function ReceiptDialog({ open, onOpenChange, deal, onDone }) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("transfer");
  const [cashAccountId, setCashAccountId] = useState("");
  const [note, setNote] = useState("");
  const [allowOverpay, setAllowOverpay] = useState(false);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState([]);
  const [alloc, setAlloc] = useState({});

  const fifo = (total, list) => {
    let sisa = Number(total) || 0; const out = {};
    [...list].sort((a, b) => String(a.due_date || "").localeCompare(String(b.due_date || ""))).forEach((it) => {
      const open = Number(it.amount || 0) - Number(it.paid_amount || 0);
      if (open <= 0 || sisa <= 0) return;
      const pay = Math.min(open, sisa); out[it.id] = pay; sisa -= pay;
    });
    return out;
  };

  useEffect(() => {
    if (open && deal?.deal_id) {
      api.get(`/finance/ar/${deal.deal_id}`).then((r) => {
        const list = (r.data?.data?.items || []).filter((it) => Number(it.amount || 0) > Number(it.paid_amount || 0));
        setItems(list); setAlloc(fifo(deal?.outstanding || 0, list));
      }).catch(() => { setItems([]); setAlloc({}); });
    }
  }, [open, deal]);

  useEffect(() => {
    if (open) {
      setAmount(deal?.outstanding ? String(deal.outstanding) : "");
      setMethod("transfer");
      setNote("");
      setAllowOverpay(false);
    }
  }, [open, deal]);

  const outstanding = Number(deal?.outstanding || 0);
  const amt = Number(amount) || 0;
  const excess = Math.max(0, amt - outstanding);
  const blocked = excess > 0 && !allowOverpay;
  const allocSum = Object.values(alloc).reduce((a, v) => a + (Number(v) || 0), 0);
  const allocMismatch = items.length > 0 && allocSum !== Math.min(amt, outstanding);
  const setAmountFifo = (v) => { setAmount(v); setAlloc(fifo(Math.min(Number(v) || 0, outstanding), items)); };

  const submit = async () => {
    if (!deal?.deal_id) return;
    if (!amt || amt <= 0) { toast.error("Masukkan jumlah pembayaran yang valid."); return; }
    if (allocMismatch) { toast.error("Alokasi per termin harus sama dengan jumlah yang dibayar (di luar kelebihan)."); return; }
    setBusy(true);
    try {
      const res = await api.post("/finance/ar/receipts", {
        deal_id: deal.deal_id, amount: amt, method, note: note || null,
        allow_overpay: allowOverpay, cash_account_id: cashAccountId || null,
        allocations: Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([item_id, v]) => ({ item_id, amount: Number(v) })),
      });
      const rec = res.data?.data?.receipt || {};
      const dep = Number(rec.deposit_amount || 0);
      toast.success(
        dep > 0
          ? `Pembayaran diterima — ${formatIDR(dep)} dicatat sebagai titipan pelanggan.`
          : res.data?.data?.paid_off
            ? "Pembayaran diterima — AR LUNAS. Menunggu BAST."
            : "Pembayaran diterima & dialokasikan ke termin.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencatat pembayaran.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Terima Pembayaran</DialogTitle>
          <DialogDescription>
            {deal ? `Unit ${deal.unit_code || "-"} · Sisa ${formatIDR(outstanding)}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="amt">Jumlah (Rp)</Label>
            <RupiahInput id="amt" value={amount} data-testid="ar-receipt-amount"
              onChange={(e) => setAmountFifo(e.target.value)} placeholder="0" />
          </div>
          {items.length ? (
            <div data-testid="ar-receipt-allocation" className="space-y-1.5 rounded-lg border p-2.5">
              <div className="flex items-center justify-between">
                <Label className="text-[12px]">Dialokasikan ke termin</Label>
                <button type="button" data-testid="ar-receipt-alloc-fifo" className="text-[11px] text-primary hover:underline"
                  onClick={() => setAlloc(fifo(Math.min(amt, outstanding), items))}>Isi otomatis (jatuh tempo terlama dulu)</button>
              </div>
              {items.map((it) => {
                const open = Number(it.amount || 0) - Number(it.paid_amount || 0);
                return (
                  <div key={it.id} data-testid="ar-receipt-alloc-row" data-item-id={it.id} className="grid grid-cols-[1fr_9rem] items-center gap-2 text-[12px]">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{it.label}</p>
                      <p className="text-[11px] text-muted-foreground">jatuh tempo {String(it.due_date || "").slice(0, 10)} · sisa {formatIDR(open)}</p>
                    </div>
                    <RupiahInput data-testid="ar-receipt-alloc-amount" aria-label={`Alokasi ${it.label}`} className="h-8"
                      value={alloc[it.id] ?? ""} placeholder="0"
                      onChange={(e) => setAlloc((a) => ({ ...a, [it.id]: Math.min(open, Number(e.target.value) || 0) }))} />
                  </div>
                );
              })}
              <p data-testid="ar-receipt-alloc-sum" className={`text-[11px] ${allocMismatch ? "text-rose-600" : "text-muted-foreground"}`}>
                Total alokasi {formatIDR(allocSum)} dari {formatIDR(Math.min(amt, outstanding))}{allocMismatch ? " — belum sama, sesuaikan." : " ✓"}
              </p>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>Metode</Label>
            <ReferenceSelect group="payment_method" value={method} onChange={setMethod}
              testId="ar-receipt-method" />
          </div>
          <CashAccountSelect value={cashAccountId} onChange={setCashAccountId}
            kind={method === "cash" || method === "tunai" ? "cash" : "bank"}
            label="Masuk ke rekening / kas" testId="ar-receipt-cash-account" />
          <div className="space-y-1.5">
            <Label htmlFor="note">Catatan (opsional)</Label>
            <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="mis. DP 20%, cicilan termin I" rows={2} />
          </div>

          {excess > 0 ? (
            <div data-testid="ar-receipt-overpay-warning"
              className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <p className="flex items-start gap-2 font-medium">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                Jumlah melebihi sisa tagihan {formatIDR(outstanding)}.
              </p>
              <p className="text-[12px] leading-relaxed">
                Kelebihan <span className="font-semibold tabular-nums">{formatIDR(excess)}</span> akan
                dicatat sebagai <span className="font-semibold">Titipan Pelanggan</span> (akun 2-1450),
                bukan pendapatan — nanti bisa dipakai untuk termin berikutnya atau dikembalikan.
              </p>
              <label className="flex items-start gap-2 text-[12px] font-medium">
                <Checkbox data-testid="ar-receipt-allow-overpay" checked={allowOverpay}
                  onCheckedChange={(v) => setAllowOverpay(!!v)} className="mt-0.5" />
                <span>Ya, saya memang menerima kelebihan ini dan mencatatnya sebagai titipan.</span>
              </label>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.receiptSubmit} onClick={submit} disabled={busy || blocked || allocMismatch}>
            {busy ? "Memproses…" : blocked ? "Centang persetujuan dulu" : "Simpan Pembayaran"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
