import React, { useState } from "react";
import { CalendarPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { PanelStateView } from "@/components/patterns/StateViews";
import AppointmentDialog from "@/components/sales/AppointmentDialog";
import AppointmentDetailSheet from "@/components/appointments/AppointmentDetailSheet";
import { ChevronRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import { LEADS } from "@/constants/testIds";

/**
 * LeadSurveyTab — daftar appointment/survei lead + penjadwalan baru.
 *
 * Fase 52: tab ini adalah panel yang dulu MEMATIKAN seluruh halaman profil lead. Ketika
 * `GET /api/appointments` menjawab 403 (mis. karena izin peran dicabut admin di layar Hak
 * Akses), tab ini sekarang bercerita sendiri lewat `PanelStateView` dan halaman tetap hidup.
 *
 * Tombol "Jadwalkan Survey" mengikuti IZIN NYATA (`appointments:create`). Sejak Fase 52
 * Keuangan boleh MEMBACA jadwal survei tetapi tidak menjadwalkan — tanpa penjagaan ini
 * tombolnya ada tetapi selalu 403 (tombol mati, cacat yang sama kelasnya).
 */
export default function LeadSurveyTab({
  leadId, appointments = [], panel = null, onRetry = null, onChanged,
}) {
  const { can } = useAuth();
  const mayCreate = can("appointments", "create");
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);

  const blocked = (
    <PanelStateView panel={panel} subject="Jadwal survei & janji temu" onRetry={onRetry}
      whoMay={"Penjadwalan survei dipegang tim Sales & Marketing Admin; Keuangan boleh "
        + "membacanya. Bila Anda memang perlu melihat jadwal ini, mintakan hak aksesnya ke "
        + "admin sistem."} />
  );
  if (panel && !panel.ok) return <div className="space-y-3">{blocked}</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Jadwal survei & janji temu lead ini.
        </p>
        {mayCreate ? (
          <Button data-testid={LEADS.appointmentBtn} size="sm" onClick={() => setOpen(true)}>
            <CalendarPlus className="mr-1.5 h-4 w-4" /> Jadwalkan Survey
          </Button>
        ) : null}
      </div>
      {!mayCreate ? (
        <p data-testid="lead-survey-readonly"
          className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          Peran Anda boleh MEMBACA jadwal survei, tetapi penjadwalannya dipegang tim Sales /
          Marketing Admin — karena itu tombol “Jadwalkan Survey” tidak ditampilkan (bukan
          tombol mati).
        </p>
      ) : null}
      {appointments.length ? (
        <div className="space-y-2">
          {appointments.map((ap) => (
            <button type="button" key={ap.id} data-testid="lead-appointment-row" data-appointment={ap.id}
              aria-label={`Buka detail survei ${ap.title}`} onClick={() => setDetail(ap)}
              className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border bg-card p-3 text-left shadow-[var(--shadow-card)] transition-colors hover:border-primary/40 hover:bg-accent/40">
              <div>
                <p className="text-sm font-medium">{ap.title}</p>
                <p className="text-xs text-muted-foreground">
                  {formatDateTimeWIB(ap.scheduled_at)} · {ap.location || "-"} · klik untuk detail, ubah status & hasil
                </p>
              </div>
              <span className="flex items-center gap-2">
                <StatusPill status={ap.status} group="appointment_status"
                  tone={ap.status === "scheduled" ? "active" : ap.status} />
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </span>
            </button>
          ))}
        </div>
      ) : (
        <EmptyState icon={CalendarPlus} title="Belum ada survei terjadwal"
          description={mayCreate
            ? "Jadwalkan survei lokasi agar lead bisa naik ke tahap berikutnya."
            : "Belum ada survei yang dijadwalkan tim Sales untuk lead ini."}
          actionLabel={mayCreate ? "Jadwalkan Survey" : ""}
          onAction={mayCreate ? () => setOpen(true) : null} />
      )}
      {mayCreate ? (
        <AppointmentDialog leadId={leadId} open={open} onOpenChange={setOpen}
          onDone={onChanged} />
      ) : null}
      <AppointmentDetailSheet appointment={detail} open={!!detail}
        onOpenChange={(v) => !v && setDetail(null)} onChanged={() => { setDetail(null); onChanged && onChanged(); }} />
    </div>
  );
}
