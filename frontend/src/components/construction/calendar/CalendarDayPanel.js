import React from "react";
import { ArrowUpRight, CalendarClock, HardHat, Users } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import RefLabel from "@/components/patterns/RefLabel";
import StatusPill from "@/components/patterns/StatusPill";
import { useReference } from "@/context/ReferenceContext";
import { ITEM_TONE } from "@/utils/buildUi";
import { CONFLICT_TONE, KIND_ORDER, KIND_TONE, longDate } from "@/utils/calendarUi";
import { CAL } from "@/constants/testIds";

/**
 * PANEL HARI — detail satu tanggal: siapa mengerjakan apa, mana yang kritis, dan bentrok
 * apa yang terjadi. Dari sini pengguna bisa langsung membuka pekerjaannya di Papan Mandor
 * atau membuka dialog GESER JADWAL (Fase 34) — kalender sendiri tidak pernah menulis tanggal.
 */
export default function CalendarDayPanel({
  date, day, events, conflicts, open, onOpenChange, canShift, onShift,
}) {
  const nav = useNavigate();
  const { labelOf } = useReference();
  const rows = events || [];
  const grouped = KIND_ORDER
    .map((k) => ({ kind: k, rows: rows.filter((e) => e.kind === k) }))
    .filter((g) => g.rows.length);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={CAL.dayPanel} side="right"
        className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="sticky top-0 z-10 bg-background pb-2">
          <SheetTitle className="flex flex-wrap items-center gap-2">
            <CalendarClock className="h-4 w-4 text-primary" />
            {longDate(date)}
            {day ? (
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                day.is_workday ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-rose-200 bg-rose-50 text-rose-800"}`}>
                {day.holiday || labelOf("calendar_day_kind", day.kind)}
              </span>
            ) : null}
          </SheetTitle>
          <SheetDescription>
            {rows.length
              ? `${rows.length} acara terjadwal pada tanggal ini.`
              : "Tidak ada acara pada tanggal ini."}
          </SheetDescription>
        </SheetHeader>

        {(conflicts || []).length ? (
          <div className="space-y-2">
            {conflicts.map((c, i) => (
              <div key={`${c.kind}-${i}`}
                className={`rounded-lg border p-2.5 text-xs ${CONFLICT_TONE[c.kind] || ""}`}>
                <p className="font-semibold">
                  <RefLabel group="calendar_conflict_kind" value={c.kind} />
                </p>
                <p className="mt-0.5">{c.detail}</p>
              </div>
            ))}
          </div>
        ) : null}

        {day && (day.load || []).length ? (
          <div data-testid={CAL.dayLoad} className="mt-3 rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold">
              <Users className="h-3.5 w-3.5" /> Beban per pelaksana hari ini
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {day.load.map((l) => (
                <span key={l.assigned_to}
                  className="rounded-full border bg-background px-2 py-0.5 text-[11px]">
                  {l.assigned_to} <b className="tabular-nums">{l.count}</b>
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-3 space-y-3">
          {!rows.length ? (
            <p data-testid={CAL.dayEmpty}
              className="rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground">
              Tidak ada tenggat, inspeksi, punch list, atau tugas pada tanggal ini.
              Gunakan panah bulan atau klik tanggal lain pada grid.
            </p>
          ) : null}

          {grouped.map((g) => (
            <div key={g.kind} className="rounded-xl border bg-card p-2.5 shadow-[var(--shadow-card)]">
              <p className="mb-1.5 inline-flex items-center gap-1.5 text-xs font-semibold">
                <span className={`rounded-full border px-2 py-0.5 ${KIND_TONE[g.kind] || ""}`}>
                  <RefLabel group="calendar_event_kind" value={g.kind} />
                </span>
                <span className="text-muted-foreground">{g.rows.length}</span>
              </p>
              <div className="space-y-1.5">
                {g.rows.map((e) => (
                  <div key={`${e.kind}-${e.id}`} data-testid={CAL.dayEvent}
                    data-kind={e.kind} data-event-id={e.id}
                    className="rounded-lg border bg-background p-2 text-xs">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium">
                          {e.unit_code ? (
                            <span className="font-mono text-primary">{e.unit_code} </span>
                          ) : null}
                          {e.title}
                        </p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          {e.assigned_to ? `${e.assigned_to} · ` : ""}
                          {e.project_name || ""}
                          {e.step_code ? ` · ${e.step_code}` : ""}
                          {e.late ? " · " : ""}
                          {e.late ? <b className="text-rose-700">telat</b> : null}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {e.critical ? (
                          <span className="rounded-full border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800">
                            kritis
                          </span>
                        ) : null}
                        {e.kind === "work_deadline" && e.status ? (
                          <StatusPill status={e.status} group="build_item_status"
                            tone={ITEM_TONE[e.status]} />
                        ) : null}
                        <Button size="sm" variant="ghost" data-testid={CAL.dayEventOpen}
                          aria-label={`Buka ${e.title}`}
                          onClick={() => nav(e.link || "/construction")}>
                          <ArrowUpRight className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {canShift ? (
          <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50 p-3">
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-900">
              <HardHat className="h-3.5 w-3.5" /> Perlu memindahkan tanggal?
            </p>
            <p className="mt-0.5 text-[11px] text-sky-900">
              Kalender tidak mengubah tanggal sendiri. Pemindahan dilakukan lewat dialog
              geser jadwal — wajib menyebut penyebab &amp; catatan, dan pekerjaan yang sudah
              diverifikasi tidak ikut bergeser (bukti terikat waktu).
            </p>
            <Button size="sm" className="mt-2" data-testid={CAL.dayShift} onClick={onShift}>
              Buka dialog geser jadwal
            </Button>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
