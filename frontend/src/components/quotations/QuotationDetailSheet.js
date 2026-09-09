import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2, FileDown, Handshake, History, Send, SquarePen, XCircle,
} from "lucide-react";

import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import StatusPill from "@/components/patterns/StatusPill";
import QuotationBreakdown from "@/components/quotations/QuotationBreakdown";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { QUOTE } from "@/constants/testIds";

const MIN_REASON = 5;

/**
 * QuotationDetailSheet — satu penawaran beserta SEMUA yang membuatnya bisa dipertanggung-
 * jawabkan: rincian harga, termin, simulasi KPR, keputusan diskon, pengiriman, dan riwayat.
 *
 * Pemisahan tugas dipaksakan di layar: tombol Setujui/Tolak diskon hanya muncul untuk peran
 * yang memang berwenang (manajer sales/direksi) — sales pembuat penawaran tidak bisa
 * menyetujui diskonnya sendiri.
 */
export default function QuotationDetailSheet({ quotationId, open, onOpenChange, onChanged,
  onRevise }) {
  const { can } = useAuth();
  const [q, setQ] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  // Izin EFEKTIF dari `GET /auth/me` (bukan salinan daftar peran): keputusan diskon
  // dipaksakan router dengan `quotations:approve`, sedangkan kirim/konversi/revisi dengan
  // `quotations:update`. Menyalin nama peran ke layar membuat tombol mati (selalu 403) atau
  // tombol hilang untuk peran yang sebenarnya berhak begitu admin mengubah matriks RBAC.
  const canApprove = can("quotations", "approve");
  const canUpdate = can("quotations", "update");

  const load = useCallback(async () => {
    if (!quotationId) return;
    setLoading(true); setError(""); setMode(""); setReason("");
    try {
      const res = await api.get(`/quotations/${quotationId}`);
      setQ(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat penawaran.");
    } finally { setLoading(false); }
  }, [quotationId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const run = async (fn, okMsg) => {
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.data?.message || okMsg);
      await load();
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal diproses.");
    } finally { setBusy(false); }
  };

  const decide = (approve) => run(
    () => api.post(`/quotations/${quotationId}/decision`, { approve, reason: reason.trim() }),
    approve ? "Diskon disetujui." : "Diskon ditolak.",
  );

  const downloadPdf = async () => {
    setBusy(true);
    try {
      const res = await api.get(`/quotations/${quotationId}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) {
      toast.error("Gagal mengunduh PDF penawaran.");
    } finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={QUOTE.detail}
        className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {q ? `${q.no} v${q.version}` : "Penawaran"}
            {q ? <StatusPill status={q.state} group="quotation_state" /> : null}
          </SheetTitle>
          <SheetDescription>
            {q ? (
              <>
                {q.lead_name} · unit {q.unit_code} · berlaku sampai{" "}
                {formatDateWIB(q.valid_until)}
              </>
            ) : null}
          </SheetDescription>
        </SheetHeader>

        {loading ? <div className="mt-4"><LoadingCards count={3} /></div> : null}
        {error ? <div className="mt-4"><ErrorState message={error} onRetry={load} /></div> : null}

        {q && !loading && !error ? (
          <div className="mt-4 space-y-4">
            <QuotationBreakdown calc={q} />

            {q.discount_reason ? (
              <div className="rounded-lg border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
                <p className="text-xs font-medium uppercase text-muted-foreground">
                  Alasan diskon
                </p>
                <p className="mt-1">{q.discount_reason}</p>
                {q.decision_reason ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Keputusan {q.approved_by || "-"}: {q.decision_reason}
                  </p>
                ) : null}
              </div>
            ) : null}

            {q.state === "awaiting_approval" ? (
              <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm text-amber-900">
                  Penawaran ini <b>belum bisa dikonversi</b> menjadi reservasi sampai diskonnya
                  diputuskan manajer.
                </p>
                {canApprove ? (
                  <>
                    <div className="space-y-1.5">
                      <Label htmlFor="q-decision-reason">
                        Dasar keputusan (wajib, minimal {MIN_REASON} huruf)
                      </Label>
                      <Textarea id="q-decision-reason" rows={2} value={reason}
                        data-testid={QUOTE.decisionReason} className="bg-background"
                        placeholder="Mis. unit slow moving, margin masih di atas ambang."
                        onChange={(e) => setReason(e.target.value)} />
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" data-testid={QUOTE.approveBtn}
                        disabled={busy || reason.trim().length < MIN_REASON}
                        onClick={() => decide(true)}>
                        <CheckCircle2 className="mr-1.5 h-4 w-4" /> Setujui diskon
                      </Button>
                      <Button size="sm" variant="destructive" data-testid={QUOTE.rejectBtn}
                        disabled={busy || reason.trim().length < MIN_REASON}
                        onClick={() => decide(false)}>
                        <XCircle className="mr-1.5 h-4 w-4" /> Tolak diskon
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-amber-800">
                    Menunggu manajer sales — pembuat penawaran tidak boleh menyetujui
                    diskonnya sendiri.
                  </p>
                )}
              </div>
            ) : null}

            {q.sent_at ? (
              <p className="text-xs text-muted-foreground">
                Dikirim {formatDateTimeWIB(q.sent_at)} lewat {q.sent_channel} · status{" "}
                {q.sent_status}
              </p>
            ) : null}
            {q.converted_deal_id ? (
              <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                Sudah menjadi reservasi unit {q.unit_code} pada{" "}
                {formatDateTimeWIB(q.converted_at)}.
              </p>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" data-testid={QUOTE.pdfBtn} disabled={busy}
                onClick={downloadPdf}>
                <FileDown className="mr-1.5 h-4 w-4" /> PDF
              </Button>
              {canUpdate && ["draft", "approved", "sent"].includes(q.state) ? (
                <Button size="sm" variant="outline" data-testid={QUOTE.sendBtn} disabled={busy}
                  onClick={() => run(() => api.post(`/quotations/${quotationId}/send`,
                    { channel: "whatsapp" }), "Penawaran dikirim.")}>
                  <Send className="mr-1.5 h-4 w-4" /> Kirim WhatsApp
                </Button>
              ) : null}
              {canUpdate && ["draft", "approved", "sent"].includes(q.state) ? (
                <Button size="sm" data-testid={QUOTE.convertBtn} disabled={busy}
                  onClick={() => run(() => api.post(`/quotations/${quotationId}/convert`),
                    "Penawaran menjadi reservasi unit.")}>
                  <Handshake className="mr-1.5 h-4 w-4" /> Jadikan reservasi
                </Button>
              ) : null}
              {canUpdate && q.state !== "converted" && q.state !== "superseded" ? (
                <Button size="sm" variant="secondary" data-testid={QUOTE.reviseBtn}
                  onClick={() => { onOpenChange(false); onRevise?.(q); }}>
                  <SquarePen className="mr-1.5 h-4 w-4" /> Revisi (versi baru)
                </Button>
              ) : null}
            </div>

            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="flex items-center gap-1.5 text-xs font-medium uppercase text-muted-foreground">
                <History className="h-3.5 w-3.5" /> Riwayat
              </p>
              <ul className="mt-1.5 space-y-1 text-xs">
                {(q.history || []).map((h, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="tabular-nums text-muted-foreground">
                      {formatDateTimeWIB(h.at)}
                    </span>
                    <span>{h.action}{h.reason ? ` — ${h.reason}` : ""} ({h.by})</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
