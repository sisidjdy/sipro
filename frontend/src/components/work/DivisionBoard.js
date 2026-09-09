import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Users2, AlertTriangle, Hourglass, UserPlus, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import TaskCard from "@/components/patterns/TaskCard";
import AssignTaskDialog from "@/components/work/AssignTaskDialog";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";
import { cn } from "@/lib/utils";

function Metric({ label, value, tone, icon: Icon }) {
  return (
    <MetricCard testId={WORK.boardMetric} icon={Icon} label={label} value={value}
      tone={tone || "text-foreground"} />
  );
}

/**
 * DivisionBoard — papan kerja SUPERVISOR: siapa mengerjakan apa, siapa kelebihan beban,
 * apa yang menunggu verifikasi, dan tugas mana yang belum bertuan.
 *
 * Ini yang dulu tidak ada sama sekali: supervisor tidak punya cara melihat/mengatur
 * pekerjaan timnya, sehingga Work Hub hanya terasa seperti daftar pribadi.
 */
export default function DivisionBoard({ division, onOpenTask }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [assign, setAssign] = useState(null);

  const load = useCallback(async () => {
    if (!division) return;
    setLoading(true); setError("");
    try {
      const res = await api.get("/work/board", { params: { division } });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat papan divisi.");
    } finally { setLoading(false); }
  }, [division]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;
  const t = data.totals || {};

  return (
    <div data-testid={WORK.board} className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Tugas aktif" value={t.open || 0} icon={Users2} />
        <Metric label="Terlambat" value={t.overdue || 0} tone="text-rose-600" icon={AlertTriangle} />
        <Metric label="Menunggu verifikasi" value={t.review || 0} tone="text-sky-600" icon={Hourglass} />
        <Metric label="Belum bertuan" value={t.unassigned || 0} tone="text-amber-600" icon={UserPlus} />
        <Metric label="Staf divisi" value={t.staff || 0} icon={Users2} />
      </div>

      <div className="rounded-xl border bg-card shadow-sm">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
          <h3 className="text-sm font-semibold">Beban kerja per anggota</h3>
          <Button size="sm" variant="outline" onClick={load} aria-label="Muat ulang papan">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-secondary/60 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Anggota</th>
                <th className="px-3 py-2 text-left font-medium">Level</th>
                <th className="px-3 py-2 text-right font-medium">Aktif</th>
                <th className="px-3 py-2 text-right font-medium">Terlambat</th>
                <th className="px-3 py-2 text-right font-medium">Menunggu verifikasi</th>
                <th className="px-3 py-2 text-right font-medium">SLA lewat</th>
              </tr>
            </thead>
            <tbody>
              {(data.members || []).map((m) => (
                <tr key={m.email} data-testid={WORK.boardMemberRow} className="border-t">
                  <td className="px-3 py-2">
                    <p className="font-medium">{m.name}</p>
                    <p className="text-[11px] text-muted-foreground">{m.email}</p>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {m.level === "supervisor" ? "Supervisor" : "Staf"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{m.open}</td>
                  <td className={cn("px-3 py-2 text-right tabular-nums",
                    m.overdue ? "font-semibold text-rose-600" : "")}>{m.overdue}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{m.submitted}</td>
                  <td className={cn("px-3 py-2 text-right tabular-nums",
                    m.sla_breached ? "text-rose-600" : "")}>{m.sla_breached}</td>
                </tr>
              ))}
              {!(data.members || []).length ? (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-sm text-muted-foreground">
                  Belum ada anggota pada divisi ini.
                </td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border bg-card p-3 shadow-sm">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
            <Hourglass className="h-4 w-4 text-sky-600" /> Menunggu verifikasi Anda
            <span className="rounded-full bg-secondary px-2 text-xs tabular-nums">
              {(data.review_queue || []).length}
            </span>
          </h3>
          {(data.review_queue || []).length ? (
            <div className="space-y-2.5">
              {data.review_queue.map((task) => (
                <div key={task.id} data-testid={WORK.boardReviewRow}>
                  <TaskCard task={task} onOpen={onOpenTask} compact />
                  <Button size="sm" className="mt-1.5 w-full" variant="outline"
                    onClick={() => onOpenTask && onOpenTask(task)}>Periksa & verifikasi</Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed bg-card p-3 text-sm text-muted-foreground">
              Tidak ada pekerjaan yang menunggu verifikasi.
            </p>
          )}
        </div>

        <div className="rounded-xl border bg-card p-3 shadow-sm">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
            <UserPlus className="h-4 w-4 text-amber-600" /> Belum ada penerima
            <span className="rounded-full bg-secondary px-2 text-xs tabular-nums">
              {(data.unassigned || []).length}
            </span>
          </h3>
          {(data.unassigned || []).length ? (
            <div className="space-y-2.5">
              {data.unassigned.map((task) => (
                <div key={task.id} data-testid={WORK.boardUnassignedRow}>
                  <TaskCard task={task} onOpen={onOpenTask} compact />
                  <Button size="sm" className="mt-1.5 w-full"
                    onClick={() => setAssign(task)}>Tugaskan ke staf</Button>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="Semua tugas sudah bertuan"
              description="Tugas otomatis langsung diberikan sesuai aturan penerima pada jobdesk." />
          )}
        </div>
      </div>

      <AssignTaskDialog open={!!assign} onOpenChange={(v) => !v && setAssign(null)}
        taskId={assign?.id} division={division} onDone={load} />
    </div>
  );
}
