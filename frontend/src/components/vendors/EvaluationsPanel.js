import React, { useCallback, useEffect, useState } from "react";
import { Award } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import EvaluationCard from "@/components/vendors/EvaluationCard";
import api from "@/services/apiClient";
import { VENDOR as T } from "@/constants/testIds";

/**
 * EvaluationsPanel (Fase 48D) — rapor SEMUA vendor atau subkontraktor.
 *
 * `endpoint` menentukan sumbernya (`/vendors/evaluations` atau `/subcon/evaluations`) sehingga
 * satu komponen dipakai dua layar tanpa dua rumus penilaian.
 */
export default function EvaluationsPanel({ endpoint = "/vendors/evaluations",
  testId = T.evalPanel, emptyTitle = "Belum ada vendor yang bisa dinilai",
  emptyDescription }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get(endpoint);
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rapor.");
    } finally { setLoading(false); }
  }, [endpoint]);

  useEffect(() => { load(); }, [load]);

  const s = data?.summary;
  return (
    <div data-testid={testId} className="space-y-4">
      {s ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Rekanan" value={s.total} tone="primary" />
            <MetricCard label="Bisa dinilai" value={s.graded} tone="emerald" />
            <MetricCard label="Belum ada data" value={s.missing_data} tone="muted" />
            <MetricCard label="Rata-rata skor"
              value={s.avg_score === null || s.avg_score === undefined ? "—" : s.avg_score}
              tone="indigo" />
          </div>
          <p className="rounded-lg border border-dashed bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
            {s.detail}
          </p>
        </>
      ) : null}

      {loading ? <LoadingCards count={3} /> : error ? <ErrorState message={error} onRetry={load} />
        : !data?.data?.length ? (
          <EmptyState icon={Award} title={emptyTitle}
            description={emptyDescription
              || "Rapor lahir dari transaksi nyata (PO, penerimaan, retur, harga). Belum ada "
              + "rekanan yang punya bukti untuk dinilai."} />
        ) : (
          <div className="space-y-3">
            {data.data.map((ev) => (
              <EvaluationCard key={ev.vendor_id || ev.subcontractor_id} evaluation={ev} />
            ))}
          </div>
        )}
    </div>
  );
}
