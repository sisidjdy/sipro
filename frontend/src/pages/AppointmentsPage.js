import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, CalendarClock, CalendarPlus, MapPin, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import EmptyState from "@/components/patterns/EmptyState";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import AppointmentDetailSheet from "@/components/appointments/AppointmentDetailSheet";
import AgendaFormDialog from "@/components/appointments/AgendaFormDialog";
import AgendaTable from "@/components/appointments/AgendaTable";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { APPTS } from "@/constants/testIds";

const pad = (n) => String(n).padStart(2, "0");
const localDayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseDayKey = (k) => { const [y, m, d] = k.split("-").map(Number); return new Date(y, m - 1, d); };
const wibDayKey = (iso) => new Intl.DateTimeFormat("en-CA",
  { timeZone: "Asia/Jakarta", year: "numeric", month: "2-digit", day: "2-digit" })
  .format(new Date(iso));
const timeWIB = (iso) => new Intl.DateTimeFormat("id-ID",
  { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta" }).format(new Date(iso));

/** Rentang waktu tabel → parameter server (agenda mendatang vs riwayat). */
function rangeParams(range) {
  const now = new Date();
  const plus = (days) => new Date(now.getTime() + days * 86400000).toISOString();
  if (range === "next7") return { date_from: now.toISOString(), date_to: plus(7) };
  if (range === "next30") return { date_from: now.toISOString(), date_to: plus(30) };
  if (range === "past") return { date_to: now.toISOString(), sort: "scheduled_at", direction: "desc" };
  return {};
}

/**
 * AppointmentsPage — Agenda & Survey (Fase 63).
 *
 * Dulu halaman ini hanya kalender + daftar satu hari, sehingga dua pertiga layar kosong dan
 * agenda minggu depan hanya bisa ditemukan dengan mengklik tanggal satu per satu. Sekarang:
 * kalender (penanda hari beragenda) + agenda hari terpilih + TABEL seluruh agenda dengan
 * cari, filter, urut & paginasi yang dieksekusi server. Agenda juga bisa DIBUAT dari sini,
 * termasuk agenda non-penjualan (rapat internal, kunjungan proyek, rapat vendor).
 */
export default function AppointmentsPage() {
  const { can } = useAuth();
  const canManage = can("appointments", "create");

  const { query, setQuery, reset, activeCount } = useListQuery({
    filters: { status: [], type: [], kind: [], range: "next30" },
    sort: "scheduled_at", direction: "asc", limit: 25,
  });

  const [data, setData] = useState(null);
  const [monthRows, setMonthRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(new Date());
  const [detail, setDetail] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const { range, ...rest } = query;
    const params = {
      ...rest,
      status: rest.status?.length ? rest.status.join(",") : undefined,
      type: rest.type?.length ? rest.type.join(",") : undefined,
      kind: rest.kind?.length ? rest.kind.join(",") : undefined,
      q: rest.q || undefined,
      ...rangeParams(range),
    };
    try {
      const res = await api.get("/appointments", { params });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat agenda.");
    } finally { setLoading(false); }
  }, [query]);

  // Penanda kalender & agenda harian selalu memakai SELURUH agenda (tidak ikut filter tabel):
  // kalender yang menyembunyikan hari beragenda karena filter tabel adalah kalender yang
  // berbohong.
  const loadMonth = useCallback(async () => {
    try {
      const res = await api.get("/appointments", { params: { limit: 500 } });
      setMonthRows(res.data.data || []);
    } catch { setMonthRows([]); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadMonth(); }, [loadMonth]);

  const byDay = useMemo(() => {
    const map = {};
    monthRows.forEach((a) => { (map[wibDayKey(a.scheduled_at)] ||= []).push(a); });
    return map;
  }, [monthRows]);
  const daysWithAppts = useMemo(() => Object.keys(byDay).map(parseDayKey), [byDay]);
  const agenda = useMemo(() => [...(byDay[localDayKey(selected)] || [])]
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at)), [byDay, selected]);

  const refresh = () => { load(); loadMonth(); setDetail(null); };
  const openCreate = () => { setEditing(null); setFormOpen(true); };
  const openEdit = (row) => { setEditing(row); setFormOpen(true); };

  return (
    <div data-testid={APPTS.page} className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-primary" /> Agenda &amp; Survey
          </h1>
          <p className="page-desc">
            Survei pembeli, rapat internal, kunjungan proyek, dan rapat vendor — satu
            kalender kerja untuk semuanya.
          </p>
        </div>
        {canManage ? (
          <Button data-testid={APPTS.createBtn} size="sm" onClick={openCreate}>
            <CalendarPlus className="mr-1.5 h-4 w-4" /> Buat Agenda
          </Button>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-[auto,1fr]">
        <div data-testid={APPTS.calendar} className="rounded-xl border bg-card p-2 shadow-sm">
          <Calendar mode="single" selected={selected} onSelect={(d) => d && setSelected(d)}
            modifiers={{ hasAppt: daysWithAppts }}
            modifiersClassNames={{
              hasAppt: "relative font-semibold text-primary after:absolute after:bottom-1 after:left-1/2 after:h-1 after:w-1 after:-translate-x-1/2 after:rounded-full after:bg-primary",
            }} />
          <div className="flex items-center gap-2 border-t px-3 py-2 text-xs text-muted-foreground">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" /> Ada agenda
          </div>
        </div>

        <div data-testid={APPTS.agenda} className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 font-heading text-lg font-semibold">
              <CalendarClock className="h-4 w-4 text-primary" />
              Agenda · {formatDateWIB(selected.toISOString())}
              <span className="rounded-full bg-secondary px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
                {agenda.length}
              </span>
            </h2>
            {canManage ? (
              <Button size="sm" variant="outline" data-testid={APPTS.dayCreateBtn}
                onClick={openCreate}>
                <CalendarPlus className="mr-1.5 h-3.5 w-3.5" /> Tambah di tanggal ini
              </Button>
            ) : null}
          </div>
          {!agenda.length ? (
            <EmptyState icon={CalendarDays} title="Tidak ada agenda pada tanggal ini"
              description="Pilih tanggal lain pada kalender, atau buat agenda baru — termasuk rapat internal dan kunjungan proyek."
              actionLabel={canManage ? "Buat Agenda" : ""}
              onAction={canManage ? openCreate : undefined} />
          ) : (
            <div className="space-y-2">
              {agenda.map((a) => (
                <button key={a.id} data-testid={APPTS.agendaItem} onClick={() => setDetail(a)}
                  className={cn("flex w-full items-center justify-between gap-3 rounded-xl border bg-card p-3 text-left",
                    "transition-colors hover:border-primary hover:bg-secondary")}>
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex flex-col items-center rounded-lg bg-primary/10 px-2.5 py-1.5">
                      <span className="text-sm font-semibold tabular-nums text-primary">
                        {timeWIB(a.scheduled_at)}
                      </span>
                      <span className="text-[10px] uppercase text-muted-foreground">
                        <RefLabel group="appointment_type" value={a.type} />
                      </span>
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium">{a.title}</p>
                      <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3 w-3" /> {a.location || "-"}
                        </span>
                        <span>{a.lead_id ? (a.lead_name || "lead") : "Agenda internal"}</span>
                        {(a.participants || []).length ? (
                          <span className="flex items-center gap-1">
                            <Users className="h-3 w-3" /> {(a.participants || []).length}
                          </span>
                        ) : null}
                      </p>
                    </div>
                  </div>
                  <StatusPill status={a.status} group="appointment_status" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <AgendaTable data={data} loading={loading} error={error} query={query}
        setQuery={setQuery} reset={reset} activeCount={activeCount} onRefresh={load}
        canManage={canManage} onEdit={openEdit} onRowClick={(a) => setDetail(a)} />

      <AppointmentDetailSheet appointment={detail} open={!!detail}
        onOpenChange={(v) => !v && setDetail(null)} onChanged={refresh} />
      <AgendaFormDialog open={formOpen} onOpenChange={setFormOpen} editing={editing}
        defaultDate={selected?.toISOString()} onDone={refresh} />
    </div>
  );
}
