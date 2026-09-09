import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, MapPin, User2, StickyNote } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import SurveyPanel from "@/components/appointments/SurveyPanel";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { APPTS } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";
import { useReference } from "@/context/ReferenceContext";


function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-2.5 py-1.5 text-sm">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="font-medium">{value || "-"}</p>
      </div>
    </div>
  );
}

export default function AppointmentDetailSheet({ appointment, open, onOpenChange, onChanged }) {
  const [status, setStatus] = useState("scheduled");
  const [busy, setBusy] = useState(false);
  const { options } = useReference();

  useEffect(() => { if (appointment) setStatus(appointment.status || "scheduled"); }, [appointment]);

  const applyStatus = async () => {
    if (!appointment || status === appointment.status) return;
    setBusy(true);
    try {
      await api.post(`/appointments/${appointment.id}/status`, { status });
      toast.success("Status janji temu diperbarui.");
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui status."); }
    finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={APPTS.detail} className="w-full overflow-y-auto sm:max-w-lg">
        {!appointment ? (
          <>
            <SheetHeader className="sr-only"><SheetTitle>Detail appointment</SheetTitle></SheetHeader>
            <p className="mt-6 text-sm text-muted-foreground">Memuat…</p>
          </>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="font-heading">{appointment.title}</SheetTitle>
              <SheetDescription>
                {appointment.lead_id
                  ? `Janji temu & survey untuk ${appointment.lead_name || "lead"}.`
                  : "Agenda internal (tanpa lead) — rapat, kunjungan proyek, atau rapat vendor."}
              </SheetDescription>
            </SheetHeader>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <StatusPill status={appointment.status} group="appointment_status" />
              <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
                <RefLabel group="appointment_type" value={appointment.type} />
              </span>
            </div>

            <div className="mt-4 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <InfoRow icon={CalendarClock} label="Waktu" value={formatDateTimeWIB(appointment.scheduled_at)} />
              <InfoRow icon={MapPin} label="Lokasi" value={appointment.location} />
              <InfoRow icon={User2} label="Sales" value={appointment.assigned_to} />
              {appointment.notes ? <InfoRow icon={StickyNote} label="Catatan" value={appointment.notes} /> : null}
            </div>

            {/* Status control */}
            <div className="mt-4 flex items-end gap-2">
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs">Ubah Status</Label>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger data-testid={APPTS.statusSelect}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {options("appointment_status").map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Button data-testid={APPTS.statusApplyBtn} size="sm" onClick={applyStatus}
                disabled={busy || status === appointment.status}>Terapkan</Button>
            </div>

            {/* Survey — hanya untuk agenda yang MENYEBUT LEAD. Agenda internal (rapat,
                kunjungan proyek) tidak punya pembeli yang disurvei, jadi menawarkan
                "Mulai Survey" di sana hanya menjebak pemakai. */}
            {appointment.lead_id ? (
              <div className="mt-5">
                <SurveyPanel appointment={appointment} onChanged={onChanged} />
              </div>
            ) : (
              <div className="mt-5 space-y-1 rounded-xl border bg-secondary/40 p-3 text-[12px]">
                <p className="font-medium">Peserta</p>
                <p className="text-muted-foreground">
                  {(appointment.participants || []).join(", ") || "Belum ada peserta diundang."}
                </p>
              </div>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
