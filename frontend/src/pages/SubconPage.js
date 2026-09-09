import React from "react";
import { Wrench } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useSearchParams } from "react-router-dom";

import SubcontractorsPanel from "@/components/subcon/SubcontractorsPanel";
import SPKPanel from "@/components/subcon/SPKPanel";
import ClaimsPanel from "@/components/subcon/ClaimsPanel";
import AdvancesPanel from "@/components/subcon/AdvancesPanel";
import RetentionsPanel from "@/components/subcon/RetentionsPanel";
import EvaluationsPanel from "@/components/vendors/EvaluationsPanel";
import { PROCUREMENT, CLAIMS, SUBFIN } from "@/constants/testIds";

const TABS = ["subs", "spk", "claims", "advances", "retentions", "evaluation"];

/**
 * SubconPage (`/subcon`) — seluruh siklus uang subkon dalam satu pintu.
 *
 * Fase 48C menambah tiga tab yang sebelumnya tidak ada layarnya: **Uang Muka & Potongan**
 * (uang muka berjurnal + angsuran/denda yang memotong termin), **Retensi** (daftar + gerbang
 * pencairan), dan **Evaluasi** (rapor subkon dari SPK/termin/denda nyata).
 */
export default function SubconPage() {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("tab");
  const active = TABS.includes(wanted) ? wanted : "subs";
  const onTab = (value) => {
    const next = new URLSearchParams();
    next.set("tab", value);
    setParams(next, { replace: false });
  };

  return (
    <div data-testid={PROCUREMENT.subconPage} className="space-y-5">
      <div className="flex items-center gap-2">
        <Wrench className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">Subkontraktor &amp; SPK</h1>
          <p className="page-desc">
            Kontrak, termin berbasis opname, uang muka &amp; potongan, retensi bergerbang, dan
            rapor kinerja — uang subkon mengalir hanya mengikuti bukti.
          </p>
        </div>
      </div>
      <Tabs value={active} onValueChange={onTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={PROCUREMENT.subTab} value="subs">Subkontraktor</TabsTrigger>
          <TabsTrigger data-testid={PROCUREMENT.spkTab} value="spk">SPK (Perintah Kerja)</TabsTrigger>
          <TabsTrigger data-testid={CLAIMS.tab} value="claims">Progress &amp; Termin</TabsTrigger>
          <TabsTrigger data-testid={SUBFIN.advanceTab} value="advances">Uang Muka &amp; Potongan</TabsTrigger>
          <TabsTrigger data-testid={SUBFIN.retentionTab} value="retentions">Retensi</TabsTrigger>
          <TabsTrigger data-testid={SUBFIN.evalTab} value="evaluation">Evaluasi</TabsTrigger>
        </TabsList>
        <TabsContent value="subs" className="mt-4"><SubcontractorsPanel /></TabsContent>
        <TabsContent value="spk" className="mt-4"><SPKPanel /></TabsContent>
        <TabsContent value="claims" className="mt-4"><ClaimsPanel /></TabsContent>
        <TabsContent value="advances" className="mt-4"><AdvancesPanel /></TabsContent>
        <TabsContent value="retentions" className="mt-4"><RetentionsPanel /></TabsContent>
        <TabsContent value="evaluation" className="mt-4">
          <EvaluationsPanel endpoint="/subcon/evaluations" testId={SUBFIN.evalPanel}
            emptyTitle="Belum ada subkontraktor yang bisa dinilai"
            emptyDescription={"Rapor subkon dihitung dari SPK (ketepatan waktu), opname "
              + "(mutu), dan denda nyata. Belum ada SPK yang punya bukti untuk dinilai."} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
