import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { UserPlus, Zap, MessageSquarePlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import AgingCell from "@/components/patterns/AgingCell";
import StatusPill from "@/components/patterns/StatusPill";
import AssignLeadsDialog from "@/components/leads/AssignLeadsDialog";
import LeadKpiStrip from "@/components/leads/LeadKpiStrip";
import AddLeadDialog from "@/components/sales/AddLeadDialog";
import SimulateLeadDialog from "@/components/sales/SimulateLeadDialog";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { fromNow } from "@/utils/formatters";
import { downloadCsv } from "@/utils/tableCsv";
import { slaFilter } from "@/utils/agingFilter";
import api from "@/services/apiClient";
import { cn } from "@/lib/utils";
import { LEADS, DT, P94 } from "@/constants/testIds";

/**
 * LeadsPage — Pipeline Lead sebagai TABEL PRO (US-40-1).
 *
 * Yang berubah di Fase 40 dan mengapa:
 *   * cari + filter multi (tahap/sumber/skor/PIC/tanggal) + sort dieksekusi SERVER, jadi
 *     jujur pada data terpaginasi (dulu urutan hanya berlaku pada halaman yang terlihat);
 *   * seluruh filter hidup di URL sehingga KPI beranda bisa menaut ke daftar terfilter dan
 *     tautannya bisa dibagikan;
 *   * klik baris membuka HALAMAN `/leads/:id` (dulu drawer yang menyembunyikan checklist
 *     dokumen di dasar gulungan);
 *   * ada kolom UMUR (total & tahap) — inti dari “lead mana yang harus dikerjakan dulu”.
 */
export default function LeadsPage() {
  const navigate = useNavigate();
  const { options, labelOf } = useReference();
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // Kolom & aksi PIC (menugaskan lead ke orang lain) = izin `leads:assign`.
  const isManager = can("leads", "assign");

  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: {
      stage: [], source: [], score_band: [], assigned_to: [],
      created_from: "", created_to: "", sla: "", partner_id: "",
    },
    sort: "created_at", direction: "desc", limit: 25,
  });

  const [data, setData] = useState(null);
  const [owners, setOwners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [simOpen, setSimOpen] = useState(false);
  const [assignFor, setAssignFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/leads", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat lead.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/leads/owners").then((r) => setOwners(r.data.data || [])).catch(() => setOwners([]));
  }, []);

  const counts = data?.counts || {};
  const stageOptions = useMemo(() => options("lead_stage")
    .map((s) => ({ ...s, hint: counts[s.value] ?? 0 })), [options, counts]);

  const toggleStage = (value) => {
    const cur = query.stage || [];
    setQuery({ stage: cur.includes(value) ? cur.filter((s) => s !== value) : [value] });
  };

  const columns = useMemo(() => [
    {
      key: "name", header: "Nama", sortable: true, width: "22%",
      render: (l) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{l.name}</p>
          <p className="text-xs text-muted-foreground">{l.phone}</p>
        </div>
      ),
      exportValue: (l) => `${l.name} (${l.phone})`,
    },
    {
      key: "source", header: "Sumber", sortable: true,
      render: (l) => (
        <div>
          <p>{labelOf("lead_source", l.source)}</p>
          {l.campaign ? (
            <p className="text-xs text-muted-foreground">{l.campaign}</p>
          ) : null}
        </div>
      ),
      exportValue: (l) => labelOf("lead_source", l.source),
    },
    {
      key: "stage", header: "Tahap", sortable: true,
      render: (l) => <StatusPill status={l.stage} group="lead_stage" />,
    },
    {
      key: "score", header: "Skor", sortable: true, align: "right",
      render: (l) => <StatusPill status={l.score_band} label={`${l.score}`} />,
      exportValue: (l) => `${l.score} (${l.score_band})`,
    },
    {
      key: "assigned_to", header: "PIC", sortable: true, hidden: !isManager,
      render: (l) => <span className="text-sm">{l.assigned_to || "-"}</span>,
    },
    {
      key: "age_hours", header: "Umur (total · tahap)",
      render: (l) => <AgingCell ageHours={l.age_hours} stageAgeHours={l.stage_age_hours}
        slaHours={l.stage_sla_hours} state={l.sla_state} />,
      exportValue: (l) => `${Math.round(l.age_hours || 0)}j / ${Math.round(l.stage_age_hours || 0)}j`,
    },
    {
      key: "doc_progress", header: "Dokumen",
      render: (l) => {
        const p = l.doc_progress || {};
        if (!p.required) return <span className="text-xs text-muted-foreground">—</span>;
        const done = p.verified >= p.required;
        return (
          <span className={cn("text-xs tabular-nums", done ? "text-emerald-700" : "text-amber-700")}>
            {p.verified || 0}/{p.required} wajib {done ? "lengkap" : "belum"}
          </span>
        );
      },
      exportValue: (l) => `${l.doc_progress?.verified || 0}/${l.doc_progress?.required || 0}`,
    },
    {
      key: "created_at", header: "Masuk", sortable: true,
      render: (l) => <span className="text-xs text-muted-foreground">{fromNow(l.created_at)}</span>,
    },
  ], [isManager, labelOf]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "stage", label: "Tahap", type: "multiselect", options: stageOptions },
      { key: "source", label: "Sumber", type: "multiselect", options: options("lead_source") },
      { key: "score_band", label: "Skor", type: "multiselect", options: options("score_band") },
      ...(isManager ? [{ key: "assigned_to", label: "PIC", type: "multiselect", options: owners }]
        : []),
      slaFilter(options("sla_state")),
      { key: "created", label: "Tanggal masuk", type: "daterange",
        fromKey: "created_from", toKey: "created_to" },
    ]} />
  );

  const bulkActions = [
    ...(isManager ? [{
      key: "assign", label: "Tugaskan ulang…", testId: LEADS.bulkAssign,
      onRun: (rows, clear) => setAssignFor({ rows, clear }),
    }] : []),
    {
      key: "export", label: "Ekspor terpilih", testId: LEADS.bulkExport,
      onRun: (rows) => {
        downloadCsv(columns, rows, "lead-terpilih");
        toast.success(`${rows.length} baris diekspor ke CSV.`);
      },
    },
  ];

  return (
    <div data-testid={LEADS.page} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Pipeline Lead</h1>
          <p className="page-desc">
            Semua lead dengan umur, tahap, dan kelengkapan dokumennya — urutkan yang paling
            perlu dikerjakan.
          </p>
        </div>
        <div className="flex gap-2">
          {can("leads", "view_all") ? (
            <Button data-testid={P94.leadsCaptureBtn} variant="outline" size="sm"
              onClick={() => navigate("/wa-capture")}>
              <MessageSquarePlus className="mr-1.5 h-4 w-4" /> Capture dari WA
            </Button>
          ) : null}
          <Button data-testid={LEADS.simulateBtn} variant="outline" size="sm"
            onClick={() => setSimOpen(true)}>
            <Zap className="mr-1.5 h-4 w-4" /> Simulasi Lead Masuk
          </Button>
          <Button data-testid={LEADS.addBtn} size="sm" onClick={() => setAddOpen(true)}>
            <UserPlus className="mr-1.5 h-4 w-4" /> Tambah Lead
          </Button>
        </div>
      </div>

      {/* Fase 92 — kartu KPI pipeline: klik → popup daftar lead → buka profil */}
      <LeadKpiStrip refreshKey={data?.total} />

      {/* Pipeline strip = filter tahap sekali klik (angka = jumlah dalam cakupan Anda) */}
      <div data-testid={LEADS.pipeline} className="flex flex-wrap gap-2">
        <button onClick={() => setQuery({ stage: [] })}
          className={cn("rounded-lg border px-3 py-1.5 text-sm transition-colors",
            !(query.stage || []).length ? "border-primary bg-primary/10 text-primary"
              : "bg-card hover:bg-secondary")}>
          Semua <span className="ml-1 tabular-nums text-xs text-muted-foreground">
            {data?.total ?? 0}
          </span>
        </button>
        {stageOptions.map((s) => (
          <button key={s.value} onClick={() => toggleStage(s.value)}
            data-testid={`${LEADS.pipeline}-${s.value}`}
            className={cn("rounded-lg border px-3 py-1.5 text-sm transition-colors",
              (query.stage || []).includes(s.value)
                ? "border-primary bg-primary/10 text-primary" : "bg-card hover:bg-secondary")}>
            {s.label}
            <span className="ml-1.5 tabular-nums text-xs text-muted-foreground">{s.hint}</span>
          </button>
        ))}
      </div>

      <DataTable testId={LEADS.table} testIds={{ row: LEADS.row, search: LEADS.searchInput,
        pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} bulkActions={bulkActions} label="lead"
        searchPlaceholder="Cari nama / telepon / email / kampanye…"
        exportName="lead" onRefresh={load}
        onRowClick={(l) => navigate(`/leads/${l.id}`)}
        emptyTitle={activeCount || query.q ? "Tidak ada lead yang cocok"
          : "Belum ada lead"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Tambah lead manual, atau klik “Simulasi Lead Masuk” untuk menguji alur capture."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : "Simulasi Lead Masuk"}
        emptyAction={() => (activeCount || query.q ? reset() : setSimOpen(true))} />

      <AddLeadDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <SimulateLeadDialog open={simOpen} onOpenChange={setSimOpen} onDone={load} />
      <AssignLeadsDialog open={!!assignFor} onOpenChange={(v) => !v && setAssignFor(null)}
        rows={assignFor?.rows || []} owners={owners}
        onDone={() => { assignFor?.clear?.(); setAssignFor(null); load(); }} />
    </div>
  );
}
