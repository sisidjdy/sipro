import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import MetricCard from "@/components/bi/MetricCard";
import MetricChart from "@/components/bi/MetricChart";
import MetricDetailDialog from "@/components/bi/MetricDetailDialog";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { BI } from "@/constants/testIds";

/**
 * DashboardShell — kerangka yang dipakai KELIMA dashboard persona.
 *
 * Dibuat satu supaya lima halaman tidak menemukan sendiri cara memuat data, menampilkan
 * kelengkapan, dan membuka rincian — perbedaan kecil di lima tempat itulah yang biasanya
 * membuat satu dashboard mulai berbohong sementara empat lainnya jujur.
 *
 * `charts` menentukan grafik apa yang digambar dari metrik mana; sisanya otomatis.
 */
export default function DashboardShell({
  endpoint, params = {}, charts = [], extraFilters = null, description = null, testId,
}) {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  // Konfirmasi rebuild dibuat MENETAP, bukan hanya toast yang hilang 4 detik: pemakai yang
  // menekan "Hitung ulang snapshot" perlu tahu KAPAN terakhir dihitung dan BERAPA metrik yang
  // ditulis — tanpa itu tombolnya terasa tidak melakukan apa pun (temuan uji E2E Fase 44).
  const [lastRebuild, setLastRebuild] = useState(null);
  const paramKey = JSON.stringify(params);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get(endpoint, { params: JSON.parse(paramKey) });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat dashboard analitik.");
    } finally { setLoading(false); }
  }, [endpoint, paramKey]);

  useEffect(() => { load(); }, [load]);

  const byCode = useMemo(() => {
    const map = {};
    (data?.metrics || []).forEach((m) => { map[m.code] = m; });
    return map;
  }, [data]);

  const rebuild = async () => {
    setBusy(true);
    try {
      const res = await api.post("/analytics/snapshots/rebuild");
      const out = res.data.data || {};
      setLastRebuild({ metrics: out.metrics, date: out.date,
        at: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) });
      toast.success(`Snapshot dihitung ulang: ${out.metrics} metrik (${out.date}).`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghitung ulang snapshot.");
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={6} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const tally = data?.tally || {};
  const incomplete = data?.incomplete || [];

  return (
    <div data-testid={testId} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          {description ? (
            <p className="text-sm text-muted-foreground">{description}</p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Rentang <strong>{data?.range?.from} → {data?.range?.to}</strong>
            {data?.scoped_to ? ` · hanya data milik ${data.scoped_to}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {extraFilters}
          <Button size="sm" variant="outline" data-testid={BI.refresh} onClick={load}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Segarkan
          </Button>
          {can("analytics", "manage") ? (
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" data-testid={BI.rebuild} onClick={rebuild}
                disabled={busy}>
                {busy ? "Menghitung…" : "Hitung ulang snapshot"}
              </Button>
              {lastRebuild ? (
                <span data-testid={BI.rebuildStatus}
                  className="text-xs text-emerald-700">
                  {lastRebuild.metrics} metrik dihitung ulang untuk {lastRebuild.date}
                  {" "}(pukul {lastRebuild.at})
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {incomplete.length ? (
        <div data-testid={BI.incompleteBanner}
          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <strong>{incomplete.length} dari {(data?.metrics || []).length} metrik</strong> belum
            lengkap datanya ({tally.sebagian || 0} dihitung dari sebagian data,{" "}
            {tally.kosong || 0} belum ada data). Angka yang belum lengkap TIDAK ditulis 0 —
            setiap kartunya menyebutkan apa yang masih kurang.
          </span>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(data?.metrics || []).map((m) => (
          <MetricCard key={m.code} metric={m} onDetail={setDetail} />
        ))}
      </div>

      {charts.length ? (
        // `items-start` penting: tanpa itu satu grafik yang lebih tinggi (bar kategori yang
        // tumbuh mengikuti jumlah baris) meregangkan tetangganya dan membuat isinya melayang
        // di tengah kotak — terlihat seperti kartu yang tumpang tindih.
        <div className="grid items-start gap-4 xl:grid-cols-2">
          {charts.map((c) => (
            <MetricChart key={`${c.code}-${c.kind || "auto"}`} metric={byCode[c.code]}
              kind={c.kind} title={c.title} description={c.description} />
          ))}
        </div>
      ) : null}

      <MetricDetailDialog metric={detail} open={!!detail} range={data?.range}
        onOpenChange={(v) => !v && setDetail(null)} />
    </div>
  );
}
