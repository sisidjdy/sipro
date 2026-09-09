import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarDays, CalendarPlus, PauseCircle, PlayCircle, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import BuildItemCard from "@/components/construction/BuildItemCard";
import Hint from "@/components/construction/BuildHint";
import UnitTimelineChart from "@/components/construction/UnitTimelineChart";
import ShiftHistoryPanel from "@/components/construction/ShiftHistoryPanel";
import GenerateScheduleDialog from "@/components/construction/GenerateScheduleDialog";
import {
  DelayCauseDialog, OverrideGateDialog, RejectItemDialog, SubmitItemDialog, VerifyItemDialog,
} from "@/components/construction/BuildItemDialogs";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { deviationTone, SCHEDULE_TONE, shortDate } from "@/utils/buildUi";
import { BUILD, UNIT_BUILD } from "@/constants/testIds";

/**
 * ISI jadwal pembangunan satu unit: kurva-S, minggu → langkah, gerbang, bukti, dan aksi
 * (mulai, ajukan hasil, verifikasi, tolak, override beralasan, sebab keterlambatan,
 * hentikan/lanjutkan jadwal).
 *
 * Fase 46 (dok 29 §3, CR-29): komponen ini dipisah dari `UnitScheduleSheet` supaya bisa
 * dipakai LANGSUNG sebagai halaman — Unit 360 → tab Pembangunan. Sebelumnya seluruh
 * pekerjaan unit hanya bisa dibuka lewat drawer dari layar monitoring, padahal aturan IA V2
 * menyatakan konten panjang harus punya halaman sendiri. Drawer tetap ada untuk drill cepat
 * dari papan monitoring, dan keduanya kini memakai SATU kode yang sama (bukan dua salinan
 * yang bisa berbeda perilaku).
 */
