import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CalendarClock, CalendarPlus, ClipboardCheck, Gauge, HardHat, Layers, Lock, RefreshCw,
  ShieldAlert, TimerOff,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import Pagination from "@/components/patterns/Pagination";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import BuildDelayReport from "@/components/construction/BuildDelayReport";
import BuildScheduleRow from "@/components/construction/BuildScheduleRow";
import GenerateScheduleDialog from "@/components/construction/GenerateScheduleDialog";
import BulkScheduleDialog from "@/components/construction/BulkScheduleDialog";
import BulkShiftDialog from "@/components/construction/BulkShiftDialog";
import BulkRunsPanel from "@/components/construction/BulkRunsPanel";
import UnitScheduleSheet from "@/components/construction/UnitScheduleSheet";
import MetricCard from "@/components/patterns/MetricCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import api from "@/services/apiClient";
import { BUILD, P92 } from "@/constants/testIds";

/**
 * MONITORING UNIT — papan pantau pembangunan per rumah.
 *
 * Menggantikan cara lama (mengetik persen progres proyek lalu ditimpa ke semua unit).
 * Semua angka di sini dihitung dari pekerjaan yang benar-benar DIVERIFIKASI beserta
 * buktinya, sehingga bisa dipakai menagih, mengingatkan, dan mengeskalasi.
 */
