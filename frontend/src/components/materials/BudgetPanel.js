import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PieChart, AlertTriangle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import EmptyState from "@/components/patterns/EmptyState";
import api from "@/services/apiClient";
import { MATBUDGET as T } from "@/constants/testIds";

export default function BudgetPanel({ projectId, refreshKey }) {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({ materials: 0, tracked: 0, over_budget: 0 });
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await api.get(`/materials/project/${projectId}/budget`);
      setRows(res.data.data || []);
      setSummary(res.data.summary || {});
    } catch (e) { toast.error("Gagal memuat anggaran material."); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  return (
    <div data-testid={T.panel} className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border bg-card px-3 py-1 text-xs shadow-[var(--shadow-card)]">Material: <b>{summary.materials}</b></span>
        <span className="rounded-full border bg-card px-3 py-1 text-xs shadow-[var(--shadow-card)]">Terpantau RAB: <b>{summary.tracked}</b></span>
        <span className={`rounded-full border px-3 py-1 text-xs ${summary.over_budget ? "border-rose-200 bg-rose-50 text-rose-700" : "bg-card"}`}>
          Melebihi RAB: <b>{summary.over_budget}</b>
        </span>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Memuat...</p>
      ) : !rows.length ? (
        <EmptyState icon={PieChart} title="Belum ada material" description="Tambahkan material & anggaran RAB untuk memantau pemakaian." />
      ) : (
        <div className="space-y-2">
          {rows.map((r) => {
            const tracked = r.budget_qty > 0;
            const pct = tracked ? Math.min(100, r.pct ?? 0) : 0;
            return (
              <div key={r.material_id} data-testid={T.row}
                className={`rounded-xl border bg-card p-3 ${r.over_budget ? "border-rose-300" : ""}`}>
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
                      <span className="font-medium">{r.name}</span>
                      {r.over_budget ? (
                        <span className="flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                          <AlertTriangle className="h-3 w-3" /> Melebihi RAB
                        </span>
                      ) : null}
                    </div>
                    {r.boq_cost_code ? (
                      <div className="text-[11px] text-muted-foreground">RAB {r.boq_cost_code} · {r.boq_description}</div>
                    ) : <div className="text-[11px] text-muted-foreground">Belum ditaut ke item RAB</div>}
                  </div>
                  <div className="text-right text-sm tabular-nums">
                    <div className={r.over_budget ? "font-semibold text-rose-600" : "font-semibold"}>
                      {r.consumed_qty} / {tracked ? r.budget_qty : "—"} {r.uom}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {tracked ? (r.over_budget ? `lebih ${Math.abs(r.remaining_qty)}` : `sisa ${r.remaining_qty}`) : "tanpa anggaran"}
                    </div>
                  </div>
                </div>
                {tracked ? (
                  <Progress value={pct} className={`mt-2 h-2 ${r.over_budget ? "[&>div]:bg-rose-500" : ""}`} />
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
