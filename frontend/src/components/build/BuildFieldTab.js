import React, { useState } from "react";
import { HardHat } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import ProjectSelect from "@/components/construction/ProjectSelect";
import ForemanBoard from "@/components/construction/ForemanBoard";
import BuildQueuePanel from "@/components/construction/BuildQueuePanel";
import SiteDiaryPanel from "@/components/field/SiteDiaryPanel";
import PunchListPanel from "@/components/field/PunchListPanel";
import OfflineQueuePanel from "@/components/construction/OfflineQueuePanel";
import LaborAttendancePanel from "@/components/labor/LaborAttendancePanel";
import LaborWorkersPanel from "@/components/labor/LaborWorkersPanel";
import LaborPayrollPanel from "@/components/labor/LaborPayrollPanel";
import { CONSTRUCTION, LABOR } from "@/constants/testIds";

/**
 * Tab **Lapangan** pada hub Pembangunan (dok 29 §1).
 *
 * Menyatukan apa yang dikerjakan orang di lokasi: papan mandor (kerja hari ini), antrean
 * kerja lintas unit, buku harian, dan punch list — sebelumnya tersebar di dua menu
 * (“Progres &amp; Mutu” dan “Buku Harian &amp; Punch”) sehingga pelaksana harus pindah layar
 * untuk melaporkan satu hari kerja yang sama.
 */
export default function BuildFieldTab() {
  const [projectId, setProjectId] = useState(null);
  const [refresh, setRefresh] = useState(0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Kerja hari ini, antrean verifikasi, buku harian, dan temuan lapangan.
        </p>
        <ProjectSelect value={projectId} onChange={setProjectId}
          testId={CONSTRUCTION.projectSelect} />
      </div>
      {!projectId ? (
        <EmptyState icon={HardHat} title="Pilih proyek"
          description="Pilih proyek untuk melihat papan mandor, antrean kerja, buku harian, dan punch list." />
      ) : (
        <div className="space-y-6">
          <OfflineQueuePanel />
          <ForemanBoard projectId={projectId} />
          <BuildQueuePanel projectId={projectId} />
          <SiteDiaryPanel projectId={projectId} />
          <PunchListPanel projectId={projectId} />
          {/* Fase 47D — absensi & upah harian: janji dok 29 §1 ("absensi mandor") yang
              sebelumnya hanya berupa ANGKA workforce di buku harian. Diletakkan di tab
              Lapangan karena satu hari kerja dilaporkan di satu layar. */}
          <div data-testid={LABOR.section} className="space-y-6 border-t pt-6">
            <LaborAttendancePanel projectId={projectId} onChanged={() => setRefresh((n) => n + 1)} />
            <LaborPayrollPanel key={refresh} projectId={projectId} mode="field" />
            <LaborWorkersPanel projectId={projectId}
              onChanged={() => setRefresh((n) => n + 1)} />
          </div>
        </div>
      )}
    </div>
  );
}
