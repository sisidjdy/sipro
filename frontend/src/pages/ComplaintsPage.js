import React, { useCallback, useEffect, useState } from "react";
import { Headset } from "lucide-react";

import KpiCard from "@/components/patterns/KpiCard";
import ComplaintsListTab from "@/components/complaints/ComplaintsListTab";
import { LoadingKpis, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { COMPLAINTS } from "@/constants/testIds";

/**
 * ComplaintsPage (`/complaints`) — Komplain & Layanan Pelanggan.
 *
 * Fase 40d: kartu angka di atas BUKAN hiasan lagi — masing-masing menaut ke daftar yang
 * sudah terfilter persis seperti cara angkanya dihitung (blueprint §7.3: “KPI tanpa
 * drill-down dianggap belum selesai”). Daftarnya sendiri kini tabel pro.
 */
export default function ComplaintsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadStats = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/complaints/stats");
      setStats(res.data.data);
    } catch (e) {
      // Ringkasan gagal dimuat TIDAK boleh disembunyikan: pemakai harus tahu angka di atas
      // tidak bisa dipercaya saat ini (daftar di bawah tetap punya penanganan galatnya
      // sendiri, jadi layar tidak perlu kosong seluruhnya).
      setError(e?.response?.data?.detail || "Gagal memuat ringkasan komplain.");
      setStats(null);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  const KPIS = [
    { label: "Total komplain", value: stats?.total, tone: "primary", to: "/complaints" },
    { label: "Terbuka", value: stats?.open, tone: "amber", to: "/complaints?status=open" },
    { label: "Dikerjakan", value: stats?.in_progress, tone: "sky",
      to: "/complaints?status=in_progress" },
    { label: "Selesai", value: stats?.resolved, tone: "emerald",
      to: "/complaints?status=resolved" },
    { label: "Lewat SLA", value: stats?.breached, tone: "rose", to: "/complaints?sla=breached",
      hint: stats?.avg_resolution_hours
        ? `Rata-rata tuntas ${stats.avg_resolution_hours} jam` : undefined },
  ];

  return (
    <div data-testid={COMPLAINTS.page} className="space-y-4">
      <div className="flex items-center gap-2">
        <Headset className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">
            Komplain &amp; Layanan Pelanggan
          </h1>
          <p className="page-desc">
            Klik angka untuk membuka daftar yang sudah terfilter.
          </p>
        </div>
      </div>

      {loading && !stats ? <LoadingKpis /> : null}
      {error ? <ErrorState message={error} onRetry={loadStats} /> : null}
      {stats ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {KPIS.map((k) => (
            <KpiCard key={k.label} label={k.label} value={k.value ?? 0} tone={k.tone}
              hint={k.hint} to={k.to} testId={COMPLAINTS.metric} drillLabel="Lihat daftar" />
          ))}
        </div>
      ) : null}

      <ComplaintsListTab onChanged={loadStats} />
    </div>
  );
}
