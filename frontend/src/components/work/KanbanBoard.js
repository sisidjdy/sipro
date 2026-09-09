import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import TaskCard from "@/components/patterns/TaskCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";
import { cn } from "@/lib/utils";

const TONE = {
  open: "border-t-slate-300", in_progress: "border-t-sky-400",
  submitted: "border-t-amber-400", done: "border-t-emerald-400",
};

/**
 * KanbanBoard — papan tugas divisi per status, digulir horizontal.
 *
 * Sengaja TANPA geser-tarik (drag & drop): perpindahan status harus melewati aksi resmi
 * (Mulai → Ajukan Hasil + bukti → Verifikasi) supaya bukti kerja tidak bisa dilewati.
 * Klik kartu untuk membuka detail dan mengerjakannya.
 */
export default function KanbanBoard({ division, onOpenTask }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/work/kanban", { params: division ? { division } : {} });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat papan tugas.");
    } finally { setLoading(false); }
  }, [division]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div data-testid={WORK.kanban} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {data.total} tugas pada papan. Perpindahan status lewat aksi resmi (Mulai → Ajukan
          Hasil + bukti → Verifikasi) — bukan geser-tarik, agar bukti kerja tidak terlewat.
        </p>
        <Button size="sm" variant="outline" onClick={load} aria-label="Muat ulang papan">
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {(data.columns || []).map((c) => (
          <div key={c.key} data-testid={WORK.kanbanColumn} data-column={c.key}
            className={cn("w-80 shrink-0 rounded-xl border border-t-4 bg-card p-2.5 shadow-sm",
              TONE[c.key])}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">{c.label}</p>
              <span className="flex items-center gap-1.5">
                {c.overdue ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800">
                    <AlertTriangle className="h-3 w-3" /> {c.overdue}
                  </span>
                ) : null}
                <span className="rounded-full bg-secondary px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
                  {c.count}
                </span>
              </span>
            </div>
            <div className="max-h-[65vh] space-y-2 overflow-y-auto pr-0.5">
              {c.tasks.length ? c.tasks.map((t) => (
                <TaskCard key={t.id} task={t} onOpen={onOpenTask} compact />
              )) : (
                <p className="rounded-lg border border-dashed bg-card p-3 text-center text-[11px] text-muted-foreground">
                  Kosong
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
