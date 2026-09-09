import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronUp, HardHat, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import MetricCard from "@/components/patterns/MetricCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import { P92 } from "@/constants/testIds";

/** Kartu KPI papan unit yang bisa diklik → popup daftar unit (Fase 92). */
function Kpi({ id, onOpen, label, ...card }) {
  return (
    <button type="button" data-testid={`${P92.buildMetric}-${id}`} onClick={() => onOpen(id, label)}
      className="group rounded-xl text-left outline-none transition-transform focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99]">
      <MetricCard label={label} {...card} className="h-full ring-1 ring-transparent group-hover:ring-primary/50" />
    </button>
  );
}
import StatusPill from "@/components/patterns/StatusPill";
import BuildMonitorPanel from "@/components/construction/BuildMonitorPanel";
import ProjectPhasesPanel from "@/components/construction/ProjectPhasesPanel";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { shortDate } from "@/utils/buildUi";
import {
  deviationClass, deviationText, pctText, READINESS_TONE, reasonSummary,
} from "@/utils/permitUi";
import { UNIT_BOARD } from "@/constants/testIds";

/**
 * PAPAN UNIT (Fase 46, dok 29 §1 & §4) — satu baris per RUMAH.
 *
 * Cacat yang ditutup: papan lama (`build_monitor.board()`) berbaris per JADWAL, jadi unit
 * yang belum dijadwalkan HILANG dari layar — padahal itu yang paling perlu ditindak. Papan
 * ini menampilkan semua unit dan MENGAKU saat datanya belum ada: unit tanpa jadwal ditulis
 * "belum ada data", bukan 0% (0% berarti sudah dijadwalkan tetapi belum dikerjakan — dua
 * keadaan itu butuh tindakan berbeda).
 */
