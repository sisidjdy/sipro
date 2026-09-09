import React from "react";
import {
  ArrowRight, CalendarDays, ClipboardCheck, Lock, ShieldAlert, Trash2, User,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { deviationTone, SCHEDULE_TONE, shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";

/**
 * Satu BARIS papan pantau: satu rumah (unit) dengan jadwalnya.
 *
 * Yang ditampilkan sengaja bukan sekadar angka persen: pengguna perlu tahu
 * pekerjaan apa yang sedang jalan, apa yang menahan, siapa yang harus bergerak,
 * dan berapa hari tertinggal — supaya papan ini bisa dipakai memimpin rapat lapangan.
 */
export default function BuildScheduleRow({ row, can, onOpen, onDelete }) {
  const dev = Number(row.deviation || 0);
  const planned = Math.min(100, Math.max(0, Number(row.planned_progress || 0)));
  const progress = Math.min(100, Math.max(0, Number(row.progress || 0)));
  const late = row.late_detail || [];
  const blocked = row.blocked_detail || [];

  return (
    <div data-testid={BUILD.row} data-unit={row.unit_code}
      className="rounded-xl border bg-card p-3 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-xs text-primary">
              {row.unit_code}
            </span>
            <RefLabel group="unit_type" value={row.unit_type} />
            <span className="text-xs font-normal text-muted-foreground">
              {row.template_name}
            </span>
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="h-3 w-3" /> {shortDate(row.start_date)} →{" "}
              {shortDate(row.target_finish_date)}
            </span>
            <span>{row.items_done}/{row.items_total} item selesai</span>
            {row.lead_name ? (
              <span className="inline-flex items-center gap-1">
                <User className="h-3 w-3" /> {row.lead_name}
              </span>
            ) : <span>belum ada pembeli</span>}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusPill status={row.status} group="build_schedule_status"
            tone={SCHEDULE_TONE[row.status] || "draft"} />
          <span className={`text-[11px] font-semibold ${deviationTone(dev)}`}>
            {dev >= 0 ? `+${dev}` : dev}% ·{" "}
            {row.deviation_days ? `${row.deviation_days} hari tertinggal` : "sesuai jadwal"}
          </span>
        </div>
      </div>

      <div className="mt-2.5">
        <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${progress}%` }} />
          <div className="absolute top-0 h-full w-0.5 bg-amber-500"
            style={{ left: `${planned}%` }} title={`Rencana hari ini ${planned}%`} />
        </div>
        <p className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>Terverifikasi <b className="tabular-nums text-foreground">{progress}%</b></span>
          <span>Rencana hari ini <b className="tabular-nums">{planned}%</b></span>
        </p>
      </div>

      <div className="mt-2 space-y-1 text-[11px]">
        {row.next_item ? (
          <p className="flex items-start gap-1.5 text-foreground">
            <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-primary" />
            <span>
              Sedang jalan: <b>{row.next_item.name}</b> (rencana{" "}
              {shortDate(row.next_item.planned_finish)}
              {row.next_item.assigned_to ? ` · ${row.next_item.assigned_to}` : ""})
            </span>
          </p>
        ) : null}
        {row.awaiting_verification ? (
          <p className="flex items-start gap-1.5 text-sky-800">
            <ClipboardCheck className="mt-0.5 h-3 w-3 shrink-0" />
            <span>Menunggu verifikasi: <b>{row.awaiting_verification.name}</b></span>
          </p>
        ) : null}
        {blocked.map((b, i) => (
          <p key={i} className="flex items-start gap-1.5 text-amber-800"
            data-blocked={row.unit_code}>
            <Lock className="mt-0.5 h-3 w-3 shrink-0" />
            <span>Terkunci: <b>{b.name}</b> — {(b.reasons || []).join(" ")}</span>
          </p>
        ))}
        {late.length ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-rose-900">
            <p className="font-semibold">Lewat tenggat ({late.length})</p>
            {late.slice(0, 3).map((l, i) => (
              <p key={i} data-late={row.unit_code}>
                • {l.name} — telat {l.days} hari
                {l.delay_label ? ` (${l.delay_label})` : " (penyebab belum dijelaskan)"}
              </p>
            ))}
          </div>
        ) : null}
        {row.overrides ? (
          <p className="flex items-center gap-1.5 text-rose-800">
            <ShieldAlert className="h-3 w-3 shrink-0" />
            <span>{row.overrides} gerbang mutu pernah diterobos (tercatat di jejak audit)</span>
          </p>
        ) : null}
        {row.status === "on_hold" ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-amber-900">
            Dihentikan sementara: {row.hold_note}
          </p>
        ) : null}
      </div>

      <div className="mt-2.5 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" aria-label={`Buka jadwal unit ${row.unit_code}`}
          data-testid={`${BUILD.row}-open`} data-open={row.unit_code}
          onClick={() => onOpen(row.unit_id)}>
          Buka jadwal & bukti
        </Button>
        {can?.configure && !row.items_done ? (
          <Button size="sm" variant="ghost"
            aria-label={`Hapus jadwal unit ${row.unit_code}`}
            data-testid={`${BUILD.row}-delete`} data-delete={row.unit_code}
            onClick={() => onDelete(row)}>
            <Trash2 className="mr-1 h-3.5 w-3.5" /> Hapus jadwal
          </Button>
        ) : null}
      </div>
    </div>
  );
}
