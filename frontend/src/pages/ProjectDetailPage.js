import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import useTabParam from "@/hooks/useTabParam";
import EntityHeader from "@/components/patterns/EntityHeader";
import MetricCard from "@/components/patterns/MetricCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import { P93 } from "@/constants/testIds";

/** Kartu ringkasan proyek yang bisa diklik → popup daftar unit (Fase 93). */
function Kpi({ id, onOpen, label, ...card }) {
  return (
    <button type="button" data-testid={`${P93.projectKpi}-${id}`} onClick={() => onOpen(id, label)}
      className="group rounded-xl text-left outline-none transition-transform focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99]">
      <MetricCard label={label} {...card} className="h-full ring-1 ring-transparent group-hover:ring-primary/50" />
    </button>
  );
}
import StructureTab from "@/components/projects/StructureTab";
import TargetSummaryCard from "@/components/budget/TargetSummaryCard";
import PermitCoveragePanel from "@/components/permits/PermitCoveragePanel";
import UnitsTab from "@/components/projects/UnitsTab";
import CreateTaskDialog from "@/components/work/CreateTaskDialog";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import DeleteEntityButton from "@/components/patterns/DeleteEntityButton";
import { formatIDR } from "@/utils/formatters";
import { MASTERPLAN } from "@/constants/testIds";

/**
 * Halaman kanonik PROYEK (Fase 39) — tempat mengelola hierarki
 * proyek → cluster → blok → unit yang sebelumnya tidak ada sama sekali (audit CR-05).
 */
export default function ProjectDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useTabParam("structure");
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("projects", "update");
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [drill, setDrill] = useState(null);
  const openDrill = (sub, label) => setDrill({ key: `project:${sub}`, label, params: { project_id: id } });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get(`/masterplan/projects/${id}/tree`);
      setTree(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat struktur proyek.");
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const project = tree?.project || {};
  const stats = project.unit_stats || {};
  const soldLike = (stats.booked || 0) + (stats.sold || 0) + (stats.handed_over || 0);

  return (
    <div data-testid={MASTERPLAN.projectPage} className="space-y-5">
      <EntityHeader
        kicker="Proyek"
        title={project.name || "Proyek"}
        subtitle={project.location}
        backLabel="Daftar proyek"
        chips={[
          { label: "Kode", value: project.code },
          { label: "Cluster", value: tree?.totals?.clusters || 0 },
          { label: "Blok", value: tree?.totals?.blocks || 0 },
          { label: "Unit", value: tree?.totals?.units || 0 },
          { label: "Progres konstruksi (fase berbobot)", value: `${project.construction_progress || 0}%` },
          { label: "Rata-rata progres unit", value: `${project.units_progress || 0}% · ${project.units_scheduled || 0}/${project.units_total ?? tree?.totals?.units ?? 0} unit terjadwal` },
        ]}
        actions={(
          <>
            {can("work_tasks", "create") ? (
              <CreateTaskDialog triggerLabel="Buat tugas" triggerVariant="outline"
                preset={{ type: "project", id,
                  label: `${project.name || id}${project.code ? ` (${project.code})` : ""}` }} />
            ) : null}
            {can("projects", "delete") ? (
              <DeleteEntityButton entity="Proyek" name={project.code} testId="project-delete"
                checkUrl={`/projects/${id}/delete-check`} deleteUrl={`/projects/${id}`}
                onDeleted={() => navigate("/projects")} />
            ) : null}
          </>
        )} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi id="available" label="Unit tersedia" value={stats.available || 0} tone="emerald" onOpen={openDrill} />
        <Kpi id="held" label="Dipegang / booking" value={(stats.reserved || 0) + (stats.booked || 0)}
          tone="amber" onOpen={openDrill} />
        <Kpi id="sold" label="Terjual (kumulatif)" value={soldLike} tone="primary" onOpen={openDrill}
          hint={`absorpsi ${stats.absorption_pct || 0}%`} />
        <Kpi id="value" label="Nilai unit" value={formatIDR(stats.value || 0)} tone="indigo" onOpen={openDrill} />
        <Kpi id="progress" label="Progres konstruksi (fase berbobot)" value={`${project.construction_progress || 0}%`} tone="sky"
          hint={`rata-rata unit ${project.units_progress || 0}% (${project.units_scheduled || 0}/${project.units_total ?? tree?.totals?.units ?? 0} terjadwal)`} onOpen={openDrill} />
      </div>
      <DrilldownDialog target={drill} onOpenChange={(o) => { if (!o) setDrill(null); }} />

      {/* Fase 45 — kartu target proyek. Diletakkan di sini karena pertanyaan pertama saat
          membuka satu proyek adalah "targetnya berapa dan sudah sejauh mana", sebelum
          melihat struktur cluster/blok. Tanpa target aktif kartu ini MENGAKU kosong. */}
      <TargetSummaryCard projectId={id} />

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList>
          <TabsTrigger data-testid={MASTERPLAN.tabStructure} value="structure">
            Struktur (Cluster → Blok)
          </TabsTrigger>
          <TabsTrigger data-testid={MASTERPLAN.tabUnits} value="units">Unit</TabsTrigger>
          <TabsTrigger data-testid="project-tab-permits" value="permits">
            Dokumen &amp; Perizinan
          </TabsTrigger>
        </TabsList>
        <TabsContent value="structure">
          <StructureTab tree={tree} projectId={id} onChanged={load} canManage={canManage} />
        </TabsContent>
        <TabsContent value="units">
          <UnitsTab projectId={id} clusters={tree?.clusters || []} />
        </TabsContent>
        {/* Fase 46 (dok 29 §5): perizinan bukan menu tersendiri lagi — ia menempel pada
            objeknya. Di tingkat proyek yang tampil adalah izin kawasan beserta kesehatan
            masa berlakunya; izin blok/unit tampil di Unit 360. */}
        <TabsContent value="permits">
          <PermitCoveragePanel projectId={id}
            title={`Perizinan tingkat proyek ${project.name || ""}`} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
