import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ExternalLink, Info, Receipt } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import MoneyText from "@/components/patterns/MoneyText";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { formatDateWIB } from "@/utils/formatters";
import { CRMC } from "@/constants/testIds";

/**
 * Tab “Rencana Bayar” pada profil pelanggan.
 *
 * Tab ini sempat MATI (“dijadwalkan Fase 43”) padahal jadwal tagihan per termin, penerimaan
 * berbukti, dan sisa kewajiban SUDAH lama menjadi data nyata (`ar_invoices` + `receipts`).
 * Akibatnya pelanggan/CS harus pindah ke menu Keuangan hanya untuk menjawab “sudah bayar
 * berapa, sisanya kapan jatuh tempo” — padahal pertanyaan itu milik halaman pelanggan.
 *
 * Yang JUJUR di layar ini:
 *  * Termin yang lewat jatuh tempo dan masih bersisa ditandai TERLAMBAT (dihitung dari
 *    tanggal jatuh tempo & sisa, bukan dari status yang diketik orang).
 *  * Yang belum dibangun disebut apa adanya: toleransi keterlambatan dan mesin
 *    pembatalan/refund berjurnal sudah ada sejak Fase 56 (lihat tab Kontrak & Legal).
 */
function planState(item) {
  // Data nyata memakai `paid_amount` (bukan `paid`) — dan `status` per termin diperbarui
  // finance_engine saat penerimaan dicatat. Keadaan TERLAMBAT dihitung dari tanggal jatuh
  // tempo + sisa, bukan dari status yang diketik orang.
  const paid = Number(item.paid_amount ?? item.paid ?? 0);
  const outstanding = Number(item.amount || 0) - paid;
  if (outstanding <= 0) return { key: "lunas", label: "Lunas", tone: "border-emerald-200 bg-emerald-50 text-emerald-800" };
  const due = item.due_date ? new Date(`${String(item.due_date).slice(0, 10)}T23:59:59`) : null;
  if (due && due.getTime() < Date.now()) {
    return { key: "terlambat", label: "Terlambat", tone: "border-rose-200 bg-rose-50 text-rose-800" };
  }
  if (paid > 0) {
    return { key: "sebagian", label: "Dibayar sebagian", tone: "border-amber-200 bg-amber-50 text-amber-900" };
  }
  return { key: "menunggu", label: "Menunggu", tone: "border-slate-200 bg-slate-100 text-slate-700" };
}

const paidOf = (item) => Number(item.paid_amount ?? item.paid ?? 0);

