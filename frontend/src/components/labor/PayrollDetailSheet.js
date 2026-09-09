import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BanknoteArrowUp, CheckCircle2, Send, XCircle } from "lucide-react";

import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateWIB, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LABOR } from "@/constants/testIds";

const MIN_REASON = 5;

/**
 * PayrollDetailSheet — satu rekap upah, BARIS PER ORANG, beserti tombol keputusannya.
 *
 * Pemisahan tugas: yang MENCATAT kehadiran (pelaksana/PM) mengajukan; yang MENYETUJUI &
 * MEMBAYAR (keuangan) berbeda orang. Karena itu tombol di sini muncul sesuai peran, dan
 * penolakan wajib beralasan (alasan dibaca pengaju supaya bisa diperbaiki).
 */
export default function PayrollDetailSheet({ payrollId, open, onOpenChange, onChanged,
  canSubmit, canApprove }) {
  const [p, setP] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!payrollId) return;
    setLoading(true); setError(""); setReason("");
    try {
      const res = await api.get(`/labor/payrolls/${payrollId}`);
      setP(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rekap upah.");
    } finally { setLoading(false); }
  }, [payrollId]);

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

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={LABOR.payrollDetail}
        className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {p ? p.no : "Rekap upah"}
            {p ? <StatusPill status={p.state} group="payroll_state" /> : null}
          </SheetTitle>
          <SheetDescription>
            {p ? (
              <>
                {p.project_name} · periode {formatDateWIB(p.period_start)} –{" "}
                {formatDateWIB(p.period_end)} · {p.worker_count} orang
              </>
            ) : null}
          </SheetDescription>
        </SheetHeader>

        {loading ? <div className="mt-4"><LoadingCards count={3} /></div> : null}
        {error ? <div className="mt-4"><ErrorState message={error} onRetry={load} /></div> : null}

        {p && !loading && !error ? (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="text-[11px] text-muted-foreground">Upah pokok</p>
                <MoneyText value={p.base_total} className="text-sm font-semibold" />
              </div>
              <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="text-[11px] text-muted-foreground">
                  Lembur ({p.overtime_hours || 0} jam)
                </p>
                <MoneyText value={p.overtime_total} className="text-sm font-semibold" />
              </div>
              <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="text-[11px] text-muted-foreground">Total dibayar</p>
                <MoneyText value={p.total} className="text-sm font-semibold text-emerald-700" />
              </div>
            </div>

            <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <table className="w-full text-sm">
                <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left">Orang</th>
                    <th className="px-3 py-2 text-right">Hari</th>
                    <th className="px-3 py-2 text-right">Lembur</th>
                    <th className="px-3 py-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(p.lines || []).map((l) => (
                    <tr key={l.worker_id}>
                      <td className="px-3 py-2">
                        <p className="font-medium">{l.worker_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {l.role_label || l.role} · tarif <MoneyText value={l.daily_wage} />
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          {(l.dates || []).join(", ")}
                        </p>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{l.days}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {l.overtime_hours || 0} jam
                      </td>
                      <td className="px-3 py-2 text-right">
                        <MoneyText value={l.total} className="font-medium" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {p.journal_id ? (
              <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                Sudah dibayar {formatDateTimeWIB(p.paid_at)} · jurnal {p.journal_no || p.journal_id}
                {" "}(Dr Pekerjaan dalam proses / Cr Bank).
              </p>
            ) : null}
            {p.decision_reason ? (
              <p className="rounded-md border bg-secondary/50 px-3 py-2 text-sm">
                Keputusan {p.approved_by || "-"}: {p.decision_reason}
              </p>
            ) : null}

            {(canApprove && ["submitted"].includes(p.state))
              || (canApprove && p.state === "approved") ? (
                <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  {p.state === "submitted" ? (
                    <>
                      <div className="space-y-1.5">
                        <Label htmlFor="payroll-reason">
                          Dasar keputusan (wajib bila menolak, minimal {MIN_REASON} huruf)
                        </Label>
                        <Textarea id="payroll-reason" rows={2} value={reason}
                          data-testid={LABOR.payrollReason} className="bg-background"
                          placeholder="Mis. jumlah hari tidak cocok dengan buku harian 14 Agustus."
                          onChange={(e) => setReason(e.target.value)} />
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" data-testid={LABOR.payrollApproveBtn} disabled={busy}
                          onClick={() => run(() => api.post(
                            `/labor/payrolls/${p.id}/decision`,
                            { approve: true, reason: reason.trim() || null },
                          ), "Rekap upah disetujui.")}>
                          <CheckCircle2 className="mr-1.5 h-4 w-4" /> Setujui
                        </Button>
                        <Button size="sm" variant="destructive"
                          data-testid={LABOR.payrollRejectBtn}
                          disabled={busy || reason.trim().length < MIN_REASON}
                          onClick={() => run(() => api.post(
                            `/labor/payrolls/${p.id}/decision`,
                            { approve: false, reason: reason.trim() },
                          ), "Rekap upah ditolak.")}>
                          <XCircle className="mr-1.5 h-4 w-4" /> Tolak
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm text-amber-900">
                        Sudah disetujui — pembayaran akan melahirkan jurnal dan mengurangi kas
                        bank. Angka tidak bisa diubah lagi setelah dibayar.
                      </p>
                      <Button size="sm" data-testid={LABOR.payrollPayBtn} disabled={busy}
                        onClick={() => run(() => api.post(`/labor/payrolls/${p.id}/pay`, {}),
                          "Upah dibayar & dijurnal.")}>
                        <BanknoteArrowUp className="mr-1.5 h-4 w-4" /> Bayar sekarang
                      </Button>
                    </div>
                  )}
                </div>
              ) : null}

            {canSubmit && p.state === "draft" ? (
              <Button size="sm" data-testid={LABOR.payrollSubmitBtn} disabled={busy}
                onClick={() => run(() => api.post(`/labor/payrolls/${p.id}/submit`, {}),
                  "Rekap diajukan ke keuangan.")}>
                <Send className="mr-1.5 h-4 w-4" /> Ajukan ke keuangan
              </Button>
            ) : null}

            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-xs font-medium uppercase text-muted-foreground">Riwayat</p>
              <ul className="mt-1.5 space-y-1 text-xs">
                {(p.history || []).map((h, i) => (
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
