import React, { useCallback, useEffect, useState } from "react";
import { TimerOff } from "lucide-react";

import RefLabel from "@/components/patterns/RefLabel";
import api from "@/services/apiClient";
import { BUILD } from "@/constants/testIds";

/**
 * Laporan keterlambatan: penyebab tersering (kode SSOT, bukan teks bebas) +
 * pekerjaan paling parah telatnya. Dipakai untuk memutuskan tindakan, bukan pajangan.
 */
export default function BuildDelayReport({ projectId, refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const r = await api.get("/build/delays", { params: { project_id: projectId || undefined } });
      setData(r.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat laporan keterlambatan.");
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (error) {
    return (
      <div data-testid={BUILD.delayCard}
        className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
        {error}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div data-testid={BUILD.delayCard} className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <TimerOff className="h-4 w-4 text-rose-600" /> Laporan keterlambatan
        </h3>
        <span className="text-xs text-muted-foreground">
          {data.late_total} pekerjaan lewat tenggat ·{" "}
          <b className={data.unreported_cause ? "text-rose-700" : ""}>
            {data.unreported_cause} belum dijelaskan penyebabnya
          </b>
        </span>
      </div>

      {!data.late_total ? (
        <p className="mt-3 rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
          Tidak ada pekerjaan yang lewat tenggat. Pertahankan.
        </p>
      ) : (
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Penyebab tersering
            </p>
            <div className="space-y-1.5">
              {(data.by_cause || []).map((c) => {
                const pct = Math.round((c.count / Math.max(1, data.late_total)) * 100);
                return (
                  <div key={c.cause} data-cause={c.cause} className="text-xs">
                    <div className="flex items-center justify-between">
                      <span>
                        {c.cause === "unreported" ? "Belum dijelaskan"
                          : <RefLabel group="build_delay_cause" value={c.cause} />}
                      </span>
                      <span className="tabular-nums text-muted-foreground">{c.count}</span>
                    </div>
                    <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                      <div className={`h-full rounded-full ${c.cause === "unreported"
                        ? "bg-slate-400" : "bg-rose-500"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Paling parah (hari telat)
            </p>
            <div className="space-y-1">
              {(data.worst || []).map((w, i) => (
                <div key={i} data-worst={w.unit_code}
                  className="flex items-start justify-between gap-2 rounded-lg border bg-background px-2 py-1.5 text-xs">
                  <span className="min-w-0">
                    <b className="font-mono">{w.unit_code}</b> {w.name}
                    {w.assigned_to ? (
                      <span className="block text-[11px] text-muted-foreground">
                        {w.assigned_to}
                      </span>
                    ) : null}
                  </span>
                  <span className="shrink-0 rounded-full bg-rose-100 px-2 py-0.5 font-semibold tabular-nums text-rose-700">
                    {w.days} hari
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
