import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle, Lightbulb, SlidersHorizontal, TrendingDown, UserCog, Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import RefLabel from "@/components/patterns/RefLabel";
import CalibrationDialog from "@/components/construction/calibration/CalibrationDialog";
import CalibrationHistoryPanel from "@/components/construction/calibration/CalibrationHistoryPanel";
import CalibrationRollbackDialog from "@/components/construction/calibration/CalibrationRollbackDialog";
import MetricCard from "@/components/patterns/MetricCard";
import api from "@/services/apiClient";
import { KIND_DEFAULT, targetFromDelayRow } from "@/utils/calibrationUi";
import { BUILD } from "@/constants/testIds";

/**
 * ANALITIK KETERLAMBATAN — supaya template dikalibrasi dari DATA NYATA, bukan perasaan.
 *
 * Tiga sudut pandang: pekerjaan mana yang paling sering telat, siapa pelaksana yang paling
 * sering telat (beserta penyebab dominan agar adil, bukan menghakimi), dan tipe unit mana
 * yang templatenya paling tidak realistis.
 *
 * Fase 37: rekomendasi tidak lagi berhenti sebagai kalimat "buka Template Jadwal lalu ubah
 * hari mulai/selesai". Setiap rekomendasi (dan setiap baris tabel telat) punya tombol
 * "Kalibrasi" yang membuka dialog pratinjau DI TEMPAT — angka template datang dari backend,
 * jadi tidak ada yang diketik ulang dan template tidak perlu disimpan ulang seluruhnya.
 * Riwayat kalibrasi beserta tombol pembatalannya ikut di sini supaya keputusan perencanaan
 * bisa dibaca ulang di layar yang sama dengan buktinya.
 */
