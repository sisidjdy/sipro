import React, { useCallback, useEffect, useState } from "react";
import { MousePointerClick } from "lucide-react";

import MetricCard from "@/components/patterns/MetricCard";
import { LoadingKpis, ErrorState } from "@/components/patterns/StateViews";
import AgingBuckets from "@/components/finance/AgingBuckets";
import AgingChart from "@/components/finance/AgingChart";
import KpiDrilldownDialog from "@/components/finance/KpiDrilldownDialog";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FINANCE, P91 } from "@/constants/testIds";

/** Kartu KPI yang bisa diklik → popup rincian (Fase 91). */
function KpiButton({ id, onOpen, ...card }) {
  return (
    <button type="button" data-testid={`${P91.kpiCard}-${id}`} onClick={() => onOpen({ key: id, label: card.label })}
      className="group rounded-xl text-left outline-none transition-transform focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99]">
      <MetricCard {...card} className="h-full border-transparent ring-1 ring-border group-hover:ring-primary/50" />
    </button>
  );
}

export default function FinanceDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [target, setTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/finance/summary");
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat ringkasan keuangan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingKpis count={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const c = data.counts || {};
  const open = (t) => setTarget(t);
  return (
    <div data-testid={FINANCE.dashboard} className="space-y-6">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <MousePointerClick className="h-3.5 w-3.5" /> Klik kartu atau bucket aging untuk melihat baris penyusunnya dan lompat ke tabel yang sudah terfilter.
      </p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <KpiButton id="ar_outstanding" onOpen={open} label="Piutang (AR) Outstanding" value={data.ar_outstanding} tone="primary"
          format="idr" hint={`Belum tertagih ${data.ar_outstanding_pct ?? 0}% dari total tagihan \u00b7 ${c.ar_invoices || 0} invoice`} />
        <KpiButton id="ar_overdue" onOpen={open} label="AR Jatuh Tempo" value={data.ar_overdue} tone="rose"
          format="idr" hint="Melewati tanggal termin" />
        <KpiButton id="ap_outstanding" onOpen={open} label="Utang (AP) Outstanding" value={data.ap_outstanding} tone="amber"
          format="idr" hint={`${c.ap_pending || 0} menunggu approval`} />
        <KpiButton id="contract_liability" onOpen={open} label="Kewajiban Kontrak" value={data.contract_liability} tone="indigo"
          format="idr" hint="Diterima sebelum BAST (PSAK 72)" />
        <KpiButton id="customer_deposits" onOpen={open} label="Titipan Pelanggan" value={data.customer_deposits || 0} tone="indigo"
          format="idr" hint="Kelebihan bayar / setoran di muka (2-1450)" />
        <KpiButton id="revenue_recognized" onOpen={open} label="Pendapatan Diakui" value={data.revenue_recognized} tone="emerald"
          format="idr" hint="Point-in-time saat BAST" />
      </div>

      <AgingChart ar={data.ar_buckets} ap={data.ap_buckets} onSelect={open} />

      <div className="space-y-3">
        <h3 className="font-heading text-sm font-semibold">Aging Piutang (AR)</h3>
        <AgingBuckets buckets={data.ar_buckets}
          onSelect={(bk, label) => open({ key: "ar_bucket", bucket: bk, label: `Aging piutang · ${label}` })} />
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-heading text-sm font-semibold">Aging Utang (AP)</h3>
          <p className="text-xs text-muted-foreground">
            Retensi ditahan: <span className="font-medium tabular-nums text-foreground">{formatIDR(data.ap_retention_held)}</span>
          </p>
        </div>
        <AgingBuckets buckets={data.ap_buckets}
          onSelect={(bk, label) => open({ key: "ap_bucket", bucket: bk, label: `Aging utang · ${label}` })} />
      </div>

      <p className="text-[11px] italic text-muted-foreground">{data.worksheet_note}</p>
      <KpiDrilldownDialog target={target} onOpenChange={(o) => { if (!o) setTarget(null); }} />
    </div>
  );
}
