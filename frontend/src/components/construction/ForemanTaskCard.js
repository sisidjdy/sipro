import React from "react";
import {
  AlertTriangle, CalendarClock, CheckCircle2, ChevronDown, ChevronUp, ImageIcon, Lock,
  MapPin, PlayCircle, Upload, XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { ITEM_TONE, shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";

/**
 * ForemanTaskCard — satu INSTRUKSI KERJA di Papan Mandor (dipakai dari HP).
 *
 * Kartu ini menjawab pertanyaan mandor dalam satu tatapan: apa yang dikerjakan, sampai
 * kapan, apa yang diperiksa (checklist mutu + hold point), berapa foto bukti yang wajib,
 * siapa yang memvalidasi — lalu satu tombol besar untuk mengambil foto & mengajukan.
 * Pekerjaan yang belum boleh dikerjakan tampil sebagai "instruksi menunggu" beserta
 * alasannya, jadi urutan pekerjaan tidak bisa dilangkahi.
 */
export default function ForemanTaskCard({
  row, mode = "work", open, onToggle, onStart, onSubmit, onVerify, onReject, onDelay,
  onOpenUnit,
}) {
  const waiting = mode === "waiting";
  const verifyMode = mode === "verify";
  const late = row.days_late || 0;
  const photoShort = Math.max(0, (row.min_photos || 0) - (row.photos_attached || 0));

  return (
    <div data-testid={BUILD.boardCard} data-step={row.step_code} data-status={row.status}
      className={`rounded-xl border bg-card p-3 shadow-sm ${late ? "border-rose-200" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-semibold leading-snug">
            <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
              {row.unit_code}
            </span>
            {row.name}
            {row.hold_point ? (
              <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">
                HOLD POINT
              </span>
            ) : null}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <CalendarClock className="h-3 w-3" />
              {shortDate(row.planned_start)} → {shortDate(row.planned_finish)}
            </span>
            <span>minggu {row.week}</span>
            <span>bobot {row.weight}%</span>
            <span><RefLabel group="work_category" value={row.work_category} /></span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusPill status={row.status} group="build_item_status"
            tone={ITEM_TONE[row.status] || "draft"} />
          {late ? (
            <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-700">
              telat {late} hari
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${photoShort
          ? "border-amber-200 bg-amber-50 text-amber-800"
          : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
          <ImageIcon className="h-3 w-3" /> bukti {row.photos_attached}/{row.min_photos} foto
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-muted-foreground">
          <CheckCircle2 className="h-3 w-3" /> checklist {row.checklist_total} butir
          {row.checklist_critical ? ` (${row.checklist_critical} kritis)` : ""}
        </span>
        {row.verifier_hint ? (
          <span className="text-muted-foreground">divalidasi {row.verifier_hint}</span>
        ) : null}
      </div>

      {row.rejected_reason && row.status === "rework" ? (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
          <b>Dikembalikan supervisor:</b> {row.rejected_reason}
        </p>
      ) : null}

      {waiting && (row.gate_reasons || []).length ? (
        <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
          <p className="flex items-center gap-1 font-semibold">
            <Lock className="h-3 w-3" /> Belum boleh dikerjakan
          </p>
          {(row.gate_reasons || []).map((r, i) => <p key={i}>• {r.detail}</p>)}
        </div>
      ) : null}

      {row.hold_point && row.hold_note && !waiting ? (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
          <AlertTriangle className="mr-1 inline h-3 w-3" />{row.hold_note}
        </p>
      ) : null}

      <button type="button" data-testid={BUILD.boardInstructionToggle} onClick={onToggle}
        className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        {open ? "Sembunyikan instruksi kerja" : "Lihat instruksi kerja lengkap"}
      </button>
      {open ? (
        <div data-testid={BUILD.boardInstruction}
          className="mt-1.5 space-y-0.5 rounded-lg border bg-secondary/40 p-2.5 text-[11px] leading-relaxed">
          {(row.instruction || []).map((line, i) => (
            <p key={i} className={line.startsWith("  ") ? "pl-3" : "font-medium"}>{line}</p>
          ))}
        </div>
      ) : null}

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {!waiting && !verifyMode && row.status === "ready" ? (
          <Button size="sm" variant="outline" data-testid={BUILD.boardStart}
            onClick={() => onStart(row)}>
            <PlayCircle className="mr-1 h-3.5 w-3.5" /> Mulai kerjakan
          </Button>
        ) : null}
        {!waiting && !verifyMode && ["ready", "in_progress", "rework"].includes(row.status) ? (
          <Button size="sm" data-testid={BUILD.boardSubmit} onClick={() => onSubmit(row)}>
            <Upload className="mr-1 h-3.5 w-3.5" /> Ambil foto & ajukan
          </Button>
        ) : null}
        {verifyMode ? (
          <>
            <Button size="sm" data-testid={BUILD.boardVerify} onClick={() => onVerify(row)}>
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Verifikasi
            </Button>
            <Button size="sm" variant="outline" data-testid={BUILD.boardReject}
              onClick={() => onReject(row)}>
              <XCircle className="mr-1 h-3.5 w-3.5" /> Kembalikan
            </Button>
          </>
        ) : null}
        {late && !waiting && !row.delay_cause ? (
          <Button size="sm" variant="ghost" data-testid={BUILD.boardDelay}
            onClick={() => onDelay(row)}>
            Penyebab telat
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" data-testid={BUILD.boardOpenUnit}
          onClick={() => onOpenUnit(row)}>
          <MapPin className="mr-1 h-3.5 w-3.5" /> Jadwal unit
        </Button>
      </div>
      {row.delay_cause ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Penyebab telat: <b><RefLabel group="build_delay_cause" value={row.delay_cause} /></b>
        </p>
      ) : null}
    </div>
  );
}
