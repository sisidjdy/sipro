import React, { useCallback, useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState } from "@/components/patterns/StateViews";
import ProjectSelect from "@/components/construction/ProjectSelect";
import InspectionsPanel from "@/components/construction/InspectionsPanel";
import api from "@/services/apiClient";
import { CONSTRUCTION } from "@/constants/testIds";

/**
 * Tab **Mutu & Inspeksi** pada hub Pembangunan (dok 29 §1).
 *
 * Dulu QC hanya bisa dicapai sebagai sub-tab di dalam tab — tiga klik dari beranda dan
 * mudah tidak ditemukan. Inspeksi per UNIT tetap muncul di Unit 360 → tab Pembangunan;
 * yang di sini adalah inspeksi tingkat proyek/kawasan beserta seluruh daftarnya.
 */
export default function BuildQualityTab() {
  const [projectId, setProjectId] = useState(null);
  const [phases, setPhases] = useState([]);
  const [error, setError] = useState("");

  const loadPhases = useCallback(async () => {
    if (!projectId) return;
    setError("");
    try {
      const r = await api.get(`/construction/project/${projectId}/phases`);
      setPhases(r.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat pekerjaan kawasan proyek.");
    }
  }, [projectId]);

  useEffect(() => { loadPhases(); }, [loadPhases]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Inspeksi formal (QC) beserta hasil dan temuannya. Inspeksi milik satu rumah juga
          tampil di Unit 360 → tab Pembangunan.
        </p>
        <ProjectSelect value={projectId} onChange={setProjectId}
          testId={CONSTRUCTION.projectSelect} />
      </div>
      {!projectId ? (
        <EmptyState icon={ClipboardCheck} title="Pilih proyek"
          description="Pilih proyek untuk melihat inspeksi mutu dan temuannya." />
      ) : (
        <div className="space-y-3">
          {error ? <ErrorState message={error} onRetry={loadPhases} /> : null}
          {!phases.length ? (
            <p className="rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground">
              Belum ada pekerjaan kawasan pada proyek ini — inspeksi tetap bisa dibuat tanpa
              dikaitkan ke fase kawasan.
            </p>
          ) : null}
          <InspectionsPanel projectId={projectId} phases={phases} />
        </div>
      )}
    </div>
  );
}
