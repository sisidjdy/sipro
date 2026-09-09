import React, { useMemo } from "react";
import { CalendarClock, MapPin, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import { useReference } from "@/context/ReferenceContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import { APPTS, DT } from "@/constants/testIds";

const RANGES = [
  { value: "next7", label: "7 hari ke depan" },
  { value: "next30", label: "30 hari ke depan" },
  { value: "past", label: "Riwayat (sudah lewat)" },
  { value: "all", label: "Semua waktu" },
];

/**
 * AgendaTable — daftar agenda kerja dengan cari, filter, urut & paginasi SERVER (Fase 63).
 *
 * Sebelumnya halaman Agenda hanya menampilkan agenda pada SATU tanggal yang diklik di
 * kalender: "rapat minggu depan" hanya bisa ditemukan dengan menebak tanggalnya, dan
 * separuh layar tinggal kosong. Sort & pencarian dieksekusi di database supaya urutannya
 * jujur pada seluruh hasil, bukan pada halaman yang kebetulan terlihat.
 */
export default function AgendaTable({ data, loading, error, query, setQuery, reset,
  activeCount, onRefresh, onRowClick, onEdit, canManage }) {
  const { options, labelOf } = useReference();

  const columns = useMemo(() => [
    {
      key: "scheduled_at", header: "Waktu (WIB)", sortable: true, width: "20%",
      render: (a) => (
        <div className="min-w-0">
          <p className="font-medium tabular-nums">{formatDateTimeWIB(a.scheduled_at)}</p>
          <p className="text-xs text-muted-foreground">
            {labelOf("appointment_type", a.type)}
          </p>
        </div>
      ),
      exportValue: (a) => a.scheduled_at,
    },
    {
      key: "title", header: "Agenda", sortable: true, width: "26%",
      render: (a) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{a.title}</p>
          <p className="truncate text-xs text-muted-foreground">
            {a.lead_id ? (a.lead_name || "lead") : "Agenda internal"}
          </p>
        </div>
      ),
    },
    {
      key: "kind", header: "Golongan", sortable: true,
      render: (a) => (
        <span className="text-xs">
          {labelOf("agenda_kind", a.kind || (a.lead_id ? "sales" : "internal"))}
        </span>
      ),
    },
    {
      key: "location", header: "Lokasi",
      render: (a) => (
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin className="h-3 w-3 shrink-0" /> {a.location || "-"}
        </span>
      ),
    },
    {
      key: "participants", header: "Peserta", align: "right",
      render: (a) => (
        <span className="text-xs tabular-nums text-muted-foreground">
          {(a.participants || []).length || "—"}
        </span>
      ),
      exportValue: (a) => (a.participants || []).join("; "),
    },
    {
      key: "assigned_to", header: "PIC", sortable: true,
      render: (a) => <span className="text-xs">{a.assigned_to || "-"}</span>,
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (a) => <StatusPill status={a.status} group="appointment_status" />,
    },
    {
      key: "aksi", header: "", align: "right", sticky: true,
      render: (a) => (canManage && !["done", "cancelled"].includes(a.status) ? (
        <Button size="icon" variant="ghost" data-testid={APPTS.editBtn}
          aria-label={`Ubah agenda ${a.title}`}
          onClick={(e) => { e.stopPropagation(); onEdit(a); }}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ) : null),
      exportValue: () => "",
    },
  ], [labelOf, canManage, onEdit]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "range", label: "Rentang", type: "select", options: RANGES },
      { key: "kind", label: "Golongan", type: "multiselect", options: options("agenda_kind") },
      { key: "type", label: "Jenis", type: "multiselect",
        options: options("appointment_type") },
      { key: "status", label: "Status", type: "multiselect",
        options: options("appointment_status") },
    ]} />
  );

  return (
    <DataTable testId={APPTS.table}
      testIds={{ row: APPTS.tableRow, search: APPTS.tableSearch, pagination: DT.pagination }}
      columns={columns} rows={data?.data || []} total={data?.total || 0}
      query={query} onQueryChange={setQuery} loading={loading} error={error}
      filters={filters} label="agenda" exportName="agenda" onRefresh={onRefresh}
      onRowClick={onRowClick}
      searchPlaceholder="Cari judul / lead / lokasi / catatan…"
      emptyTitle={activeCount || query.q ? "Tidak ada agenda yang cocok" : "Belum ada agenda"}
      emptyDescription={activeCount || query.q
        ? "Longgarkan filter, atau ubah rentang waktunya."
        : "Buat agenda rapat, kunjungan proyek, atau survei pembeli."}
      emptyActionLabel={activeCount || query.q ? "Reset filter" : ""}
      emptyAction={activeCount || query.q ? () => reset() : null}
      footer={(
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <CalendarClock className="h-3 w-3" />
          Agenda yang sudah selesai/dibatalkan tidak bisa diubah — buat agenda baru bila
          jadwalnya diulang.
        </p>
      )} />
  );
}
