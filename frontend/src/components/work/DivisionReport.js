import React, { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Clock, CheckCircle2, AlertTriangle, RotateCcw,
  Paperclip, Camera, Trophy } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateTimeWIB } from "@/utils/formatters";
import { photoSrc } from "@/utils/photoSrc";
import MetricCard from "@/components/patterns/MetricCard";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";
import { cn } from "@/lib/utils";

function Metric({ label, value, tone, icon: Icon, hint }) {
  return (
    <MetricCard testId={WORK.reportMetric} icon={Icon} label={label} value={value}
      hint={hint} tone={tone || "text-foreground"} />
  );
}

/**
 * DivisionReport — rapor MINGGUAN divisi: ketepatan waktu & bukti kerja tiap staf.
 *
 * Semua angka dihitung dari data (tanggal jatuh tempo vs waktu selesai, hasil verifikasi,
 * lampiran bukti) sehingga tidak bisa dikarang. Rapor juga dikirim otomatis sebagai
 * notifikasi ke supervisor tiap pekan oleh penjadwal.
 */
export default function DivisionReport({ division, onOpenTask }) {
  const [week, setWeek] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!division) return;
    setLoading(true); setError("");
    try {
      const res = await api.get("/work/report", {
        params: { division, week: week || undefined },
      });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rapor divisi.");
    } finally { setLoading(false); }
  }, [division, week]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;
  const t = data.totals || {};

  return (
    <div data-testid={WORK.report} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
        <div>
          <p className="text-sm font-semibold">Rapor pekan {data.week}</p>
          <p className="text-[11px] text-muted-foreground">
            {String(data.start).slice(0, 10)} → {String(data.end).slice(0, 10)} · dihitung dari
            tenggat vs waktu selesai &amp; bukti terlampir
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="outline" data-testid={WORK.reportPrev}
            aria-label="Pekan sebelumnya" onClick={() => setWeek(data.prev_week)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="outline" data-testid={WORK.reportNext}
            aria-label="Pekan berikutnya" onClick={() => setWeek(data.next_week)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Ketepatan waktu" icon={Trophy}
          value={t.on_time_rate != null ? `${t.on_time_rate}%` : "—"}
          tone={t.on_time_rate != null && t.on_time_rate < 70 ? "text-rose-600" : "text-emerald-600"}
          hint={`${t.on_time || 0} dari ${t.done || 0} tugas selesai`} />
        <Metric label="Selesai pekan ini" value={t.done || 0} icon={CheckCircle2} />
        <Metric label="Selesai terlambat" value={t.late || 0} tone="text-amber-600" icon={Clock} />
        <Metric label="Terlambat berjalan" value={t.overdue || 0} tone="text-rose-600"
          icon={AlertTriangle} />
        <Metric label="Bukti kerja" value={t.evidence || 0} icon={Paperclip}
          hint={`${t.returned || 0} dikembalikan`} />
      </div>

      <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-secondary/60 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Anggota</th>
              <th className="px-3 py-2 text-right font-medium">Selesai</th>
              <th className="px-3 py-2 text-right font-medium">Tepat waktu</th>
              <th className="px-3 py-2 text-right font-medium">Terlambat</th>
              <th className="px-3 py-2 text-right font-medium">Dikembalikan</th>
              <th className="px-3 py-2 text-right font-medium">Bukti</th>
              <th className="px-3 py-2 text-right font-medium">Ketepatan</th>
            </tr>
          </thead>
          <tbody>
            {(data.members || []).map((m) => (
              <tr key={m.email} data-testid={WORK.reportMemberRow} className="border-t">
                <td className="px-3 py-2">
                  <p className="font-medium">{m.name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {m.level === "supervisor" ? "Supervisor" : "Staf"} · {m.open} aktif
                    {m.overdue ? ` · ${m.overdue} terlambat` : ""}
                  </p>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{m.done}</td>
                <td className="px-3 py-2 text-right tabular-nums text-emerald-700">{m.on_time}</td>
                <td className={cn("px-3 py-2 text-right tabular-nums",
                  m.late ? "text-amber-700" : "")}>{m.late}</td>
                <td className={cn("px-3 py-2 text-right tabular-nums",
                  m.returned ? "text-rose-600" : "")}>{m.returned}</td>
                <td className="px-3 py-2 text-right tabular-nums">{m.evidence}</td>
                <td className="px-3 py-2 text-right">
                  {m.on_time_rate != null ? (
                    <StatusPill status={m.on_time_rate >= 90 ? "paid" : m.on_time_rate >= 70
                      ? "pending" : "overdue"} label={`${m.on_time_rate}%`} />
                  ) : <span className="text-xs text-muted-foreground">—</span>}
                </td>
              </tr>
            ))}
            {!(data.members || []).length ? (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-sm text-muted-foreground">
                Belum ada anggota pada divisi ini.
              </td></tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {/* Bukti kerja nyata per anggota */}
      <div className="grid gap-3 lg:grid-cols-2">
        {(data.members || []).filter((m) => (m.samples || []).length).map((m) => (
          <div key={m.email} className="rounded-xl border bg-card p-3 shadow-sm">
            <p className="mb-2 text-sm font-semibold">Bukti kerja — {m.name}</p>
            <div className="space-y-2">
              {m.samples.map((s) => (
                <button key={s.task_id} type="button" data-testid={WORK.reportEvidence}
                  onClick={() => onOpenTask && onOpenTask({ id: s.task_id })}
                  className="w-full rounded-lg border bg-card p-2.5 text-left transition-colors hover:bg-secondary/60 shadow-[var(--shadow-card)]">
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 text-xs font-medium">{s.title}</p>
                    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold",
                      s.on_time ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800")}>
                      {s.on_time ? "tepat waktu" : "terlambat"}
                    </span>
                  </div>
                  {s.note ? (
                    <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{s.note}</p>
                  ) : (
                    <p className="mt-1 text-[11px] italic text-muted-foreground">
                      Tanpa catatan hasil kerja
                    </p>
                  )}
                  {(s.photos || []).length ? (
                    <div className="mt-1.5 flex gap-1.5">
                      {s.photos.map((f, i) => (
                        <img key={i} src={photoSrc({ file_id: f })} alt="Bukti kerja"
                          className="h-12 w-16 rounded border bg-secondary object-cover" />
                      ))}
                    </div>
                  ) : null}
                  <p className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
                    <Camera className="h-3 w-3" /> {s.jobdesk_code || "manual"} ·
                    {" "}{formatDateTimeWIB(s.completed_at)}
                    {s.verified_by ? ` · diverifikasi ${s.verified_by}` : ""}
                  </p>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {(data.jobdesks || []).length ? (
        <div className="rounded-xl border bg-card p-3 shadow-sm">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
            <RotateCcw className="h-4 w-4 text-muted-foreground" /> Jenis pekerjaan paling rawan
          </p>
          <div className="space-y-1.5">
            {data.jobdesks.map((j) => (
              <div key={j.code} className="flex items-center justify-between gap-2 rounded-lg bg-secondary/50 px-2.5 py-1.5 text-xs">
                <span><span className="font-mono font-semibold text-primary">{j.code}</span> {j.title}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {j.done} selesai · {j.late} terlambat · {j.open} berjalan
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
