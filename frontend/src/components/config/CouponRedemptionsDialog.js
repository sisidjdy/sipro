import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { formatDateTimeWIB } from "@/utils/formatters";
import { PRICING } from "@/constants/testIds";

/** Riwayat pemakaian satu kupon — siapa, unit apa, kapan, masih terpakai atau dilepas. */
export default function CouponRedemptionsDialog({ coupon, open, onOpenChange }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !coupon?.id) return;
    setRows(null); setError("");
    api.get(`/pricing/coupons/${coupon.id}/redemptions`)
      .then((r) => setRows(r.data.data?.rows || []))
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat riwayat kupon."));
  }, [open, coupon]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PRICING.redemptionsDialog} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Pemakaian kupon {coupon?.code}</DialogTitle>
          <DialogDescription>
            {coupon?.used_count || 0}{coupon?.quota_total ? ` dari ${coupon.quota_total}` : ""} kuota
            terpakai · {coupon?.quota_per_customer ? `${coupon.quota_per_customer}× per pembeli` : "tanpa batas per pembeli"}.
          </DialogDescription>
        </DialogHeader>
        {error ? <ErrorState message={error} /> : rows === null ? <LoadingCards count={3} /> : (
          <div className="max-h-[60vh] overflow-y-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-1.5 text-left">Pembeli</th>
                  <th className="px-3 py-1.5 text-left">Unit</th>
                  <th className="px-3 py-1.5 text-left">Waktu</th>
                  <th className="px-3 py-1.5 text-right">Potongan</th>
                  <th className="px-3 py-1.5 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((r) => (
                  <tr key={r.id} data-testid={PRICING.redemptionRow}>
                    <td className="px-3 py-1.5">
                      {r.lead_id ? (
                        <Link className="text-primary hover:underline" to={`/leads/${r.lead_id}`}>{r.lead_name || "Lead"}</Link>
                      ) : (r.lead_name || "-")}
                    </td>
                    <td className="px-3 py-1.5">{r.unit_code || "-"}</td>
                    <td className="px-3 py-1.5 text-xs text-muted-foreground">
                      {r.used_at ? formatDateTimeWIB(r.used_at) : "-"}
                      {r.released_at ? <div>dilepas {formatDateTimeWIB(r.released_at)}</div> : null}
                    </td>
                    <td className="px-3 py-1.5 text-right"><MoneyText value={r.amount} /></td>
                    <td className="px-3 py-1.5"><StatusPill status={r.state} group="coupon_redemption_state" /></td>
                  </tr>
                ))}
                {!rows.length ? (
                  <tr><td colSpan={5} className="px-3 py-3 text-center text-sm text-muted-foreground">
                    Kupon ini belum pernah dipakai.
                  </td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