export default function UnitBoardTab({ projectId: fixedProject = null }) {
  const navigate = useNavigate();
  const { options, labelOf } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: {
      construction_status: [], readiness: [], project_id: [], late_only: "",
      unscheduled_only: "",
    },
    sort: "code", direction: "asc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [extras, setExtras] = useState(false);

  const params = useMemo(() => {
    const out = { ...apiParams };
    if (fixedProject) out.project_id = fixedProject;
    else if (Array.isArray(query.project_id) && query.project_id.length === 1) {
      out.project_id = query.project_id[0];
    }
    delete out.project_id_multi;
    return out;
  }, [apiParams, query.project_id, fixedProject]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/build/board/units", { params });
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat papan unit.");
    } finally { setLoading(false); }
  }, [params]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/projects").then((r) => setProjects((r.data.data || [])
      .map((p) => ({ value: p.id, label: p.name })))).catch(() => setProjects([]));
  }, []);

  const s = data?.summary;
  const [drill, setDrill] = useState(null);
  const openDrill = (id, label) => setDrill({ key: `board:${id}`, label, params: params.project_id ? { project_id: params.project_id } : {} });
  const mode = data?.mode || {};
  const columns = useMemo(() => [
    {
      key: "code", header: "Unit", sortable: true,
      render: (r) => (
        <div>
          <p className="font-medium text-primary">{r.code}</p>
          <p className="text-xs text-muted-foreground">
            {r.cluster_code || "-"} / {r.block || "-"} · {r.type || "-"}
          </p>
        </div>
      ),
      exportValue: (r) => r.code,
    },
    {
      key: "construction_status", header: "Status bangun", sortable: true,
      render: (r) => (
        <div className="space-y-1">
          <StatusPill status={r.construction_status} group="construction_status" />
          {r.schedule_status ? (
            <p className="text-[11px] text-muted-foreground">
              jadwal: {labelOf("build_schedule_status", r.schedule_status)}
            </p>
          ) : null}
        </div>
      ),
      exportValue: (r) => r.construction_status,
    },
    {
      key: "actual_progress", header: "Realisasi", sortable: true, align: "right",
      render: (r) => (r.actual_progress === null
        ? <span data-testid={UNIT_BOARD.planEmpty}
            className="text-xs text-muted-foreground">belum ada data</span>
        : <span className="tabular-nums font-medium">{r.actual_progress}%</span>),
      exportValue: (r) => r.actual_progress,
    },
    {
      key: "planned_progress", header: "Rencana", sortable: true, align: "right",
      render: (r) => (r.planned_progress === null
        ? <span data-testid={UNIT_BOARD.planEmpty}
            className="text-xs text-muted-foreground">belum ada data</span>
        : <span className="tabular-nums">{pctText(r.planned_progress)}</span>),
      exportValue: (r) => r.planned_progress,
    },
    {
      key: "deviation", header: "Deviasi", sortable: true, align: "right",
      render: (r) => (
        <div className={`text-right ${deviationClass(r.deviation)}`}>
          <p className="tabular-nums text-sm font-semibold">{deviationText(r.deviation)}</p>
          {r.deviation_days ? (
            <p className="text-[11px]">setara {r.deviation_days} hari</p>
          ) : null}
        </div>
      ),
      exportValue: (r) => r.deviation,
    },
    {
      key: "days_late", header: "Umur telat", sortable: true, align: "right",
      render: (r) => (r.days_late === null
        ? <span className="text-xs text-muted-foreground">belum ada data</span>
        : r.days_late > 0
          ? <span className="font-semibold text-rose-700 tabular-nums">{r.days_late} hari</span>
          : <span className="text-xs text-emerald-700">tepat waktu</span>),
      exportValue: (r) => r.days_late,
    },
    {
      key: "active_step", header: "Langkah aktif & tenggat",
      render: (r) => (r.active_step ? (
        <div>
          <p className="line-clamp-1 text-sm">{r.active_step.name}</p>
          <p className="text-[11px] text-muted-foreground">
            {labelOf("build_item_status", r.active_step.status)} · tenggat{" "}
            {shortDate(r.active_step.planned_finish)}
          </p>
        </div>
      ) : (
        <span className="text-xs text-muted-foreground">
          {r.schedule_id ? "tidak ada langkah terbuka" : "belum dijadwalkan"}
        </span>
      )),
      exportValue: (r) => r.active_step?.name || "",
    },
    {
      key: "pic", header: "PIC",
      render: (r) => (r.pic
        ? <span className="text-xs">{r.pic}</span>
        : <span className="text-xs text-muted-foreground">belum ada PIC</span>),
    },
    {
      key: "last_evidence", header: "Bukti terakhir",
      render: (r) => (r.last_evidence ? (
        <div>
          <p className="text-xs">{shortDate(r.last_evidence.at)}</p>
          <p className="text-[11px] text-muted-foreground">
            {r.last_evidence.kind === "verified" ? "diverifikasi" : "diajukan"} ·{" "}
            {r.last_evidence.photos} foto
          </p>
        </div>
      ) : <span className="text-xs text-muted-foreground">belum ada bukti</span>),
      exportValue: (r) => r.last_evidence?.at || "",
    },
    {
      key: "readiness", header: "Kesiapan mulai", sortable: true,
      render: (r) => (
        <div className="space-y-1" data-testid={UNIT_BOARD.readiness}
          data-state={r.readiness}>
          <StatusPill status={r.readiness} group="build_readiness_state"
            tone={READINESS_TONE[r.readiness]} />
          {r.readiness_codes?.length ? (
            <p className="text-[11px] text-muted-foreground">
              {reasonSummary(r.readiness_codes, labelOf)}
            </p>
          ) : null}
        </div>
      ),
      exportValue: (r) => r.readiness,
    },
  ], [labelOf]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "construction_status", label: "Status bangun", type: "multiselect",
        options: options("construction_status") },
      { key: "readiness", label: "Kesiapan mulai", type: "multiselect",
        options: options("build_readiness_state") },
      ...(fixedProject ? [] : [{ key: "project_id", label: "Proyek", type: "multiselect",
        options: projects }]),
      { key: "late_only", label: "Hanya yang telat", type: "select",
        options: [{ value: "true", label: "Ya" }] },
      { key: "unscheduled_only", label: "Hanya belum dijadwalkan", type: "select",
        options: [{ value: "true", label: "Ya" }] },
    ]} />
  );

  return (
    <div data-testid={UNIT_BOARD.panel} className="space-y-4">
      <div data-testid={UNIT_BOARD.modeBanner}
        className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
        <p className="flex items-center gap-1.5 font-semibold">
          <ShieldAlert className="h-3.5 w-3.5" /> Kebijakan mulai bangun:{" "}
          {mode.require_dp_before_start
            ? "DP wajib terbayar (memblokir)"
            : "peringatan saja (tidak memblokir)"}
          {mode.block_build_without?.length
            ? ` · izin wajib: ${mode.block_build_without.join(", ")}`
            : " · tidak ada izin yang memblokir"}
        </p>
        <p className="mt-1">
          Unit yang belum dijadwalkan ditulis <b>“belum ada data”</b>, bukan 0% — 0% berarti
          sudah dijadwalkan tetapi belum ada pekerjaan terverifikasi. Ubah kebijakan di
          Pusat Konfigurasi → Konstruksi &amp; Izin.
        </p>
      </div>

      {s ? (
        <div data-testid={UNIT_BOARD.summary}
          className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Kpi id="all" onOpen={openDrill} label="Unit" value={s.units_total} tone="primary" />
          <Kpi id="unscheduled" onOpen={openDrill} label="Sudah dijadwalkan" value={s.scheduled} tone="indigo"
            hint={`${s.unscheduled} belum dijadwalkan`} />
          <Kpi id="running" onOpen={openDrill} label="Sedang berjalan" value={s.running} tone="sky" />
          <Kpi id="late" onOpen={openDrill} label="Telat" value={s.late} tone="rose"
            hint={`${s.awaiting_verification} menunggu verifikasi`} />
          <Kpi id="ready" onOpen={openDrill} label="Siap dimulai" value={s.ready_to_start} tone="emerald"
            hint={`${s.warning_to_start} perlu konfirmasi`} />
          <Kpi id="progress" onOpen={openDrill} label="Rata-rata progres"
            value={s.avg_progress === null ? "belum ada data" : `${s.avg_progress}%`}
            tone="amber"
            hint={s.avg_planned === null ? "rencana belum ada"
              : `rencana ${s.avg_planned}% · hanya unit terjadwal`} />
        </div>
      ) : null}
      <DrilldownDialog target={drill} onOpenChange={(o) => { if (!o) setDrill(null); }} />

      <DataTable testId={UNIT_BOARD.table} testIds={{ row: UNIT_BOARD.row }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="unit" exportName="papan-unit" onRefresh={load}
        searchPlaceholder="Cari kode unit / tipe / blok / pembeli…"
        onRowClick={(r) => navigate(`/units/${r.unit_id}?tab=build`)}
        emptyTitle={activeCount || query.q ? "Tidak ada unit yang cocok" : "Belum ada unit"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Buat cluster → blok → unit dari halaman proyek."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : ""}
        emptyAction={() => reset()} bulkActions={[]} />

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <HardHat className="h-3.5 w-3.5" /> Klik baris untuk membuka{" "}
        <b>Unit 360 → tab Pembangunan</b> (kurva-S, langkah + bukti, mutu, izin, aksi kerja).
      </p>

      <div className="rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <button type="button" data-testid={UNIT_BOARD.extrasToggle}
          onClick={() => setExtras((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium">
          Pekerjaan kawasan &amp; monitoring jadwal (bukan per unit)
          {extras ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
        {extras ? (
          <div data-testid={UNIT_BOARD.extras} className="space-y-5 border-t p-4">
            <p className="text-xs text-muted-foreground">
              Jalan, drainase, gerbang, dan pantauan jadwal lintas unit tetap ada di sini
              supaya tidak ada fitur yang hilang saat menu konstruksi dilebur (dok 29 §6).
            </p>
            <ProjectPhasesPanel projectId={fixedProject
              || (Array.isArray(query.project_id) ? query.project_id[0] : null)} />
            <BuildMonitorPanel projectId={fixedProject
              || (Array.isArray(query.project_id) ? query.project_id[0] : null)} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
