import React from "react";
import { CalendarClock, ChevronLeft, ChevronRight, RefreshCw, Settings2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ProjectSelect from "@/components/construction/ProjectSelect";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useReference } from "@/context/ReferenceContext";
import { KIND_DOT, KIND_ORDER, monthLabel } from "@/utils/calendarUi";
import { CAL } from "@/constants/testIds";

/**
 * Toolbar Kalender Jadwal: cakupan (satu proyek / semua proyek), bulan, filter jenis acara,
 * filter pelaksana, dan pintu ke pengaturan kalender kerja.
 *
 * Semua daftar pilihan enum diambil dari SSOT `/api/reference` (cakupan & jenis acara),
 * sehingga tidak ada kamus label yang diketik ulang di frontend.
 */
export default function CalendarToolbar({
  scope, onScope, projectId, onProject, month, months, onMonth, onStep, onToday,
  kinds, onToggleKind, assignees, assignee, onAssignee, onRefresh, loading,
  can, onOpenSettings, onOpenShift,
}) {
  const { options } = useReference();
  const kindOptions = options("calendar_event_kind");
  const ordered = KIND_ORDER
    .map((k) => kindOptions.find((o) => o.value === k))
    .filter(Boolean);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <ReferenceSelect group="calendar_scope" value={scope} onChange={onScope}
          testId={CAL.scope} className="w-full sm:w-56" placeholder="Cakupan kalender" />
        {scope === "project" ? (
          <ProjectSelect value={projectId} onChange={onProject} testId={CAL.project} />
        ) : (
          <p className="rounded-lg border bg-secondary px-3 py-2 text-xs text-muted-foreground">
            Portofolio: semua proyek yang boleh Anda lihat
          </p>
        )}

        <div className="ml-auto flex items-center gap-1.5">
          <Button variant="outline" size="icon" data-testid={CAL.prev}
            aria-label="Bulan sebelumnya" onClick={() => onStep(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Select value={month || ""} onValueChange={onMonth}>
            <SelectTrigger data-testid={CAL.month} className="w-40">
              <SelectValue placeholder="Pilih bulan" />
            </SelectTrigger>
            <SelectContent>
              {(months || []).map((m) => (
                <SelectItem key={m} value={m}>{monthLabel(m)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" data-testid={CAL.next}
            aria-label="Bulan berikutnya" onClick={() => onStep(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="secondary" size="sm" data-testid={CAL.today} onClick={onToday}>
            <CalendarClock className="mr-1.5 h-3.5 w-3.5" /> Bulan ini
          </Button>
          <Button variant="outline" size="icon" data-testid={CAL.refresh}
            aria-label="Muat ulang kalender" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Tampilkan:</span>
        {ordered.map((o) => {
          const on = kinds.includes(o.value);
          return (
            <button key={o.value} type="button" data-testid={CAL.kind} data-kind={o.value}
              aria-pressed={on} aria-label={`Saring acara ${o.label}`}
              onClick={() => onToggleKind(o.value)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1
                text-[11px] font-medium transition ${on
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-card text-muted-foreground hover:bg-secondary"}`}>
              <span className={`h-2 w-2 rounded-full ${KIND_DOT[o.value] || "bg-slate-400"}`} />
              {o.label}
            </button>
          );
        })}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            <Select value={assignee || "__all__"}
              onValueChange={(v) => onAssignee(v === "__all__" ? "" : v)}>
              <SelectTrigger data-testid={CAL.assignee} className="w-52">
                <SelectValue placeholder="Semua pelaksana" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua pelaksana</SelectItem>
                {(assignees || []).map((a) => (
                  <SelectItem key={a} value={a}>{a}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {can?.shift ? (
            <Button variant="outline" size="sm" data-testid={CAL.shiftBtn} onClick={onOpenShift}>
              Geser jadwal
            </Button>
          ) : null}
          {can?.configure ? (
            <Button size="sm" data-testid={CAL.settingsBtn} onClick={onOpenSettings}>
              <Settings2 className="mr-1.5 h-3.5 w-3.5" /> Kalender kerja
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
