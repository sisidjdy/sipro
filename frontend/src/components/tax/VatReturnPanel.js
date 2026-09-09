import React, { useCallback, useEffect, useState } from "react";
import { Landmark, Info, CheckCircle2, AlertTriangle } from "lucide-react";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import TaxPeriodBar from "@/components/tax/TaxPeriodBar";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const thisMonth = () => new Date().toISOString().slice(0, 7);
const TONE = {
  kurang_bayar: "unpaid", lebih_bayar: "sky", nihil: "completed", missing_data: "snoozed",
};

/**
 * Rekap SPT Masa PPN (Fase 49G) — angka yang bisa DIREKONSTRUKSI pembacanya.
 *
 * Dua kejujuran: masa tanpa faktur & tanpa tagihan masukan dinyatakan “belum ada data”, bukan
 * “nihil”; dan cara menghitung ditulis di layar (faktur batal/diganti tetap terbaca jumlahnya
 * tetapi tidak dihitung sebagai PPN keluaran).
 */
export default function VatReturnPanel() {
  const [period, setPeriod] = useState(thisMonth());
  const [periods, setPeriods] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (p) => {
    setLoading(true); setError("");
    try {
      const [res, per] = await Promise.all([
        api.get("/tax/compliance/vat-return", { params: { period: p } }),
        api.get("/tax/compliance/periods"),
      ]);
      setData(res.data.data || null);
      setPeriods(per.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rekap SPT Masa PPN.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(period); }, [load, period]);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={() => load(period)} />;

  const empty = (data?.missing || []).length > 0;
  const net = data?.net || 0;

  return (
    <div data-testid={P49.vatPanel} className="space-y-4">
      <TaxPeriodBar period={period} onChange={setPeriod} periods={periods}
        inputId="p49-vat-month" inputTestId={P49.vatPeriod} quickTestId={P49.vatPeriodQuick}
        onRefresh={() => load(period)} />

      <div data-testid={P49.vatState} data-state={data?.state}
        className={`flex flex-wrap items-start gap-2 rounded-xl border p-3.5 text-sm ${empty
          ? "border-sky-200 bg-sky-50 text-sky-900"
          : net > 0 ? "border-amber-200 bg-amber-50 text-amber-900"
            : "border-emerald-200 bg-emerald-50 text-emerald-900"}`}>
        {empty ? <Info className="mt-0.5 h-4 w-4 shrink-0" />
          : net > 0 ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />}
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={data?.state} group="vat_return_state" label={data?.state_label}
              tone={TONE[data?.state] || "snoozed"} />
            <p className="section-title">Masa {data?.period}</p>
          </div>
          <p>{data?.detail}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="PPN keluaran (faktur terbit)" value={data?.ppn_keluaran} format="idr"
          tone="emerald" hint={`${data?.faktur_count || 0} faktur aktif · DPP ${formatIDR(data?.dpp_keluaran)}`} />
        <MetricCard label="PPN masukan (estimasi tagihan)" value={data?.ppn_masukan} format="idr"
          tone="sky" hint={`${data?.masukan_count || 0} tagihan · tarif ${data?.ppn_rate || 0}%`} />
        <MetricCard label="Net (keluaran − masukan)" value={data?.net} format="idr"
          tone={net > 0 ? "rose" : "emerald"} hint={data?.state_label} />
        <MetricCard label="Setoran PPN" value={data?.belum_disetor} format="idr" tone="amber"
          hint={`Sudah disetor ${formatIDR(data?.sudah_disetor)}`} />
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard label="Faktur dibatalkan pada masa ini" value={`${data?.faktur_cancelled || 0} faktur`}
          tone="rose" hint="Terbaca jumlahnya, tidak dihitung sebagai PPN keluaran" />
        <MetricCard label="Faktur diganti pada masa ini" value={`${data?.faktur_replaced || 0} faktur`}
          tone="amber" hint="Digantikan faktur pengganti bernomor baru" />
        <MetricCard label="DPP masukan" value={data?.dpp_masukan} format="idr" tone="slate"
          hint="Estimasi inklusif dari tagihan vendor" />
      </div>

      <div data-testid={P49.vatReconstruct} className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <p className="flex items-center gap-1.5 font-heading text-sm font-semibold">
          <Landmark className="h-4 w-4 text-primary" /> Cara angka ini dihitung (bisa diaudit)
        </p>
        <p className="text-xs text-muted-foreground">{data?.reconstruct}</p>
        <p className="text-[11px] text-muted-foreground">{data?.note}</p>
      </div>
    </div>
  );
}