export default function UnitScheduleView({ unitId, onChanged, embedded = false }) {
  const { user } = useAuth();
  const [bundle, setBundle] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dialog, setDialog] = useState({ kind: null, item: null });
  const [holdOpen, setHoldOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);

  const load = useCallback(async () => {
    if (!unitId) return;
    setLoading(true);
    try {
      const r = await api.get(`/build/unit/${unitId}`);
      setBundle(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat jadwal unit.");
    } finally { setLoading(false); }
  }, [unitId]);

  useEffect(() => { load(); }, [load]);

  const after = () => { load(); onChanged && onChanged(); };
  const sched = bundle?.data;
  const can = bundle?.can || {};

  const start = async (item) => {
    try {
      await api.post(`/build/items/${item.id}/start`);
      toast.success("Pekerjaan ditandai sedang dikerjakan.");
      after();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulai pekerjaan."); }
  };

  const resume = async () => {
    try {
      await api.post(`/build/schedules/${sched.id}/resume`);
      toast.success("Jadwal dilanjutkan.");
      after();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal melanjutkan jadwal."); }
  };

  if (loading && !bundle) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Memuat jadwal…</p>;
  }
  if (!sched) {
    const tpls = bundle?.matching_templates || [];
    const buildable = bundle?.buildable !== false;
    return (
      <div data-testid={UNIT_BUILD.noSchedule}
        className="rounded-xl border border-dashed bg-card p-6 text-center text-sm text-muted-foreground">
        {bundle?.message || "Unit ini belum punya jadwal pembangunan."}
        <p className="mt-1 text-xs">
          Karena belum dijadwalkan, progres &amp; rencana unit ini ditulis
          <b> “belum ada data”</b> — bukan 0%.
        </p>
        {bundle && buildable ? (
          <p data-testid={UNIT_BUILD.templateHint} className="mt-3 text-xs">
            {tpls.length
              ? <>Template yang cocok untuk tipe <b>{bundle?.unit?.type || "—"}</b>:{" "}
                {tpls.map((t) => <span key={t.id} data-testid={UNIT_BUILD.templateChip}
                  className="mx-0.5 inline-block rounded-full border bg-background px-2 py-0.5 font-mono text-[11px]">
                  {t.code}</span>)}</>
              : <span className="text-amber-700">Belum ada Template Jadwal yang mencakup tipe{" "}
                <b>{bundle?.unit?.type || "—"}</b>. Buat/ubah template di Pembangunan › Template
                Jadwal dan tambahkan tipe ini pada daftar tipe unitnya.</span>}
          </p>
        ) : null}
        {can.configure && buildable ? (
          <div className="mt-4 flex justify-center">
            <Button size="sm" data-testid={UNIT_BUILD.generateBtn} onClick={() => setGenOpen(true)}>
              <CalendarPlus className="mr-1.5 h-4 w-4" /> Buat jadwal dari template
            </Button>
          </div>
        ) : null}
        <GenerateScheduleDialog projectId={bundle?.unit?.project_id} open={genOpen}
          onOpenChange={setGenOpen} presetUnitId={unitId} onDone={after} />
      </div>
    );
  }

  return (
    <div data-testid={UNIT_BUILD.schedule} className={embedded ? "space-y-4" : "space-y-4 pb-10"}>
      <div data-testid={BUILD.sheetMetrics} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="text-[11px] text-muted-foreground">
              Progres terverifikasi · unit {bundle?.unit?.code || "—"}
              {sched.template_name ? ` · ${sched.template_name}` : ""}
            </p>
            <p className="font-heading text-3xl font-bold tabular-nums text-primary">
              {sched.progress}%
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill status={sched.status} group="build_schedule_status"
              tone={SCHEDULE_TONE[sched.status] || "draft"} />
            <div className="text-right text-xs">
              <p className="text-muted-foreground">
                Rencana hari ini {sched.planned_progress}%
              </p>
              <p className={`font-semibold ${deviationTone(sched.deviation)}`}>
                {sched.deviation >= 0 ? "+" : ""}{sched.deviation}% ·{" "}
                {sched.deviation_days ? `setara ${sched.deviation_days} hari tertinggal`
                  : "sesuai jadwal"}
              </p>
            </div>
          </div>
        </div>
        <Progress value={sched.progress} className="mt-2 h-2.5" />
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <Metric label="Item selesai" value={`${sched.items_done}/${sched.items_total}`} />
          <Metric label="Telat" value={sched.late_items} tone="text-rose-700" />
          <Metric label="Tertahan gerbang" value={sched.blocked_items} tone="text-amber-700" />
          <Metric label="Override" value={sched.overrides || 0}
            tone={sched.overrides ? "text-rose-700" : ""} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-3 w-3" /> {shortDate(sched.start_date)} →{" "}
            {shortDate(sched.target_finish_date)}
          </span>
          {sched.build_started_at ? (
            <span>Mulai bangun dicatat {shortDate(sched.build_started_at)}</span>
          ) : null}
          {sched.lead_name ? (
            <span className="inline-flex items-center gap-1">
              <User className="h-3 w-3" /> Pembeli: <b>{sched.lead_name}</b>
              {sched.customer_id ? " (data KYC lengkap)" : " (belum jadi customer)"}
            </span>
          ) : <span>Belum ada pembeli terikat pada unit ini</span>}
        </div>
        {sched.status === "on_hold" ? (
          <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            <b>Dihentikan sementara</b>{" "}
            (<RefLabel group="build_delay_cause" value={sched.hold_cause} />):{" "}
            {sched.hold_note}
          </p>
        ) : null}
        {(sched.start_gate_log || []).length ? (
          <p className="mt-2 rounded-lg border border-sky-200 bg-sky-50 p-2 text-[11px] text-sky-900">
            <b>Jejak gerbang mulai bangun:</b>{" "}
            {sched.start_gate_log[sched.start_gate_log.length - 1].by} ·{" "}
            {shortDate(sched.start_gate_log[sched.start_gate_log.length - 1].at)}
            {sched.start_gate_log[sched.start_gate_log.length - 1].acknowledged
              ? ` · mengakui ${(sched.start_gate_log[sched.start_gate_log.length - 1]
                .warnings || []).length} peringatan: "${sched.start_gate_log[
                sched.start_gate_log.length - 1].reason}"`
              : " · tanpa peringatan"}
          </p>
        ) : null}
        {can.verify ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {sched.status === "on_hold" ? (
              <Button size="sm" variant="outline" data-testid={BUILD.resumeBtn} onClick={resume}>
                <PlayCircle className="mr-1 h-3.5 w-3.5" /> Lanjutkan jadwal
              </Button>
            ) : (
              <Button size="sm" variant="outline" data-testid={BUILD.holdBtn}
                onClick={() => setHoldOpen(true)}>
                <PauseCircle className="mr-1 h-3.5 w-3.5" /> Hentikan sementara
              </Button>
            )}
          </div>
        ) : null}
      </div>

      <UnitTimelineChart timeline={bundle.timeline} deviation={sched.deviation} />

      <ShiftHistoryPanel history={sched.shift_history} />

      {(bundle.weeks || []).map((w) => {
        const done = w.items.filter((i) => i.status === "done").length;
        return (
          <div key={w.week} data-testid={BUILD.week} data-week={w.week} className="space-y-2">
            <div className="flex items-center justify-between rounded-lg bg-secondary px-3 py-1.5">
              <p className="text-xs font-semibold">Minggu {w.week}</p>
              <p className="text-[11px] text-muted-foreground">
                {done}/{w.items.length} item selesai
              </p>
            </div>
            {w.items.map((it) => (
              <BuildItemCard key={it.id} item={it} can={can} currentEmail={user?.email}
                onStart={start}
                onSubmit={(x) => setDialog({ kind: "submit", item: x })}
                onVerify={(x) => setDialog({ kind: "verify", item: x })}
                onReject={(x) => setDialog({ kind: "reject", item: x })}
                onOverride={(x) => setDialog({ kind: "override", item: x })}
                onDelay={(x) => setDialog({ kind: "delay", item: x })} />
            ))}
          </div>
        );
      })}

      <SubmitItemDialog item={dialog.kind === "submit" ? dialog.item : null}
        unitCode={bundle?.unit?.code} open={dialog.kind === "submit"}
        onOpenChange={(v) => !v && setDialog({ kind: null, item: null })} onDone={after} />
      <VerifyItemDialog item={dialog.kind === "verify" ? dialog.item : null}
        open={dialog.kind === "verify"}
        onOpenChange={(v) => !v && setDialog({ kind: null, item: null })} onDone={after} />
      <RejectItemDialog item={dialog.kind === "reject" ? dialog.item : null}
        open={dialog.kind === "reject"}
        onOpenChange={(v) => !v && setDialog({ kind: null, item: null })} onDone={after} />
      <OverrideGateDialog item={dialog.kind === "override" ? dialog.item : null}
        open={dialog.kind === "override"}
        onOpenChange={(v) => !v && setDialog({ kind: null, item: null })} onDone={after} />
      <DelayCauseDialog item={dialog.kind === "delay" ? dialog.item : null}
        open={dialog.kind === "delay"}
        onOpenChange={(v) => !v && setDialog({ kind: null, item: null })} onDone={after} />
      <HoldDialog schedule={sched} open={holdOpen} onOpenChange={setHoldOpen} onDone={after} />
    </div>
  );
}

