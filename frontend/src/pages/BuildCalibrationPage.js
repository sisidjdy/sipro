import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  CalendarClock, Lightbulb, RefreshCw, ShieldCheck, SlidersHorizontal, TrendingDown,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { AccessDenied, ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import ProjectSelect from "@/components/construction/ProjectSelect";
import CalibrationDialog from "@/components/construction/calibration/CalibrationDialog";
import CalibrationHistoryPanel from "@/components/construction/calibration/CalibrationHistoryPanel";
import CalibrationRecommendations from "@/components/construction/calibration/CalibrationRecommendations";
import CalibrationRollbackDialog from "@/components/construction/calibration/CalibrationRollbackDialog";
import CalibrationStepTable from "@/components/construction/calibration/CalibrationStepTable";
import CalibrationTemplatePanel from "@/components/construction/calibration/CalibrationTemplatePanel";
import MetricCard from "@/components/patterns/MetricCard";
import api from "@/services/apiClient";
import { crossLink } from "@/utils/hubNav";
import {
  KIND_DEFAULT, countCalibrated, countPending, targetFromTemplateStep,
} from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * KALIBRASI TEMPLATE JADWAL (Fase 37) — dari bukti telat langsung ke angka template.
 *
 * Masalah yang ditutup: Analitik Telat (Fase 32) sudah menunjuk pekerjaan mana yang selalu
 * telat dan memberi rekomendasi kalibrasi, tetapi ujungnya hanya kalimat "buka Template
 * Jadwal lalu ubah hari mulai/selesai langkah ini". Menyimpan template menuntut payload
 * penuh, jadi perencana harus mengetik ulang seluruh template — akibatnya kalibrasi tidak
 * pernah dilakukan, template tetap tidak realistis, dan analitik hanya jadi hiasan.
 *
 * Halaman ini menyatukan bukti + tombol perbaikannya: usulan siap-pakai, tabel langkah yang
 * sering telat, SELURUH langkah template dengan angka yang berlaku sekarang, dan riwayat
 * kalibrasi yang bisa dibatalkan tepat. Yang TIDAK dilakukan halaman ini: menggeser tanggal
 * jadwal rumah yang sudah berjalan — itu tetap lewat "Geser jadwal" (Fase 34) yang
 * mewajibkan penyebab + catatan dan mempertahankan pekerjaan yang sudah diverifikasi.
 */
export default function BuildCalibrationPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);

  const [scope, setScope] = useState(params.get("project_id") ? "project" : "all");
  const [projectId, setProjectId] = useState(params.get("project_id") || null);
  const [data, setData] = useState(null);
  const [can, setCan] = useState({ calibrate: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const [tplId, setTplId] = useState(params.get("template") || "");
  const [dialog, setDialog] = useState(null);
  const [rollback, setRollback] = useState(null);
  const deepLinked = useRef(false);

  const load = useCallback(async () => {
    if (scope === "project" && !projectId) return;
    setLoading(true);
    setError("");
    try {
      const r = await api.get("/build/calibration/candidates", {
        params: { project_id: scope === "project" ? projectId : undefined },
      });
      setData(r.data?.data || null);
      setCan(r.data?.can || { calibrate: false });
      setDenied(false);
    } catch (e) {
      if (e?.response?.status === 403) setDenied(true);
      else setError(e?.response?.data?.detail || "Gagal memuat usulan kalibrasi template.");
    } finally { setLoading(false); }
  }, [scope, projectId]);

  useEffect(() => { load(); }, [load]);

  // Template terpilih selalu ada isinya (default: template pertama yang punya bukti telat).
  useEffect(() => {
    const list = data?.templates || [];
    if (!list.length) return;
    if (!tplId || !list.some((t) => t.id === tplId)) setTplId(list[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const openCalibration = useCallback((target, kind, delta, source) => {
    setDialog({ target, kind: kind || KIND_DEFAULT, delta: delta || 0, source });
  }, []);

  // Tautan dalam dari Analitik Telat: ?step=W3-02&kind=step_duration&delta=3 langsung
  // membuka dialog kalibrasi pada langkah itu (inilah "sekali klik" dari layar analitik).
  useEffect(() => {
    if (deepLinked.current || !data) return;
    const step = params.get("step");
    if (!step) return;
    const list = data.templates || [];
    const wanted = params.get("template");
    const tpl = list.find((t) => (wanted ? t.id === wanted : true)
      && (t.steps || []).some((s) => s.code === step));
    const found = tpl ? (tpl.steps || []).find((s) => s.code === step) : null;
    deepLinked.current = true;
    if (!tpl || !found) return;
    setTplId(tpl.id);
    openCalibration(targetFromTemplateStep(tpl, found), params.get("kind") || KIND_DEFAULT,
      Number(params.get("delta") || 0), "analitik_telat");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const s = data?.summary || {};
  const recs = data?.recommendations || [];
  const steps = data?.steps || [];
  const templates = data?.templates || [];

  if (denied) {
    return (
      <div className="space-y-4" data-testid={CALIB.page}>
        <AccessDenied testId={CALIB.denied}
          title="Kalibrasi template hanya untuk tim Proyek"
          description="Layar ini mengubah durasi & waktu tunggu template jadwal pembangunan berdasarkan bukti keterlambatan — dibuka untuk Manajer Proyek, Direksi, pelaksana lapangan, dan Keuangan."
          askWho="Bila Anda perlu ikut menilai realistisnya jadwal pembangunan, mintakan hak akses ke admin sistem." />
      </div>
    );
  }

  return (
    <div data-testid={CALIB.page} className="space-y-4">
      <div className="sticky top-0 z-20 -mx-4 border-b bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5 text-primary" />
            <div>
              <h1 className="page-title">Kalibrasi Template Jadwal</h1>
              <p className="text-xs text-muted-foreground">
                Ubah durasi atau waktu tunggu langkah pekerjaan langsung dari bukti telat —
                dengan pratinjau dampak, alasan wajib, dan bisa dibatalkan.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" data-testid={CALIB.openAnalytics}
              onClick={() => nav(crossLink(loc.pathname, "/construction", "tab=reports"))}>
              <TrendingDown className="mr-1.5 h-3.5 w-3.5" /> Analitik Telat
            </Button>
            <Button variant="outline" size="sm" data-testid={CALIB.openShift}
              onClick={() => nav(crossLink(loc.pathname, "/build-calendar"))}>
              <CalendarClock className="mr-1.5 h-3.5 w-3.5" /> Geser jadwal berjalan
            </Button>
            <Button variant="ghost" size="sm" data-testid={CALIB.refresh} onClick={load}
              disabled={loading}>
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Muat ulang
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div data-testid={CALIB.scope} className="inline-flex rounded-lg border bg-card p-0.5 shadow-[var(--shadow-card)]">
          {[["all", "Semua proyek"], ["project", "Per proyek"]].map(([v, label]) => (
            <button key={v} type="button" data-scope={v}
              onClick={() => { setScope(v); if (v === "all") setProjectId(null); }}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${scope === v
                ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
              {label}
            </button>
          ))}
        </div>
        {scope === "project" ? (
          <ProjectSelect value={projectId} onChange={setProjectId} testId={CALIB.project} />
        ) : (
          <p className="text-xs text-muted-foreground">
            Template jadwal berlaku lintas proyek, jadi bukti telat dibaca dari seluruh
            proyek. Pilih “Per proyek” bila ingin menilai satu proyek saja.
          </p>
        )}
      </div>

      {error ? <div data-testid={CALIB.error}><ErrorState message={error} onRetry={load} /></div> : null}

      {loading && !data ? (
        <div data-testid={CALIB.loading}><LoadingCards count={3} /></div>
      ) : null}

      {data ? (
        <>
          <div data-testid={CALIB.summary} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Metric label="Pekerjaan telat" value={s.items_late ?? 0}
              hint={`dari ${s.items_total ?? 0} pekerjaan berjadwal`} tone="text-rose-700" />
            <Metric label="Langkah sering telat" value={steps.length}
              hint="punya bukti telat pada tabel di bawah" />
            <Metric label="Usulan siap diterapkan" value={countPending(recs)}
              hint="sekali klik dari bukti, bukan mengetik ulang template"
              tone={countPending(recs) ? "text-amber-700" : "text-emerald-700"} />
            <Metric label="Kalibrasi aktif" value={countCalibrated(templates)}
              hint="langkah dengan angka hasil kalibrasi · bisa dibatalkan"
              tone="text-emerald-700" />
            <Metric label="Template dipantau" value={templates.length}
              hint={`${templates.reduce((n, t) => n + Number(t.steps_count || 0), 0)} langkah pekerjaan`} />
          </div>

          <div data-testid={CALIB.safetyNote}
            className="flex flex-wrap items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-2.5 text-[11px] text-emerald-900">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <p>
              <b>Kalibrasi mengubah TEMPLATE, bukan jadwal rumah yang sudah dibuat.</b> Bukti
              kerja (foto, checklist, verifikasi) dan tanggal rencana yang sudah berjalan tidak
              bergeser sedikit pun; angka baru dipakai saat jadwal berikutnya dibuat. Untuk
              memindahkan tanggal jadwal yang sedang berjalan, pakai “Geser jadwal” — wajib
              penyebab + catatan dan pekerjaan terverifikasi dipertahankan.
            </p>
          </div>

          {!can.calibrate ? (
            <p data-testid={CALIB.viewerNote}
              className="rounded-xl border bg-card p-2.5 text-[11px] text-muted-foreground shadow-[var(--shadow-card)]">
              Anda bisa melihat bukti telat, usulan, angka template, dan riwayat kalibrasi.
              Menerapkan atau membatalkan kalibrasi hanya untuk admin/direksi/Manajer Proyek
              karena durasi &amp; waktu tunggu template menjadi dasar seluruh tenggat,
              pengingat, dan eskalasi pekerjaan.
            </p>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-4">
              <section className="space-y-2">
                <h2 className="inline-flex items-center gap-1.5 text-sm font-semibold">
                  <Lightbulb className="h-4 w-4 text-primary" /> Usulan kalibrasi dari data nyata
                </h2>
                <CalibrationRecommendations recs={recs} canCalibrate={can.calibrate}
                  onCalibrate={openCalibration} onUndo={(applied) => setRollback(applied)} />
              </section>

              <section className="space-y-2">
                <h2 className="inline-flex items-center gap-1.5 text-sm font-semibold">
                  <TrendingDown className="h-4 w-4 text-rose-600" /> Bukti telat per langkah
                </h2>
                <CalibrationStepTable steps={steps} canCalibrate={can.calibrate}
                  onCalibrate={openCalibration} />
              </section>

              <section className="space-y-2">
                <h2 className="text-sm font-semibold">Seluruh langkah template</h2>
                <CalibrationTemplatePanel templates={templates} selectedId={tplId}
                  onSelect={setTplId} canCalibrate={can.calibrate}
                  onCalibrate={openCalibration} />
              </section>
            </div>

            <CalibrationHistoryPanel rows={data.history} canCalibrate={can.calibrate}
              onRollback={(c) => setRollback(c)} />
          </div>
        </>
      ) : null}

      <CalibrationDialog open={!!dialog} onOpenChange={(v) => !v && setDialog(null)}
        target={dialog?.target} initialKind={dialog?.kind} initialDelta={dialog?.delta}
        source={dialog?.source} canCalibrate={can.calibrate} onDone={load} />

      <CalibrationRollbackDialog open={!!rollback}
        onOpenChange={(v) => !v && setRollback(null)} calibration={rollback} onDone={load} />
    </div>
  );
}

function Metric({ label, value, hint, tone = "" }) {
  return (
    <MetricCard label={label} value={value} hint={hint} tone={tone || "text-foreground"}
      dot={false} testId={undefined} />
  );
}
