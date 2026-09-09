import React, { useState } from "react";
import { ClipboardList } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import EmptyState from "@/components/patterns/EmptyState";
import ProjectSelect from "@/components/construction/ProjectSelect";
import SiteDiaryPanel from "@/components/field/SiteDiaryPanel";
import PunchListPanel from "@/components/field/PunchListPanel";
import OfflineQueuePanel from "@/components/construction/OfflineQueuePanel";
import { FIELD } from "@/constants/testIds";

export default function FieldPage() {
  const [projectId, setProjectId] = useState(null);
  return (
    <div data-testid={FIELD.page} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-5 w-5 text-primary" />
          <h1 className="page-title">Buku Harian & Punch List</h1>
        </div>
        <ProjectSelect value={projectId} onChange={setProjectId} testId={FIELD.projectSelect} />
      </div>

      {!projectId ? (
        <EmptyState icon={ClipboardList} title="Pilih proyek"
          description="Pilih proyek untuk melihat buku harian lapangan & daftar punch list." />
      ) : (
        <Tabs defaultValue="diary">
          <TabsList>
            <TabsTrigger data-testid={FIELD.tabDiary} value="diary">Buku Harian</TabsTrigger>
            <TabsTrigger data-testid={FIELD.tabPunch} value="punch">Punch List</TabsTrigger>
          </TabsList>
          {/* Fase 50B: antrean perangkat untuk buku harian & punch list tampil di halaman
              tempat keduanya dikerjakan — bukan hanya di Papan Mandor. Pekerjaan yang
              belum sampai server harus TERLIHAT di tempat pemakai menuliskannya. */}
          <div className="mt-3">
            <OfflineQueuePanel kinds={["field_diary", "punch_create", "punch_status"]} />
          </div>
          <TabsContent value="diary" className="mt-4">
            <SiteDiaryPanel projectId={projectId} />
          </TabsContent>
          <TabsContent value="punch" className="mt-4">
            <PunchListPanel projectId={projectId} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