export default function DelayAnalyticsPanel({ projectId, onOpenTemplates }) {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [calib, setCalib] = useState(null);
  const [can, setCan] = useState({ calibrate: false });
  const [dialog, setDialog] = useState(null);
  const [rollback, setRollback] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.get("/build/analytics/delays",
        { params: { project_id: projectId || undefined } });
      setData(r.data?.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat analitik keterlambatan.");
    } finally { setLoading(false); }
  }, [projectId]);

  // Sasaran kalibrasi (template + angka yang berlaku sekarang) & riwayatnya. Dipisah dari
  // analitik supaya kegagalan/penolakan di sini tidak pernah mengosongkan tabel bukti.
  const loadCalib = useCallback(async () => {
    try {
      const r = await api.get("/build/calibration/candidates",
        { params: { project_id: projectId || undefined } });
      setCalib(r.data?.data || null);
      setCan(r.data?.can || { calibrate: false });
    } catch {
      setCalib(null);
      setCan({ calibrate: false });
    }
  }, [projectId]);

  useEffect(() => { load(); loadCalib(); }, [load, loadCalib]);

  /** Cari target kalibrasi untuk satu langkah; jatuh ke layar Kalibrasi bila tidak ketemu. */
  const openCalibration = (stepCode, kind, delta, row) => {
    const rowStep = (calib?.steps || []).find((s) => s.step_code === stepCode);
    const t = (rowStep?.targets || [])[0]
      || (calib?.recommendations || [])
        .flatMap((r) => (r.calibration?.step_code === stepCode ? r.targets || [] : []))[0];
    if (!t) {
      const q = new URLSearchParams();
      if (projectId) q.set("project_id", projectId);
      q.set("step", stepCode);
      if (kind) q.set("kind", kind);
      if (delta) q.set("delta", String(delta));
      nav(`/build-calibration?${q.toString()}`);
      return;
    }
    setDialog({
      target: targetFromDelayRow(row || rowStep || { step_code: stepCode }, t),
      kind: kind || KIND_DEFAULT,
      delta: delta || 0,
    });
  };

  const afterChange = () => { load(); loadCalib(); };

  if (loading && !data) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const s = data.summary || {};
  const steps = data.by_step || [];
  const people = data.by_person || [];
  const types = data.by_unit_type || [];
  const recs = data.recommendations || [];

  if (!steps.length && !s.items_late) {
    return (
      <EmptyState icon={TrendingDown} title="Belum ada keterlambatan tercatat"
        description="Semua pekerjaan masih dalam rencana. Analitik ini akan terisi otomatis begitu ada pekerjaan yang lewat tenggat." />
    );
  }

  return (
    <div data-testid={BUILD.analyticsPanel} className="space-y-4">
      <div data-testid={BUILD.analyticsSummary} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Pekerjaan telat" value={s.items_late}
          hint={`dari ${s.items_total} pekerjaan`} tone="text-rose-700" />
        <Metric label="Selesai tepat waktu" value={`${s.on_time_rate}%`}
          hint={`${s.on_time_done}/${s.items_done} pekerjaan selesai`}
          tone="text-emerald-700" />
        <Metric label="Telat tanpa penjelasan" value={s.unexplained}
          hint="penyebab belum diisi pelaksana" tone="text-amber-700" />
        <Metric label="Rekomendasi kalibrasi" value={recs.length}
          hint="bisa langsung diterapkan ke template" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-2.5 shadow-[var(--shadow-card)]">
        <p className="text-[11px] text-muted-foreground">
          Kalibrasi mengubah <b>template</b> (durasi / waktu tunggu) — jadwal rumah yang sudah
          dibuat tidak bergeser. Angka baru dipakai saat jadwal berikutnya dibuat.
        </p>
        <Button size="sm" variant="outline" data-testid={BUILD.analyticsOpenCalibration}
          onClick={() => nav(`/build-calibration${projectId ? `?project_id=${projectId}` : ""}`)}>
          <SlidersHorizontal className="mr-1.5 h-3.5 w-3.5" /> Layar Kalibrasi lengkap
        </Button>
      </div>

      {recs.length ? (
        <div className="space-y-2 rounded-xl border border-sky-200 bg-sky-50 p-3">
          <p className="inline-flex items-center gap-1.5 text-sm font-semibold text-sky-900">
            <Lightbulb className="h-4 w-4" /> Rekomendasi kalibrasi dari data nyata
          </p>
          {recs.map((r, i) => (
            <div key={i} data-testid={BUILD.analyticsRec}
              className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
              <p className="text-xs font-semibold">{r.title}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">{r.detail}</p>
              <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-medium text-primary">{r.action}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {r.calibration ? (
                    <Button size="sm" data-testid={BUILD.analyticsRecCalibrate}
                      data-step={r.calibration.step_code} disabled={!can.calibrate}
                      onClick={() => openCalibration(r.calibration.step_code,
                        r.calibration.kind, r.calibration.delta_days, null)}>
                      <SlidersHorizontal className="mr-1 h-3.5 w-3.5" />
                      {can.calibrate ? "Kalibrasi sekarang" : "Kalibrasi (khusus PM)"}
                    </Button>
                  ) : null}
                  {onOpenTemplates ? (
                    <Button size="sm" variant="outline" data-testid={BUILD.analyticsRecAction}
                      onClick={() => onOpenTemplates(r)}>
                      <Wrench className="mr-1 h-3.5 w-3.5" /> Buka Template Jadwal
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <h4 className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold">
          <AlertTriangle className="h-4 w-4 text-rose-600" /> Pekerjaan paling sering telat
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-secondary text-left">
              <tr>
                {["Langkah", "Minggu", "Rumah telat", "Rata-rata", "Maks", "Rasio",
                  "Durasi template", "Penyebab dominan", "Unit", "Kalibrasi"].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2.5 py-2 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {steps.map((r) => (
                <tr key={r.step_code} data-testid={BUILD.analyticsStepRow} className="border-t">
                  <td className="px-2.5 py-2">
                    <span className="font-mono font-semibold">{r.step_code}</span>
                    <span className="ml-1.5 text-muted-foreground">{r.name}</span>
                  </td>
                  <td className="px-2.5 py-2 tabular-nums">M{r.week}</td>
                  <td className="px-2.5 py-2 tabular-nums font-semibold text-rose-700">
                    {r.units_late}/{r.units_total}
                  </td>
                  <td className="px-2.5 py-2 tabular-nums">{r.avg_days} hari</td>
                  <td className="px-2.5 py-2 tabular-nums">{r.max_days} hari</td>
                  <td className="px-2.5 py-2 tabular-nums">{r.late_rate}%</td>
                  <td className="px-2.5 py-2 tabular-nums text-muted-foreground">
                    {r.planned_days} hari{r.wait_days ? ` +${r.wait_days} tunggu` : ""}
                  </td>
                  <td className="px-2.5 py-2">
                    {r.dominant_cause ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                        <RefLabel group="build_delay_cause" value={r.dominant_cause.cause} />
                        {" "}({r.dominant_cause.count})
                      </span>
                    ) : <span className="text-muted-foreground">belum dijelaskan</span>}
                  </td>
                  <td className="px-2.5 py-2 text-[11px] text-muted-foreground">
                    {(r.unit_codes || []).join(", ")}
                  </td>
                  <td className="px-2.5 py-2">
                    <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]"
                      data-testid={BUILD.analyticsStepCalibrate} data-step={r.step_code}
                      disabled={!can.calibrate}
                      onClick={() => openCalibration(r.step_code, "step_duration", 0, r)}>
                      <SlidersHorizontal className="mr-1 h-3 w-3" /> Kalibrasi
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <h4 className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold">
            <UserCog className="h-4 w-4" /> Pelaksana paling sering telat
          </h4>
          <div className="space-y-1.5">
            {people.map((p) => (
              <div key={p.assigned_to} data-testid={BUILD.analyticsPersonRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-2.5 text-xs">
                <div className="min-w-0">
                  <p className="font-medium">{p.assigned_to}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {p.items_late} dari {p.items_total} pekerjaan telat · rata-rata{" "}
                    {p.avg_days} hari · selesai {p.items_done}
                    {p.unexplained ? ` · ${p.unexplained} tanpa penjelasan` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`font-semibold tabular-nums ${p.late_rate >= 40
                    ? "text-rose-700" : "text-amber-700"}`}>{p.late_rate}%</p>
                  {p.dominant_cause ? (
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="build_delay_cause" value={p.dominant_cause.cause} />
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <h4 className="mb-2 text-sm font-semibold">Keterlambatan per tipe unit</h4>
          <div className="space-y-1.5">
            {types.map((tp) => (
              <div key={tp.unit_type} data-testid={BUILD.analyticsTypeRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-2.5 text-xs">
                <div>
                  <p className="font-medium">{tp.unit_type}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {tp.items_late}/{tp.items_total} pekerjaan telat · rata-rata {tp.avg_days} hari
                    {(tp.templates || []).length ? ` · template ${tp.templates.join(", ")}` : ""}
                  </p>
                </div>
                <p className={`font-semibold tabular-nums ${tp.late_rate >= 35
                  ? "text-rose-700" : "text-emerald-700"}`}>{tp.late_rate}%</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {calib ? (
        <CalibrationHistoryPanel rows={calib.history} canCalibrate={can.calibrate}
          onRollback={(c) => setRollback(c)} />
      ) : null}

      <CalibrationDialog open={!!dialog} onOpenChange={(v) => !v && setDialog(null)}
        target={dialog?.target} initialKind={dialog?.kind} initialDelta={dialog?.delta}
        source="analitik_telat" canCalibrate={can.calibrate} onDone={afterChange} />

      <CalibrationRollbackDialog open={!!rollback}
        onOpenChange={(v) => !v && setRollback(null)} calibration={rollback}
        onDone={afterChange} />
    </div>
  );
}

function Metric({ label, value, hint, tone = "" }) {
  return (
    <MetricCard label={label} value={value} hint={hint} tone={tone || "text-foreground"}
      dot={false} testId={undefined} />
  );
}
