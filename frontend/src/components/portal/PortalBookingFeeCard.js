import React from "react";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { PORTAL_BF } from "@/constants/testIds";

const STATUS = { unpaid: "Belum dibayar", partial: "Dibayar sebagian", paid: "Lunas",
  cancelled: "Dibatalkan", refunded: "Dikembalikan", forfeited: "Hangus" };
const TONE = { paid: "text-emerald-700 bg-emerald-50 border-emerald-200",
  refunded: "text-sky-700 bg-sky-50 border-sky-200" };

/** Kartu booking fee di Portal Pembeli: tagihan paling awal, statusnya, bukti, kwitansi, refund. */
export default function PortalBookingFeeCard({ bf, dealId, unitCode, onProof }) {
  if (!bf?.invoice) return null;
  const inv = bf.invoice;
  const pending = (bf.proofs || []).find((p) => p.state === "pending");
  const canPay = ["unpaid", "partial"].includes(inv.status);
  return (
    <div data-testid={PORTAL_BF.card} className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-indigo-950">Booking fee · {inv.no}</p>
          <p className="text-xs text-indigo-900/80">
            Dibayar paling awal untuk mengunci unit {unitCode || "-"} · jatuh tempo {inv.due_date ? formatDateWIB(inv.due_date) : "-"}
          </p>
        </div>
        <span data-testid={PORTAL_BF.status}
          className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONE[inv.status] || "text-amber-800 bg-amber-50 border-amber-200"}`}>
          {STATUS[inv.status] || inv.status}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div><p className="text-xs text-slate-500">Tagihan</p><p className="font-semibold tabular-nums">{formatIDR(inv.amount)}</p></div>
        <div><p className="text-xs text-slate-500">Dibayar</p><p className="font-semibold tabular-nums text-emerald-600">{formatIDR(inv.paid)}</p></div>
        <div><p className="text-xs text-slate-500">Sisa</p><p className="font-semibold tabular-nums text-rose-600">{formatIDR(inv.outstanding)}</p></div>
      </div>
      {(bf.receipts || []).length ? (
        <p className="text-xs text-slate-600">
          Kwitansi: {(bf.receipts || []).map((r) => r.receipt_no).join(", ")}
        </p>
      ) : null}
      {(bf.proofs || []).map((p) => (
        <div key={p.id} data-testid={PORTAL_BF.proofRow} data-state={p.state}
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-white px-3 py-2 text-xs">
          <span>Bukti {formatIDR(p.amount)} · transfer {formatDateWIB(p.transfer_date)}</span>
          <span className="font-semibold">{p.state_label}</span>
          {p.reject_reason ? <span className="w-full text-rose-700">Alasan: {p.reject_reason}</span> : null}
        </div>
      ))}
      {(bf.refunds || []).map((r) => (
        <div key={r.id} className="rounded-lg border bg-white px-3 py-2 text-xs">
          Refund {r.receipt_no}: {formatIDR(r.amount)} dikembalikan{r.forfeited ? ` · ${formatIDR(r.forfeited)} hangus` : ""}
        </div>
      ))}
      {canPay && !pending ? (
        <Button size="sm" data-testid={PORTAL_BF.proofBtn}
          onClick={() => onProof({ deal_id: dealId, unit_code: unitCode, summary: { outstanding: inv.outstanding } })}>
          <Upload className="mr-1.5 h-4 w-4" /> Kirim bukti transfer booking fee
        </Button>
      ) : null}
      {pending ? <p className="text-xs text-slate-600">Bukti Anda sedang diverifikasi keuangan.</p> : null}
    </div>
  );
}
