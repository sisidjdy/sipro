import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { CalendarRange, Download, FileBarChart2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import api from "@/services/apiClient";
import { deviationTone, shortDate } from "@/utils/buildUi";
import { legendLabel } from "@/utils/chartUi";
import { BUILD } from "@/constants/testIds";

const TONE_LABEL = { on_track: "Sesuai jadwal", behind: "Tertinggal", critical: "Kritis" };
const TONE_PILL = { on_track: "completed", behind: "pending", critical: "overdue" };

/**
 * LAPORAN MINGGUAN PEMBANGUNAN — dikirim otomatis tiap Senin ke Direksi & Manajer Proyek.
 *
 * Isinya sengaja "apa adanya": progres tiap rumah dibanding rencana, deviasi dalam HARI,
 * pekerjaan telat, gerbang yang diterobos, dan penyebab telat dominan. Semua dihitung dari
 * pekerjaan yang sudah diverifikasi beserta buktinya — tidak ada angka yang diketik manual.
 * PDF disediakan untuk rapat/investor.
 */
export default function WeeklyReportPanel({ projectId, focusReportId }) {
  const [rows, setRows] = useState([]);
  const [canRun, setCanRun] = useState(false);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.get("/build/reports/weekly",
        { params: { project_id: projectId || undefined, limit: 12 } });
      const data = r.data?.data || [];
      setRows(data);
      setCanRun(!!r.data?.can_run);
      setSel((cur) => focusReportId || cur || (data[0]?.id ?? null));
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat laporan mingguan.");
    } finally { setLoading(false); }
  }, [projectId, focusReportId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!sel) { setDetail(null); return; }
    api.get(`/build/reports/weekly/${sel}`)
      .then((r) => setDetail(r.data?.data || null))
      .catch(() => setDetail(null));
  }, [sel]);

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post("/build/reports/weekly/run",
        { project_id: projectId || null });
      toast.success(r.data?.message || "Laporan mingguan dibuat.");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat laporan mingguan.");
    } finally { setBusy(false); }
  };

  const download = async () => {
    if (!sel) return;
    try {
      const r = await api.get(`/build/reports/weekly/${sel}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `laporan-mingguan-${detail?.week_key || sel}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("PDF laporan diunduh.");
    } catch {
      toast.error("Gagal mengunduh PDF laporan.");
    }
  };

  if (loading && !rows.length) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const t = detail?.totals || {};
  return (
    <div data-testid={BUILD.reportPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <div>
          <p className="text-sm font-semibold">Laporan mingguan pembangunan</p>
          <p className="text-[11px] text-muted-foreground">
            Dibuat otomatis setiap Senin pagi lalu dikirim ke Direksi & Manajer Proyek
            sebagai notifikasi + tugas baca.
          </p>
        </div>
        {canRun ? (
          <Button size="sm" data-testid={BUILD.reportRun} onClick={run} disabled={busy}>
            <Play className="mr-1 h-3.5 w-3.5" />
            {busy ? "Menyusun…" : "Buat laporan pekan ini"}
          </Button>
        ) : null}
      </div>

      {!rows.length ? (
        <div data-testid={BUILD.reportEmpty}>
          <EmptyState icon={FileBarChart2} title="Belum ada laporan mingguan"
            description={canRun
              ? "Buat laporan pekan ini, atau tunggu penjadwal Senin membuatnya otomatis."
              : "Laporan pekan ini akan muncul begitu Manajer Proyek atau penjadwal Senin menyusunnya."}
            actionLabel={canRun ? "Buat laporan pekan ini" : null} onAction={run} />
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {rows.map((r) => (
            <button key={r.id} type="button" data-testid={BUILD.reportRow}
              onClick={() => setSel(r.id)}
              className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${sel === r.id
                ? "border-primary bg-primary/10" : "bg-card hover:bg-secondary"}`}>
              <p className="font-semibold">{r.week_key}</p>
              <p className="text-[11px] text-muted-foreground">
                {r.project_name} · {r.totals?.units_scheduled || 0} rumah ·{" "}
                <span className={deviationTone(r.totals?.deviation || 0)}>
                  {(r.totals?.deviation || 0) >= 0 ? "+" : ""}{r.totals?.deviation || 0}%
                </span>
              </p>
            </button>
          ))}
        </div>
      )}

      {detail ? (
        <div data-testid={BUILD.reportDetail} className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            <div>
              <p className="section-title">
                {detail.project_name} — pekan {detail.week_key}
              </p>
              <p className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <CalendarRange className="h-3 w-3" />
                {shortDate(detail.period_start)} – {shortDate(detail.period_end)} · disusun{" "}
                {String(detail.generated_at || "").slice(0, 10)}
              </p>
            </div>
            <Button size="sm" variant="outline" data-testid={BUILD.reportPdf} onClick={download}>
              <Download className="mr-1 h-3.5 w-3.5" /> Unduh PDF
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <Metric label="Rumah terjadwal" value={t.units_scheduled} />
            <Metric label="Progres rata-rata" value={`${t.avg_progress}%`}
              hint={`rencana ${t.avg_planned}%`}
              tone={deviationTone(t.deviation || 0)} />
            <Metric label="Sesuai jadwal" value={t.on_track} tone="text-emerald-700" />
            <Metric label="Tertinggal / kritis" value={`${t.behind}/${t.critical}`}
              tone="text-rose-700" />
            <Metric label="Pekerjaan telat" value={t.late_items} tone="text-rose-700" />
            <Metric label="Diverifikasi pekan ini" value={t.verified_this_week}
              hint={t.overrides ? `${t.overrides} gerbang diterobos` : "tanpa override"} />
          </div>

          {(detail.curve || []).length ? (
            <div data-testid={BUILD.reportCurve} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <h4 className="mb-1 text-sm font-semibold">Rencana vs realisasi (kumulatif)</h4>
              <ResponsiveContainer width="100%" height={210}>
                <AreaChart data={detail.curve} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                  <Tooltip formatter={(v) => `${v}%`} />
                  <Legend wrapperStyle={{ fontSize: 11 }} formatter={legendLabel} />
                  <Area type="monotone" dataKey="planned" name="Rencana" stroke="#f59e0b"
                    fill="#fef3c7" strokeWidth={2} />
                  <Area type="monotone" dataKey="actual" name="Terverifikasi" stroke="#0d9488"
                    fill="#ccfbf1" strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : null}

          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-xs">
              <thead className="bg-secondary text-left">
                <tr>
                  {["Rumah", "Pembeli", "Progres", "Rencana", "Deviasi", "Item", "Telat",
                    "Tertahan", "Target selesai", "Status"].map((h) => (
                      <th key={h} className="px-2.5 py-2 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(detail.houses || []).map((h) => (
                  <tr key={h.unit_id} data-testid={BUILD.reportHouseRow} className="border-t">
                    <td className="px-2.5 py-2 font-mono font-semibold">{h.unit_code}</td>
                    <td className="px-2.5 py-2">{h.buyer || <span className="text-muted-foreground">belum ada</span>}</td>
                    <td className="px-2.5 py-2 font-semibold tabular-nums">{h.progress}%</td>
                    <td className="px-2.5 py-2 tabular-nums text-muted-foreground">{h.planned_progress}%</td>
                    <td className={`px-2.5 py-2 tabular-nums font-semibold ${deviationTone(h.deviation)}`}>
                      {h.deviation >= 0 ? "+" : ""}{h.deviation}%
                      {h.deviation_days ? ` (${h.deviation_days} hari)` : ""}
                    </td>
                    <td className="px-2.5 py-2 tabular-nums">{h.items_done}/{h.items_total}</td>
                    <td className="px-2.5 py-2 tabular-nums text-rose-700">{h.late_items}</td>
                    <td className="px-2.5 py-2 tabular-nums text-amber-700">{h.blocked_items}</td>
                    <td className="px-2.5 py-2">{shortDate(h.target_finish_date)}</td>
                    <td className="px-2.5 py-2">
                      <StatusPill status={h.tone} label={TONE_LABEL[h.tone] || h.tone}
                        tone={TONE_PILL[h.tone] || "draft"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(detail.delays_top || []).length ? (
            <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <h4 className="mb-1.5 text-sm font-semibold">Pekerjaan paling sering telat pekan ini</h4>
              <div className="space-y-1.5">
                {detail.delays_top.map((d) => (
                  <p key={d.step_code} data-testid={BUILD.reportDelayRow}
                    className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
                    <b>{d.step_code} {d.name}</b> — {d.units} rumah, rata-rata {d.avg_days} hari
                    (maksimal {d.max_days} hari): {(d.unit_codes || []).join(", ")}
                  </p>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value, hint, tone = "" }) {
  return (
    <MetricCard label={label} value={value} hint={hint} tone={tone || "text-foreground"}
      dot={false} testId={undefined} />
  );
}