export default function BuildMonitorPanel({ projectId }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [can, setCan] = useState({});
  const [unsched, setUnsched] = useState([]);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState({ skip: 0, limit: 10 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [openUnit, setOpenUnit] = useState(null);
  const [drill, setDrill] = useState(null);
  const openDrill = (sub, label) => setDrill({ key: `build:${sub}`, label, params: projectId ? { project_id: projectId } : {} });
  const [genOpen, setGenOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [shiftOpen, setShiftOpen] = useState(false);
  const [killRow, setKillRow] = useState(null);
  const [tickKey, setTickKey] = useState(0);
  const [tick, setTick] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [b, u] = await Promise.all([
        api.get("/build/schedules", {
          params: {
            project_id: projectId || undefined, status: status || undefined,
            skip: page.skip, limit: page.limit,
          },
        }),
        api.get("/build/unscheduled", { params: { project_id: projectId || undefined } }),
      ]);
      setRows(b.data.data || []);
      setTotal(b.data.total || 0);
      setSummary(b.data.summary || null);
      setCan(b.data.can || {});
      setUnsched((u.data.data || []).filter((x) => x.buildable));
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat papan pantau pembangunan.");
    } finally { setLoading(false); }
  }, [projectId, status, page.skip, page.limit]);

  useEffect(() => { load(); }, [load]);

  const refresh = () => { setTickKey((k) => k + 1); load(); };

  const runTick = async () => {
    setBusy(true);
    try {
      const r = await api.post("/build/tick");
      const d = r.data?.data || {};
      setTick(d);
      toast.success(`Pemantauan dijalankan: ${d.gates_opened} gerbang dibuka, `
        + `${d.reminders} pengingat, ${d.escalations} eskalasi.`);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan pemantauan.");
    } finally { setBusy(false); }
  };

  const removeSchedule = async () => {
    if (!killRow) return;
    try {
      await api.delete(`/build/schedules/${killRow.id}`);
      toast.success(`Jadwal unit ${killRow.unit_code} dihapus.`);
      setKillRow(null);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghapus jadwal.");
    }
  };

  return (
    <div data-testid={BUILD.monitorPanel} className="space-y-4">
      {summary ? (
        <div data-testid={BUILD.summary} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Metric icon={HardHat} label="Rumah terjadwal" testId={`${P92.buildMetric}-scheduled`}
            onOpen={() => openDrill(summary.unscheduled ? "unscheduled" : "scheduled", summary.unscheduled ? "Unit belum dijadwalkan" : "Unit terjadwal")}
            value={`${summary.scheduled}/${summary.units_total}`}
            hint={summary.unscheduled ? `${summary.unscheduled} belum dijadwalkan` : "lengkap"}
            tone={summary.unscheduled ? "amber" : "emerald"} />
          <Metric icon={Gauge} label="Progres rata-rata" testId={`${P92.buildMetric}-progress`}
            onOpen={() => openDrill("scheduled", "Progres per unit")}
            value={`${summary.avg_progress}%`}
            hint={`rencana ${summary.avg_planned}%`}
            tone={summary.avg_progress + 5 < summary.avg_planned ? "rose" : "emerald"} />
          <Metric icon={ClipboardCheck} label="Menunggu verifikasi" testId={`${P92.buildMetric}-awaiting`}
            onOpen={() => openDrill("awaiting_verification", "Pekerjaan menunggu verifikasi")}
            value={summary.awaiting_verification}
            hint={summary.rework ? `${summary.rework} minta perbaikan` : "tidak ada perbaikan"}
            tone={summary.awaiting_verification ? "sky" : "slate"} />
          <Metric icon={TimerOff} label="Pekerjaan telat" value={summary.late_items} testId={`${P92.buildMetric}-late`}
            onOpen={() => openDrill("late_items", "Pekerjaan telat")}
            hint={`${summary.at_risk} unit berisiko`}
            tone={summary.late_items ? "rose" : "emerald"} />
          <Metric icon={Lock} label="Tertahan gerbang" value={summary.blocked_items} testId={`${P92.buildMetric}-blocked`}
            onOpen={() => openDrill("blocked_items", "Pekerjaan tertahan gerbang")}
            hint={summary.overrides ? `${summary.overrides} pernah diterobos` : "tanpa override"}
            tone={summary.overrides ? "rose" : "slate"} />
        </div>
      ) : null}
      <DrilldownDialog target={drill} onOpenChange={(o) => { if (!o) setDrill(null); }}
        onRow={(r) => { const m = /\/units\/([^/?]+)/.exec(r.href || ""); if (m) setOpenUnit(m[1]); }} />

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-2.5 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Status jadwal</span>
          <div className="w-48">
            <ReferenceSelect group="build_schedule_status" value={status}
              onChange={(v) => { setStatus(v); setPage({ ...page, skip: 0 }); }}
              allowEmpty emptyLabel="Semua status" testId={BUILD.statusFilter} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" data-testid={BUILD.refresh} onClick={refresh}
            disabled={loading}>
            <RefreshCw className={`mr-1 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Muat ulang
          </Button>
          {can.verify ? (
            <Button size="sm" variant="secondary" data-testid={BUILD.tickBtn} onClick={runTick}
              disabled={busy}>
              <ShieldAlert className="mr-1 h-3.5 w-3.5" />
              {busy ? "Menjalankan…" : "Jalankan pemantauan"}
            </Button>
          ) : null}
          {can.configure ? (
            <>
              <Button size="sm" variant="outline" data-testid={BUILD.shiftBtn}
                onClick={() => setShiftOpen(true)} disabled={!total}>
                <CalendarClock className="mr-1 h-3.5 w-3.5" /> Geser jadwal
              </Button>
              <Button size="sm" data-testid={BUILD.bulkBtn} onClick={() => setBulkOpen(true)}>
                <Layers className="mr-1 h-3.5 w-3.5" /> Jadwal massal
              </Button>
              <Button size="sm" variant="secondary" data-testid={BUILD.generateBtn}
                onClick={() => setGenOpen(true)}>
                <CalendarPlus className="mr-1 h-3.5 w-3.5" /> Satu unit
              </Button>
            </>
          ) : null}
        </div>
      </div>

      {tick ? (
        <div data-testid={BUILD.tickResult}
          className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
          <p className="font-semibold">
            Pemantauan terakhir: {tick.schedules} jadwal diperiksa
          </p>
          <p className="mt-0.5">
            {tick.gates_opened} gerbang waktu tunggu dibuka · {tick.reminders} pengingat
            dikirim ke pelaksana · {tick.escalations} eskalasi keterlambatan
            {tick.escalations ? " (supervisor & direksi diberi tahu + tugas kejar dibuat)" : ""}.
          </p>
        </div>
      ) : null}

      {unsched.length ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="font-semibold">
                {unsched.length} rumah belum punya jadwal pembangunan
              </p>
              <p className="mt-0.5">
                Tanpa jadwal, tidak ada tenggat, pengingat, maupun eskalasi untuk unit ini:{" "}
                {unsched.slice(0, 12).map((u) => u.code).join(", ")}
                {unsched.length > 12 ? `, +${unsched.length - 12} lain` : ""}.
              </p>
            </div>
            {can.configure ? (
              <Button size="sm" data-testid={`${BUILD.bulkBtn}-banner`}
                onClick={() => setBulkOpen(true)}>
                <Layers className="mr-1 h-3.5 w-3.5" /> Jadwalkan sekaligus
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {loading ? <LoadingCards count={3} />
        : error ? <ErrorState message={error} onRetry={load} />
          : !rows.length ? (
            <div data-testid={BUILD.empty}>
              <EmptyState icon={HardHat}
                title={status ? "Tidak ada jadwal pada status ini"
                  : "Belum ada jadwal pembangunan"}
                description={can.configure
                  ? "Buat jadwal per unit dari template tipe rumah agar progres, bukti kerja, pengingat, dan eskalasi bisa dipantau."
                  : "Manajer Proyek belum menetapkan jadwal pembangunan unit."}
                actionLabel={can.configure ? "Buat jadwal unit" : null}
                onAction={() => setGenOpen(true)} />
            </div>
          ) : (
            <div className="space-y-3">
              {rows.map((r) => (
                <BuildScheduleRow key={r.id} row={r} can={can}
                  onOpen={setOpenUnit} onDelete={setKillRow} />
              ))}
              <div data-testid={BUILD.pagination}>
                <Pagination total={total} skip={page.skip} limit={page.limit}
                  label="jadwal unit" testId={`${BUILD.pagination}-control`}
                  onChange={setPage} />
              </div>
            </div>
          )}

      <BuildDelayReport projectId={projectId} refreshKey={tickKey} />

      <BulkRunsPanel refreshKey={tickKey} />

      <UnitScheduleSheet unitId={openUnit} open={!!openUnit}
        onOpenChange={(v) => !v && setOpenUnit(null)} onChanged={load} />
      <GenerateScheduleDialog projectId={projectId} open={genOpen} onOpenChange={setGenOpen}
        onDone={(d) => { load(); if (d?.unit_id) setOpenUnit(d.unit_id); }} />
      <BulkScheduleDialog projectId={projectId} open={bulkOpen} onOpenChange={setBulkOpen}
        onDone={() => refresh()} />
      <BulkShiftDialog projectId={projectId} open={shiftOpen} onOpenChange={setShiftOpen}
        onDone={() => refresh()} />
      <ConfirmDialog open={!!killRow} onOpenChange={(v) => !v && setKillRow(null)}
        title="Hapus jadwal unit?"
        description={`Jadwal unit ${killRow?.unit_code || ""} beserta ${killRow?.items_total || 0} `
          + "item pekerjaan akan dihapus. Hanya boleh selama belum ada pekerjaan yang "
          + "diverifikasi."}
        confirmLabel="Hapus jadwal" onConfirm={removeSchedule} />
    </div>
  );
}

const TONE = {
  emerald: "text-emerald-700", rose: "text-rose-700", amber: "text-amber-700",
  sky: "text-sky-700", slate: "text-muted-foreground",
};

function Metric({ icon: Icon, label, value, hint, tone = "slate", onOpen, testId }) {
  // Satu bentuk kartu angka untuk seluruh aplikasi (lihat patterns/MetricCard):
  // nada warna di sini melekat pada KETERANGAN, bukan pada angkanya.
  // Fase 92: bila `onOpen` diberikan, kartu menjadi tombol → popup rincian.
  const card = (
    <MetricCard icon={Icon} label={label} value={value} hint={hint}
      hintTone={TONE[tone]} tone="text-foreground" testId={undefined}
      className={onOpen ? "h-full ring-1 ring-transparent group-hover:ring-primary/50" : undefined} />
  );
  if (!onOpen) return card;
  return (
    <button type="button" onClick={onOpen} data-testid={testId}
      className="group rounded-xl text-left outline-none transition-transform focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99]">
      {card}
    </button>
  );
}
