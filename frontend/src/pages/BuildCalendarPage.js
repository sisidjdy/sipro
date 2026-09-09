import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, CalendarDays, HardHat, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import { AccessDenied, ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import BulkShiftDialog from "@/components/construction/BulkShiftDialog";
import CalendarConflictPanel from "@/components/construction/calendar/CalendarConflictPanel";
import CalendarDayPanel from "@/components/construction/calendar/CalendarDayPanel";
import CalendarMonthGrid from "@/components/construction/calendar/CalendarMonthGrid";
import CalendarToolbar from "@/components/construction/calendar/CalendarToolbar";
import CalendarUnscheduledPanel from "@/components/construction/calendar/CalendarUnscheduledPanel";
import WorkCalendarDialog from "@/components/construction/calendar/WorkCalendarDialog";
import MetricCard from "@/components/patterns/MetricCard";
import api from "@/services/apiClient";
import { KIND_ORDER, monthLabel } from "@/utils/calendarUi";
import { crossLink, keepHub, selfPath } from "@/utils/hubNav";
import { CAL } from "@/constants/testIds";

/**
 * KALENDER JADWAL (Fase 36).
 *
 * Masalah yang ditutup: tenggat pembangunan sebelumnya hanya bisa dilihat per rumah atau
 * sebagai daftar, sehingga BENTROK baru terasa setelah telat — satu mandor kebagian banyak
 * tenggat di hari yang sama, beberapa hold point bertabrakan, dan tenggat mendarat di hari
 * libur nasional lalu tercatat "telat" tanpa ada yang bersalah.
 *
 * Halaman ini menyatukan lima lapisan acara nyata (tenggat pekerjaan, mulai/target selesai
 * rumah, inspeksi QC terjadwal, punch list jatuh tempo, tugas Work Hub tim proyek) dalam
 * satu grid bulanan, menandai bentroknya, dan menawarkan jalan keluar. Kalender ini
 * READ-ONLY: mengubah tanggal tetap lewat dialog geser jadwal Fase 34 yang mewajibkan
 * penyebab + catatan dan tidak pernah menggeser pekerjaan yang sudah diverifikasi.
 */
export default function BuildCalendarPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);

  const [scope, setScope] = useState(params.get("scope") || "project");
  const [projectId, setProjectId] = useState(params.get("project_id") || null);
  const [month, setMonth] = useState(params.get("month") || "");
  const [months, setMonths] = useState([]);
  const [kinds, setKinds] = useState(KIND_ORDER);
  const [assignee, setAssignee] = useState("");
  const [data, setData] = useState(null);
  const [can, setCan] = useState({ configure: false, shift: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const [pickedDay, setPickedDay] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shiftOpen, setShiftOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get("/build/calendar/months", { params: { months: 8 } });
        setMonths(r.data.data || []);
      } catch { /* dropdown bulan opsional: panah bulan tetap bekerja */ }
    })();
  }, []);

  const load = useCallback(async () => {
    if (scope === "project" && !projectId) return;
    setLoading(true);
    setError("");
    try {
      const r = await api.get("/build/calendar", {
        params: {
          month: month || undefined,
          project_id: scope === "project" ? projectId : undefined,
          kinds: kinds.length === KIND_ORDER.length ? undefined : kinds.join(","),
          assignee: assignee || undefined,
        },
      });
      setData(r.data.data || null);
      setCan(r.data.can || { configure: false, shift: false });
      setDenied(false);
      if (!month && r.data.data?.month) setMonth(r.data.data.month);
    } catch (e) {
      if (e?.response?.status === 403) setDenied(true);
      else setError(e?.response?.data?.detail || "Gagal memuat kalender jadwal.");
    } finally { setLoading(false); }
  }, [scope, projectId, month, kinds, assignee]);

  useEffect(() => { load(); }, [load]);

  // URL mengikuti keadaan supaya tautan bisa dibagikan ke rekan kerja — DITULIS KE PATHNAME
  // YANG SEDANG DIPAKAI (`/build-calendar` atau tab hub `/build`), lihat `utils/hubNav.js`.
  useEffect(() => {
    const q = new URLSearchParams();
    q.set("scope", scope);
    if (scope === "project" && projectId) q.set("project_id", projectId);
    if (month) q.set("month", month);
    keepHub(loc.search, q);
    nav({ pathname: selfPath(loc.pathname, "/build-calendar"), search: `?${q.toString()}` },
      { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, projectId, month]);

  const step = (delta) => {
    const base = data?.month || month;
    if (!base) return;
    setMonth(delta < 0 ? data?.prev_month || base : data?.next_month || base);
  };

  const toggleKind = (k) => setKinds((prev) => (prev.includes(k)
    ? (prev.length === 1 ? prev : prev.filter((x) => x !== k))
    : [...prev, k]));

  const dayRow = (data?.days || []).find((d) => d.date === pickedDay) || null;
  const dayEvents = (data?.events || []).filter((e) => e.date === pickedDay);
  const dayConflicts = (data?.conflicts || []).filter((c) => c.date === pickedDay);
  const s = data?.summary || {};

  if (denied) {
    return (
      <div className="space-y-4" data-testid={CAL.page}>
        <AccessDenied testId={CAL.denied}
          title="Kalender Jadwal hanya untuk tim Proyek"
          description="Kalender ini memuat tenggat pembangunan tiap rumah, rencana inspeksi, dan tugas tim proyek — dibuka untuk Manajer Proyek, pelaksana lapangan, Keuangan, dan Direksi."
          askWho="Bila Anda perlu memantau tenggat pembangunan, mintakan hak akses ke admin sistem." />
      </div>
    );
  }

  return (
    <div data-testid={CAL.page} className="space-y-4">
      <div className="sticky top-0 z-20 -mx-4 border-b bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-primary" />
            <div>
              <h1 className="page-title">Kalender Jadwal</h1>
              <p className="text-xs text-muted-foreground">
                Seluruh tenggat rumah dalam satu bulan — bentrok beban, tumpukan pekerjaan
                kritis, dan tenggat yang jatuh di hari libur terlihat sebelum terjadi.
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm"
            onClick={() => nav(crossLink(loc.pathname, "/construction", "tab=monitor"))}>
            <HardHat className="mr-1.5 h-3.5 w-3.5" /> Monitoring Unit
          </Button>
        </div>
      </div>

      <CalendarToolbar
        scope={scope} onScope={(v) => { setScope(v); setPickedDay(null); }}
        projectId={projectId} onProject={setProjectId}
        month={data?.month || month} months={months} onMonth={setMonth} onStep={step}
        onToday={() => setMonth("")} kinds={kinds} onToggleKind={toggleKind}
        assignees={data?.assignees} assignee={assignee} onAssignee={setAssignee}
        onRefresh={load} loading={loading} can={can}
        onOpenSettings={() => setSettingsOpen(true)} onOpenShift={() => setShiftOpen(true)} />

      {error ? <ErrorState message={error} onRetry={load} /> : null}

      {scope === "project" && !projectId ? (
        <EmptyState icon={CalendarDays} title="Pilih proyek"
          description="Pilih proyek untuk melihat kalender tenggat pembangunannya, atau ganti cakupan menjadi 'Semua proyek' untuk tampilan portofolio." />
      ) : null}

      {loading && !data ? (
        <div data-testid={CAL.loading}><LoadingCards count={3} /></div>
      ) : null}

      {data ? (
        <>
          <div data-testid={CAL.summary} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Metric label={`Acara ${monthLabel(data.month)}`} value={s.totals?.all ?? 0}
              hint={`${s.totals?.work_deadline ?? 0} tenggat pekerjaan`} />
            <Metric label="Pekerjaan telat" value={s.late ?? 0}
              hint="lewat tenggat & belum diverifikasi" tone="text-rose-700" />
            <Metric label="Bentrok terdeteksi" value={s.conflicts?.total ?? 0}
              hint={`${s.conflicts?.overload ?? 0} beban · ${s.conflicts?.non_workday ?? 0} hari libur`}
              tone={(s.conflicts?.total ?? 0) ? "text-amber-700" : "text-emerald-700"} />
            <Metric label="Hari kerja bulan ini" value={s.work_days ?? 0}
              hint={`${s.off_days ?? 0} hari libur · ${s.half_days ?? 0} setengah hari`} />
            <Metric label="Pelaksana terlibat" value={s.people ?? 0}
              hint={s.busiest ? `terpadat ${s.busiest.date} (${s.busiest.count})` : "—"} />
          </div>

          {(s.holidays || []).length ? (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-2.5 text-[11px] text-rose-900">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span className="font-semibold">Hari libur bulan ini:</span>
              {s.holidays.map((h) => (
                <span key={h.date} className="rounded-full border border-rose-200 bg-white px-2 py-0.5">
                  {String(h.date).slice(8, 10)} — {h.name}
                </span>
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-3">
              {!(data.events || []).length ? (
                <div data-testid={CAL.empty}>
                  <EmptyState icon={TrendingUp} title={`Belum ada acara pada ${monthLabel(data.month)}`}
                    description="Tidak ada tenggat pekerjaan, inspeksi, punch list, maupun tugas tim proyek pada bulan ini. Gunakan panah bulan untuk melihat bulan lain, atau buat jadwal rumah di Monitoring Unit." />
                </div>
              ) : null}
              <CalendarMonthGrid days={data.days} selected={pickedDay}
                onPick={(d) => setPickedDay(d)} />
            </div>

            <div className="space-y-4">
              <CalendarConflictPanel conflicts={data.conflicts} summary={s}
                outlook={data.outlook} thresholds={s.thresholds} canShift={can.shift}
                onOpenDay={(d) => setPickedDay(d)} onShift={() => setShiftOpen(true)}
                onJumpMonth={(m) => setMonth(m)} />
              <CalendarUnscheduledPanel rows={data.unscheduled} canSchedule={can.configure}
                onDone={load} />
            </div>
          </div>
        </>
      ) : null}

      <CalendarDayPanel date={pickedDay} day={dayRow} events={dayEvents}
        conflicts={dayConflicts} open={!!pickedDay}
        onOpenChange={(v) => !v && setPickedDay(null)} canShift={can.shift}
        onShift={() => { setShiftOpen(true); }} />

      <WorkCalendarDialog open={settingsOpen} onOpenChange={setSettingsOpen}
        projectId={scope === "project" ? projectId : null}
        projectName={(data?.projects || []).find((p) => p.id === projectId)?.name}
        onSaved={load} />

      <BulkShiftDialog projectId={scope === "project" ? projectId : null} open={shiftOpen}
        onOpenChange={setShiftOpen} onDone={load} />
    </div>
  );
}

function Metric({ label, value, hint, tone = "" }) {
  return (
    <MetricCard label={label} value={value} hint={hint} tone={tone || "text-foreground"}
      dot={false} testId={undefined} />
  );
}
