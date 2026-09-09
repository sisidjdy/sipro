import React from "react";
import {
  CalendarClock, CheckCircle2, Coins, ImageIcon, Lock, PlayCircle, ShieldAlert, Upload, XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { formatIDR } from "@/utils/formatters";
import { photoSrc } from "@/utils/photoSrc";
import { checklistStat, daysLate, ITEM_TONE, shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";

/**
 * Satu ITEM pekerjaan pada jadwal unit.
 *
 * Menampilkan apa adanya: jadwal rencana, gerbang yang menahan (beserta alasannya),
 * hold point, bukti foto yang sudah dilampirkan, checklist mutu, dan aksi yang boleh
 * dilakukan pengguna saat ini. Tidak ada tombol mati: aksi yang tidak boleh dilakukan
 * tidak ditampilkan, dan alasannya dijelaskan.
 */
export default function BuildItemCard({ item, can, currentEmail, onStart, onSubmit, onVerify,
  onReject, onOverride, onDelay }) {
  const gate = item.gate || { open: item.status !== "blocked", reasons: item.gate_reasons || [] };
  const late = item.status !== "done" ? daysLate(item.planned_finish) : 0;
  const stat = checklistStat(item);
  const photos = (item.evidence || []).filter(
    (e) => String(e.content_type || "").startsWith("image"));
  const mine = item.assigned_to === currentEmail;
  const canWork = can?.submit && (mine || can?.verify);
  const isSubmitter = item.submitted_by === currentEmail;

  return (
    <div data-testid={BUILD.item} data-step={item.step_code} data-status={item.status}
      className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
            <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
              {item.step_code}
            </span>
            {item.name}
            {item.hold_point ? (
              <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">
                HOLD POINT
              </span>
            ) : null}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <CalendarClock className="h-3 w-3" />
              Hari {item.day_from}–{item.day_to} · {shortDate(item.planned_start)} →{" "}
              {shortDate(item.planned_finish)}
            </span>
            <span>bobot {item.weight}%</span>
            <span><RefLabel group="work_category" value={item.work_category} /></span>
            {item.assigned_to ? <span>{item.assigned_to}</span> : null}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusPill status={item.status} group="build_item_status"
            tone={ITEM_TONE[item.status] || "draft"} />
          {late ? (
            <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-700">
              telat {late} hari
            </span>
          ) : null}
        </div>
      </div>

      {(item.tasks || []).length ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Lingkup: {(item.tasks || []).join(" · ")}
        </p>
      ) : null}

      {item.hold_point && item.hold_note ? (
        <p data-testid={BUILD.itemHold}
          className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
          {item.hold_note}
        </p>
      ) : null}

      {!gate.open && (gate.reasons || []).length ? (
        <div data-testid={BUILD.itemGate}
          className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
          <p className="flex items-center gap-1 font-semibold">
            <Lock className="h-3 w-3" /> Terkunci — belum boleh dikerjakan
          </p>
          {(gate.reasons || []).map((r, i) => <p key={i}>• {r.detail}</p>)}
        </div>
      ) : null}

      {item.override ? (
        <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
          <b>Gerbang diterobos</b> oleh {item.override.by}: {item.override.note}
        </p>
      ) : null}

      {item.rejected_reason && item.status === "rework" ? (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
          <b>Dikembalikan:</b> {item.rejected_reason}
        </p>
      ) : null}

      {item.delay_cause ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Penyebab telat: <b><RefLabel group="build_delay_cause" value={item.delay_cause} /></b>
          {item.delay_note ? ` — ${item.delay_note}` : ""}
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" /> checklist {stat.passed}/{stat.total}
          {stat.critical ? ` (${stat.critical} kritis)` : ""}
        </span>
        <span className="inline-flex items-center gap-1">
          <ImageIcon className="h-3 w-3" /> bukti {photos.length}/{item.min_photos} foto
        </span>
        {item.verified_by ? <span>diverifikasi {item.verified_by}</span> : null}
        {item.rework_count ? <span>{item.rework_count}× dikembalikan</span> : null}
      </div>

      {item.contract ? (
        <p data-testid={BUILD.itemContract}
          className="mt-2 rounded-lg border bg-secondary/60 p-2 text-[11px]">
          <Coins className="mr-1 inline h-3 w-3" />
          Borongan <b className="tabular-nums">{formatIDR(item.contract.value)}</b> ·{" "}
          {item.contract.subcontractor_name} ({item.contract.spk_number})
          {item.contract.billed ? (
            <span className="ml-1 text-emerald-700">
              · sudah ditagih pada termin {item.contract.claim_number}
            </span>
          ) : item.contract.pending_claim ? (
            <span className="ml-1 text-amber-700">· sedang dalam pengajuan termin</span>
          ) : item.status === "done" ? (
            <span className="ml-1 text-amber-700">· siap ditagih (belum masuk termin)</span>
          ) : (
            <span className="ml-1 text-muted-foreground">
              · baru bisa ditagih setelah diverifikasi
            </span>
          )}
        </p>
      ) : null}

      {photos.length ? (
        <div data-testid={BUILD.itemEvidence} className="mt-2 flex flex-wrap gap-1.5">
          {photos.slice(0, 6).map((p) => (
            <a key={p.file_id} href={photoSrc(p.file_id)} target="_blank" rel="noreferrer"
              className="block h-14 w-20 overflow-hidden rounded border bg-secondary">
              <img src={photoSrc(p.file_id, { variant: "thumb" })} alt={`Bukti ${item.name}`}
                className="h-full w-full object-cover" />
            </a>
          ))}
        </div>
      ) : null}

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {canWork && gate.open && item.status === "ready" ? (
          <Button size="sm" variant="outline" data-testid={BUILD.startBtn}
            onClick={() => onStart(item)}>
            <PlayCircle className="mr-1 h-3.5 w-3.5" /> Mulai kerjakan
          </Button>
        ) : null}
        {canWork && gate.open && ["ready", "in_progress", "rework"].includes(item.status) ? (
          <Button size="sm" data-testid={BUILD.submitBtn} onClick={() => onSubmit(item)}>
            <Upload className="mr-1 h-3.5 w-3.5" /> Ajukan hasil + bukti
          </Button>
        ) : null}
        {can?.verify && item.status === "submitted" ? (
          isSubmitter ? (
            <span className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-900">
              Anda yang mengajukan — verifikasi harus oleh supervisor lain (pemisahan tugas).
            </span>
          ) : (
            <>
              <Button size="sm" data-testid={BUILD.verifyBtn} onClick={() => onVerify(item)}>
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Verifikasi
              </Button>
              <Button size="sm" variant="outline" data-testid={BUILD.rejectBtn}
                onClick={() => onReject(item)}>
                <XCircle className="mr-1 h-3.5 w-3.5" /> Kembalikan
              </Button>
            </>
          )
        ) : null}
        {can?.override && item.status === "blocked" ? (
          <Button size="sm" variant="ghost" data-testid={BUILD.overrideBtn}
            onClick={() => onOverride(item)}>
            <ShieldAlert className="mr-1 h-3.5 w-3.5" /> Terobos gerbang
          </Button>
        ) : null}
        {can?.submit && late && item.status !== "done" ? (
          <Button size="sm" variant="ghost" data-testid={BUILD.delayBtn}
            onClick={() => onDelay(item)}>
            Penyebab telat
          </Button>
        ) : null}
      </div>
    </div>
  );
}
