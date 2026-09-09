import React, { useCallback, useEffect, useState } from "react";
import { ReceiptText, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import IntakeReviewDialog from "@/components/finance/IntakeReviewDialog";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { INTAKE } from "@/constants/testIds";

/**
 * PaymentIntakePanel (Fase 47B, sisi finance) — bukti transfer yang dikirim pelanggan dari
 * Portal.
 *
 * Aturan yang dijaga layar ini: **bukti = KLAIM, bukan pelunasan**. Selama masih menunggu,
 * tagihan pelanggan TIDAK berkurang sedikit pun; itu dinyatakan terang-terangan di panel
 * (dulu “saya sudah transfer” hanya beredar di WhatsApp dan status pembayaran menjadi tafsir
 * masing-masing pihak). Penolakan wajib beralasan karena alasannya DIBACA PELANGGAN.
 */
export default function PaymentIntakePanel({ onChanged }) {
  const { can } = useAuth();
  // Memutuskan bukti transfer (verifikasi/tolak) dipaksakan router dengan `finance:approve`.
  // Peran lain tetap boleh MELIHAT riwayatnya — tombolnya berubah menjadi "Lihat".
  const canDecide = can("finance", "approve");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [review, setReview] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/payment-intakes", { params: { limit: 50 } });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat bukti transfer pelanggan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const rows = data?.data || [];
  const summary = data?.summary || {};

  return (
    <div data-testid={INTAKE.panel} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-heading text-lg font-semibold">Bukti transfer dari pelanggan</h3>
          <p className="text-sm text-muted-foreground">
            Klaim pembeli lewat Portal. Tagihan berubah HANYA setelah finance memverifikasi.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm text-amber-800">
          <ShieldAlert className="h-4 w-4" />
          {summary.pending || 0} menunggu verifikasi
          {summary.pending_amount
            ? <> · <MoneyText value={summary.pending_amount} /></>
            : null}
        </div>
      </div>

      {loading ? <LoadingCards count={2} /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}

      {!loading && !error && !rows.length ? (
        <EmptyState icon={ReceiptText} title="Belum ada bukti transfer masuk"
          description="Pelanggan dapat mengunggah bukti transfer dari Portal Pelanggan (menu Pembayaran). Bukti yang masuk akan muncul di sini untuk diverifikasi." />
      ) : null}

      {!loading && !error && rows.length ? (
        <div data-testid={INTAKE.table} className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Pelanggan / unit</th>
                <th className="px-3 py-2 text-left">Transfer</th>
                <th className="px-3 py-2 text-right">Nominal</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <tr key={r.id} data-testid={INTAKE.row} data-state={r.state}>
                  <td className="px-3 py-2">
                    <p className="font-medium">{r.customer_name || "-"}</p>
                    <p className="text-xs text-muted-foreground">
                      Unit {r.unit_code || "-"} · {(r.files || []).length} lampiran
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <p className="tabular-nums">{formatDateWIB(r.transfer_date)}</p>
                    <p className="text-xs text-muted-foreground">{r.bank_name || "bank tidak disebut"}</p>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <MoneyText value={r.amount} className="font-medium" />
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={r.state} group="payment_intake_state" />
                    {r.reject_reason ? (
                      <p className="mt-0.5 max-w-[18rem] text-xs text-rose-700">{r.reject_reason}</p>
                    ) : null}
                    {r.state === "verified" && r.verified_by ? (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        oleh {r.verified_by}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant={r.state === "pending" && canDecide
                      ? "default" : "outline"}
                      data-testid={INTAKE.reviewBtn} data-intake={r.id}
                      aria-label={`Tinjau bukti transfer ${r.customer_name || ""}`}
                      onClick={() => setReview(r)}>
                      {r.state === "pending" && canDecide ? "Tinjau & verifikasi" : "Lihat"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <IntakeReviewDialog intake={review} open={!!review} canDecide={canDecide}
        onOpenChange={(v) => !v && setReview(null)}
        onDone={() => { load(); onChanged?.(); }} />
    </div>
  );
}
