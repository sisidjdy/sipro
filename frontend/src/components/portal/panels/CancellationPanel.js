import React, { useCallback, useEffect, useState } from "react";
import { Ban, Clock, FileText } from "lucide-react";

import { toast } from "sonner";

import portalApi from "@/services/portalClient";
import { portalDownload, portalBlobError } from "@/utils/portalDownload";
import { formatIDR } from "@/utils/formatters";
import { P56 } from "@/constants/testIds";

/**
 * Portal pembeli — panel PEMBATALAN & REFUND (Fase 56C).
 *
 * Kalau pesanan pembeli dibatalkan, dialah yang paling berhak tahu angkanya: berapa yang
 * sudah ia bayar, berapa yang dipotong DAN atas dasar aturan apa, berapa yang dikembalikan,
 * apa yang sedang ditunggu, serta berapa yang sudah dibayarkan kepadanya. Tanpa layar ini,
 * pembeli hanya tahu "pesanan saya batal" dan harus menelepon untuk menagih haknya.
 *
 * Bahasanya adalah bahasa PEMBELI: tidak ada nomor akun, tidak ada istilah internal.
 */
export default function CancellationPanel() {
  const [rows, setRows] = useState([]);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await portalApi.get("/portal/cancellations");
      setRows(res.data.data || []);
      setReason(res.data.reason || "");
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data pembatalan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const money = (v) => (v === null || v === undefined ? "belum ditetapkan" : formatIDR(v));

  // Dokumen diunduh LEWAT SESI PORTAL (blob), bukan tautan mentah bertoken di URL:
  // tautan bertoken bisa disalin, dibagikan, dan tersimpan di riwayat peramban —
  // aturan yang sama dengan BAST & kwitansi (Fase 51C).
  const openDoc = async (r) => {
    try {
      await portalDownload(`/portal/documents/${r.document_id}/pdf`,
        { fallbackName: r.document_number || "berita-acara-pembatalan", open: true });
    } catch (e) {
      toast.error(await portalBlobError(e, "Berita acara tidak bisa dibuka."));
    }
  };

  if (loading) {
    return <div className="rounded-xl border bg-white p-6 text-sm text-slate-500">Memuat…</div>;
  }
  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        {error}
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div data-testid={P56.portalEmpty}
        className="rounded-xl border bg-white p-8 text-center">
        <Ban className="mx-auto h-8 w-8 text-slate-300" />
        <p className="mt-2 font-medium text-slate-700">Tidak ada pembatalan</p>
        <p className="mt-1 text-sm text-slate-500">
          {reason || "Pesanan Anda berjalan normal — ini kabar baik."}
        </p>
      </div>
    );
  }

  return (
    <div data-testid={P56.portalPanel} className="space-y-4">
      {rows.map((r) => (
        <div key={r.number} data-testid={P56.portalRow} data-state={r.state}
          className="rounded-xl border bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="font-heading text-base font-semibold text-slate-800">
                Pembatalan pesanan unit {r.unit_code}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                Nomor {r.number} · {r.state_label}
                {r.reason ? ` · alasan yang dicatat: ${r.reason}` : ""}
              </p>
            </div>
            {r.document_id ? (
              <button type="button" data-testid={P56.portalDocPrint}
                onClick={() => openDoc(r)}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
                <FileText className="h-4 w-4" /> Berita acara ({r.document_number})
              </button>
            ) : null}
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-3">
              <p className="text-xs text-slate-500">Yang sudah Anda bayarkan</p>
              <p className="font-semibold text-slate-800">{money(r.received_total)}</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <p className="text-xs text-slate-500">Potongan ({r.cut_pct}%)</p>
              <p className="font-semibold text-slate-800">{money(r.cut_amount)}</p>
            </div>
            <div className="rounded-lg bg-emerald-50 p-3">
              <p className="text-xs text-emerald-700">Yang dikembalikan kepada Anda</p>
              <p className="font-semibold text-emerald-800">{money(r.payable_total)}</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <p className="text-xs text-slate-500">Sudah dibayarkan · sisa</p>
              <p className="font-semibold text-slate-800">
                {money(r.refund_paid_total)} · {money(r.refund_outstanding)}
              </p>
            </div>
          </div>

          {r.money_note ? (
            <p className="mt-3 text-xs text-slate-600">{r.money_note}</p>
          ) : null}
          {r.rule_label ? (
            <p className="mt-1 text-xs text-slate-500">{r.rule_label}</p>
          ) : null}

          {r.waiting_note ? (
            <p data-testid={P56.portalWaiting}
              className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              <Clock className="mt-0.5 h-4 w-4 shrink-0" /> {r.waiting_note}
            </p>
          ) : null}

          {(r.payments || []).length ? (
            <div className="mt-3 space-y-1">
              <p className="text-xs font-medium text-slate-600">Riwayat pengembalian dana</p>
              {r.payments.map((p, i) => (
                <p key={i} className="text-xs text-slate-600">
                  • {money(p.amount)} · {p.method_label} ·{" "}
                  {String(p.at || "").slice(0, 10)}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