function Metric({ label, value, tone = "" }) {
  return (
    <MetricCard label={label} value={value} tone={tone || "text-foreground"} compact
      dot={false} testId={undefined} />
  );
}

function HoldDialog({ schedule, open, onOpenChange, onDone }) {
  const [cause, setCause] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setCause(""); setNote(""); } }, [open]);
  if (!schedule) return null;
  const problems = [];
  if (!cause) problems.push("Pilih penyebab penghentian dari daftar.");
  if (note.trim().length < 10) problems.push("Penjelasan minimal 10 karakter.");

  const run = async () => {
    if (problems.length) { toast.error(problems[0]); return; }
    setBusy(true);
    try {
      await api.post(`/build/schedules/${schedule.id}/hold`, { cause, note: note.trim() });
      toast.success("Jadwal dihentikan sementara — semua item ikut terkunci.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghentikan jadwal.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUILD.holdDialog} className="bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Hentikan jadwal sementara</DialogTitle>
          <DialogDescription>
            Unit {schedule.unit_code} — selama dihentikan, tidak ada pekerjaan yang bisa
            diajukan dan eskalasi keterlambatan tidak berjalan.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Penyebab</Label>
            <ReferenceSelect group="build_delay_cause" value={cause} onChange={setCause}
              testId={BUILD.holdCause} placeholder="Pilih penyebab…" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="hnote">Penjelasan</Label>
            <Textarea id="hnote" rows={3} data-testid={BUILD.holdNote} value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="mis. hujan deras 3 hari, lokasi tergenang" />
          </div>
        </div>
        <Hint testId={BUILD.holdHint} problems={problems}
          okText="Selama dihentikan, eskalasi keterlambatan berhenti dan alasan tercatat." />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={BUILD.holdSave} onClick={run}
            disabled={busy || !!problems.length}>
            {busy ? "Menyimpan…" : "Hentikan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
