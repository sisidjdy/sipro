import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BadgePercent, Settings2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { COMM_HOME } from "@/constants/testIds";

const STAT = [
  { key: "earned", label: "Total Earned", tone: "text-primary", testid: COMM_HOME.total, path: "summary.earned" },
  { key: "pending", label: "Menunggu", tone: "text-amber-600", testid: COMM_HOME.pending, path: "summary.pending.amount" },
  { key: "approved", label: "Disetujui", tone: "text-indigo-600", testid: COMM_HOME.approved, path: "summary.approved.amount" },
  { key: "paid", label: "Dibayar", tone: "text-emerald-600", testid: COMM_HOME.paid, path: "summary.paid.amount" },
];
const get = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);

export default function CommissionBreakdown() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/finance/commissions/summary");
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat komisi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid={COMM_HOME.panel} className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BadgePercent className="h-4 w-4 text-primary" />
          <h2 className="font-heading text-lg font-semibold">Komisi Saya</h2>
        </div>
        {can("finance", "update") ? (
          <button type="button" data-testid="commission-config-link"
            onClick={() => navigate("/finance?tab=config")}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            <Settings2 className="h-3.5 w-3.5" /> Atur skema
          </button>
        ) : null}
      </div>

      {loading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <Skeleton className="h-3 w-1/2" /><Skeleton className="mt-2 h-5 w-2/3" />
            </div>
          ))}
        </div>
      ) : error ? <ErrorState message={error} onRetry={load} /> : (
        <>
          <div className="grid grid-cols-2 gap-3">
            {STAT.map((s) => (
              <div key={s.key} data-testid={s.testid} className="rounded-lg border bg-background/50 p-3">
                <p className="text-xs text-muted-foreground">{s.label}</p>
                <p className={cn("mt-1 text-lg font-semibold font-heading tabular-nums", s.tone)}>
                  {formatIDR(get(data, s.path) || 0)}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Rincian per-deal</p>
            {!(data?.deals || []).length ? (
              <p className="text-sm text-muted-foreground">Belum ada komisi. Komisi dihitung otomatis saat unit di-booking / lunas.</p>
            ) : (
              <div className="space-y-2">
                {data.deals.slice(0, 6).map((c) => (
                  <div key={c.id} data-testid={COMM_HOME.row}
                    className="flex items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2 text-sm">
                    <div>
                      <p className="font-medium">Unit {c.unit_code || "-"}</p>
                      <p className="text-xs text-muted-foreground">{c.scheme_name || "-"} · {c.rate_pct}%</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-semibold tabular-nums text-primary">{formatIDR(c.amount)}</span>
                      <StatusPill status={c.status} group="commission_status" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