function DealPlan({ deal, plan }) {
  const inv = plan?.data;
  if (!inv) {
    return (
      <div data-testid={CRMC.planEmpty} className="rounded-xl border bg-card p-4">
        <p className="font-medium">{deal.unit_code || "Unit"} · belum ada jadwal tagihan</p>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Transaksi ini belum punya jadwal tagihan (AR). Jadwalnya dibuat Keuangan dari skema
          pembayaran — belum ada data, bukan Rp 0.
        </p>
      </div>
    );
  }
  const items = inv.items || [];
  const receipts = plan.receipts || [];
  const total = Number(inv.total || 0);
  const paid = Number(inv.paid || 0);
  const outstanding = Number(inv.outstanding ?? (total - paid));
  const overdue = items.filter((i) => planState(i).key === "terlambat");
  const overdueAmount = overdue.reduce(
    (a, i) => a + (Number(i.amount || 0) - paidOf(i)), 0);

  return (
    <div data-testid={CRMC.planDeal} className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-heading text-base font-semibold">
            {deal.unit_code || inv.unit_code || "Unit"}
          </p>
          <p className="text-[12px] text-muted-foreground">
            {items.length} termin · skema {inv.scheme_name || inv.scheme?.name || "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill group="ar_status" status={inv.status} />
          <Link to="/finance?tab=ar" data-testid={CRMC.planOpenFinance}
            className="inline-flex items-center gap-1 text-[12px] font-medium text-primary hover:underline">
            Buka di Keuangan <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      </div>

      <div data-testid={CRMC.planSummary} className="grid gap-2 sm:grid-cols-4">
        {[["Nilai kontrak", total], ["Sudah dibayar", paid], ["Sisa kewajiban", outstanding],
          ["Tunggakan", overdueAmount]].map(([label, val]) => (
          <div key={label} className="rounded-lg border bg-secondary/40 px-2.5 py-1.5">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="font-semibold tabular-nums"><MoneyText value={val} /></p>
          </div>
        ))}
      </div>

      {overdue.length ? (
        <p data-testid={CRMC.planOverdue}
          className="flex items-start gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-2 text-[13px] text-rose-900">
          <AlertTriangle className="mt-0.5 h-4 w-4" />
          <span>
            {overdue.length} termin sudah lewat jatuh tempo dan masih bersisa
            (<MoneyText value={overdueAmount} />). Penagihan dijalankan dari menu Keuangan.
          </span>
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full text-[13px]">
          <thead className="bg-secondary/60 text-left text-[12px] text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Termin</th>
              <th className="px-3 py-2">Jatuh tempo</th>
              <th className="px-3 py-2 text-right">Nominal</th>
              <th className="px-3 py-2 text-right">Dibayar</th>
              <th className="px-3 py-2 text-right">Sisa</th>
              <th className="px-3 py-2">Keadaan</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => {
              const st = planState(it);
              const sisa = Number(it.amount || 0) - paidOf(it);
              return (
                <tr key={`${it.label || "termin"}-${i}`} data-testid={CRMC.planRow}
                  data-state={st.key} className="border-t">
                  <td className="px-3 py-2 font-medium">{it.label || `Termin ${i + 1}`}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {it.due_date ? formatDateWIB(it.due_date) : "belum dijadwalkan"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <MoneyText value={it.amount} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <MoneyText value={paidOf(it)} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <MoneyText value={sisa} />
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${st.tone}`}>
                      {st.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-1.5">
        <p className="text-[13px] font-medium">Penerimaan yang sudah tercatat</p>
        {!receipts.length ? (
          <p className="text-[12px] text-muted-foreground">
            Belum ada penerimaan pembayaran untuk transaksi ini.
          </p>
        ) : (
          <ul className="space-y-1">
            {receipts.slice(0, 8).map((r) => (
              <li key={r.id} data-testid={CRMC.planReceiptRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[12px]">
                <span>
                  {r.no || r.receipt_no || "Kuitansi"} · {formatDateWIB(r.created_at || r.date)}
                  {r.method ? ` · ${r.method}` : ""}
                </span>
                <span className="font-semibold tabular-nums">
                  <MoneyText value={r.amount} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function CustomerPaymentPlanTab({ customer }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const leadId = customer?.lead_id;

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const d = leadId
        ? await api.get("/deals", { params: { lead_id: leadId, limit: 50 } })
        : { data: { data: [] } };
      const deals = d.data.data || [];
      const plans = await Promise.all(deals.map((deal) =>
        api.get(`/finance/ar/${deal.id}`).then((r) => ({ deal, plan: r.data }))
          .catch(() => ({ deal, plan: null }))));
      setRows(plans);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rencana bayar pelanggan.");
    } finally { setLoading(false); }
  }, [leadId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const gap = (
    <div data-testid={CRMC.planGap}
      className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[13px] text-amber-900">
      <p className="flex items-center gap-1.5 font-medium">
        <Info className="h-4 w-4" /> Yang sudah ada dan yang belum
      </p>
      <p className="mt-1">
        Jadwal termin, penerimaan berbukti, sisa kewajiban, dan tunggakan di bawah adalah data
        nyata dari Keuangan. Yang <b>belum</b> dibangun: <b>toleransi keterlambatan</b>.
        Pembatalan &amp; pengembalian dana <b>sudah berjurnal</b> (Fase 56): diajukan Manajer
        Sales dari tab <b>Kontrak &amp; Legal</b>, diputus Manajer Keuangan, dan dibayar dari
        kas/bank — daftarnya ada di <b>Keuangan → Pembatalan &amp; Refund</b>.
      </p>
    </div>
  );

  if (!leadId || !rows.length) {
    return (
      <div className="space-y-4">
        {gap}
        <div data-testid={CRMC.planEmpty}>
          <EmptyState icon={Receipt} title="Belum ada transaksi untuk ditagih"
            description={leadId
              ? "Pelanggan ini belum punya transaksi, jadi belum ada rencana bayar."
              : "Pelanggan ini belum terikat ke data lead, jadi transaksinya tidak bisa ditelusuri."} />
        </div>
      </div>
    );
  }

  return (
    <div data-testid={CRMC.planTab} className="space-y-4">
      {gap}
      {rows.map(({ deal, plan }) => (
        <DealPlan key={deal.id} deal={deal} plan={plan} />
      ))}
    </div>
  );
}
