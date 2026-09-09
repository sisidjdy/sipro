import React, { useState } from "react";
import { CheckCircle2, Clock, AlarmClock, ExternalLink, HardHat, ShieldCheck, Camera,
  FileText, RotateCcw, Hourglass } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { dueLabel } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import { HOME, WORK } from "@/constants/testIds";

const PROOF_ICON = { photo: Camera, document: FileText, wa_message: ExternalLink };

/**
 * TaskCard — kartu tugas Work Hub.
 *
 * Fase 29: kartu tidak lagi "buntu". Setiap kartu menyebut DIVISI + kode JOBDESK,
 * menandai bukti yang wajib dilampirkan, status verifikasi, dan menyediakan dua aksi
 * nyata: buka detail (untuk mengajukan hasil) dan buka halaman kerja terkait.
 */
export default function TaskCard({ task, onComplete, onSnooze, onOpen, compact }) {
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const due = dueLabel(task.due_date);
  const dueTone = {
    overdue: "text-rose-600", "due-today": "text-amber-600",
    "on-track": "text-emerald-600", muted: "text-muted-foreground",
  }[due.tone];
  const needsProof = (task.proof_kind || "none") !== "none";
  const ProofIcon = PROOF_ICON[task.proof_kind] || ShieldCheck;
  const rejected = task.review === "rejected";
  const submitted = task.status === "submitted";
  // Fase 32: task pekerjaan konstruksi HANYA boleh diselesaikan lewat Papan Mandor
  // (foto bukti, checklist mutu, urutan pekerjaan, dan progres unit diperiksa di sana).
  // Karena itu kartunya tidak menampilkan tombol Ajukan Hasil generik yang akan ditolak
  // server — tombolnya langsung membawa pengguna ke tempat kerja yang benar.
  const buildItem = task.meta?.build_item_id;

  const doComplete = async () => {
    if (!onComplete) return;
    setBusy(true);
    try { await onComplete(task); } finally { setBusy(false); }
  };
  const doSnooze = async () => {
    if (!onSnooze) return;
    setBusy(true);
    try { await onSnooze(task); } finally { setBusy(false); }
  };

  return (
    <div data-testid={HOME.taskCard} data-task-id={task.id}
      data-jobdesk={task.jobdesk_code || ""}
      className={cn("rounded-xl border bg-card p-3.5 shadow-sm transition-shadow hover:shadow-md",
        rejected && "border-rose-200", submitted && "border-sky-200")}>
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={() => onOpen && onOpen(task)}
          data-testid={WORK.taskOpenBtn}
          className="min-w-0 flex-1 text-left" aria-label={`Buka detail tugas ${task.title}`}>
          <p className="font-medium text-sm leading-snug">{task.title}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <StatusPill status={task.priority} group="priority" />
            <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
              <RefLabel group="task_type" value={task.type} />
            </span>
            {task.division ? (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">
                <RefLabel group="division" value={task.division} />
              </span>
            ) : null}
            {task.jobdesk_code ? (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
                {task.jobdesk_code}
              </span>
            ) : null}
            {task.sla_breached ? <StatusPill status="overdue" label="SLA lewat" /> : null}
            {submitted ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-semibold text-sky-800">
                <Hourglass className="h-3 w-3" /> Menunggu verifikasi
              </span>
            ) : null}
            {rejected ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-800">
                <RotateCcw className="h-3 w-3" /> Dikembalikan
              </span>
            ) : null}
          </div>
        </button>
        {!compact && (
          <div className="flex shrink-0 items-center gap-1.5">
            {onSnooze ? (
              <Button data-testid={WORK.taskSnoozeBtn} size="sm" variant="outline"
                aria-label="Tunda tugas" onClick={doSnooze} disabled={busy}>
                <AlarmClock className="h-3.5 w-3.5" />
              </Button>
            ) : null}
            {buildItem ? (
              <Button data-testid={WORK.taskBuildOpenBtn} size="sm" disabled={busy}
                onClick={() => navigate(task.link || "/construction?tab=board")}>
                <HardHat className="mr-1 h-3.5 w-3.5" /> Buka & ajukan hasil
              </Button>
            ) : needsProof || task.verify_mode !== "none" ? (
              <Button data-testid={WORK.taskSubmitBtn} size="sm" disabled={busy}
                onClick={() => onOpen && onOpen(task)}>
                <ProofIcon className="mr-1 h-3.5 w-3.5" /> Ajukan Hasil
              </Button>
            ) : (
              <Button data-testid={WORK.taskCompleteBtn} size="sm" onClick={doComplete} disabled={busy}>
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Selesai
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]">
        <span className={cn("inline-flex items-center gap-1", dueTone)}>
          <Clock className="h-3 w-3" /> {due.text}
        </span>
        {needsProof ? (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <ProofIcon className="h-3 w-3" /> Bukti: <RefLabel group="proof_kind" value={task.proof_kind} />
          </span>
        ) : null}
        {task.link ? (
          <button type="button" data-testid={WORK.taskLinkBtn}
            onClick={() => navigate(task.link)}
            className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
            <ExternalLink className="h-3 w-3" /> Buka halaman kerja
          </button>
        ) : null}
        {task.assigned_to ? (
          <span className="text-muted-foreground">{task.assigned_to}</span>
        ) : (
          <span className="font-medium text-amber-600">Belum ada penerima</span>
        )}
      </div>
      {rejected && task.rejected_reason ? (
        <p className="mt-2 rounded-md bg-rose-50 px-2.5 py-1.5 text-xs text-rose-800">
          Dikembalikan: {task.rejected_reason}
        </p>
      ) : null}
      {task.verify_note && task.status === "submitted" ? (
        <p className="mt-2 rounded-md bg-sky-50 px-2.5 py-1.5 text-xs text-sky-900">
          {task.verify_note}
        </p>
      ) : null}
    </div>
  );
}
