import React, { useState } from "react";
import { FileStack } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import ProjectSelect from "@/components/construction/ProjectSelect";
import BuildTemplatePanel from "@/components/construction/BuildTemplatePanel";
import { CONSTRUCTION } from "@/constants/testIds";

/**
 * Tab **Template Jadwal** pada hub Pembangunan (dok 29 §1): master tahapan per tipe unit
 * (bobot, urutan, gerbang bukti, foto minimal). Bukan menu utama lagi — ini pekerjaan
 * setup, bukan pekerjaan harian.
 */
export default function BuildTemplatesTab() {
  const [projectId, setProjectId] = useState(null);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Tahapan pekerjaan per tipe unit: bobot, urutan, waktu tunggu, dan bukti wajib.
          Perubahan template hanya berlaku untuk jadwal yang dibuat SETELAHNYA.
        </p>
        <ProjectSelect value={projectId} onChange={setProjectId}
          testId={CONSTRUCTION.projectSelect} />
      </div>
      {!projectId ? (
        <EmptyState icon={FileStack} title="Pilih proyek"
          description="Pilih proyek untuk melihat template global maupun template khusus proyek tersebut." />
      ) : (
        <BuildTemplatePanel projectId={projectId} />
      )}
    </div>
  );
}
