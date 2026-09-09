import React from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DocTemplatesPanel from "@/components/master/DocTemplatesPanel";
import QcTemplatesPanel from "@/components/master/QcTemplatesPanel";
import DataHealthPanel from "@/components/master/DataHealthPanel";
import ReferencePanel from "@/components/master/ReferencePanel";
import BuildPolicyPanel from "@/components/master/BuildPolicyPanel";
import { MASTER } from "@/constants/testIds";
import EditGate from "@/components/patterns/EditGate";
import { Database } from "lucide-react";

/**
 * Master Data — template dokumen & QC yang sebelumnya TERKUNCI di script seed
 * (tidak ada endpoint tulis, jadi tidak bisa ditambah/diubah dari aplikasi),
 * plus panel Kesehatan Data untuk memantau integritas (field kopi basi & nilai enum liar).
 */
export default function MasterDataPage() {
  return (
    <div data-testid={MASTER.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Database className="h-5 w-5 text-primary" />
        <h1 className="page-title">Master Data & Integritas</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Kelola template dokumen legal dan checklist QC, serta pantau konsistensi data
        (nilai referensi & sinkronisasi nama antar modul).
      </p>

      <Tabs defaultValue="doc">
        <TabsList className="flex h-auto flex-wrap justify-start">
          <TabsTrigger data-testid={MASTER.tabDocTemplates} value="doc">Template Dokumen</TabsTrigger>
          <TabsTrigger data-testid={MASTER.tabQcTemplates} value="qc">Template QC</TabsTrigger>
          <TabsTrigger data-testid={MASTER.tabBuildPolicy} value="policy">Kebijakan Bukti Kerja</TabsTrigger>
          <TabsTrigger data-testid={MASTER.tabHealth} value="health">Kesehatan Data</TabsTrigger>
          <TabsTrigger data-testid={MASTER.tabReference} value="reference">Kamus Data (SSOT)</TabsTrigger>
        </TabsList>
        <TabsContent value="doc" className="mt-4"><EditGate resource="documents"><DocTemplatesPanel /></EditGate></TabsContent>
        <TabsContent value="qc" className="mt-4"><EditGate resource="construction"><QcTemplatesPanel /></EditGate></TabsContent>
        <TabsContent value="policy" className="mt-4"><EditGate resource="settings"><BuildPolicyPanel /></EditGate></TabsContent>
        <TabsContent value="health" className="mt-4"><DataHealthPanel /></TabsContent>
        <TabsContent value="reference" className="mt-4"><ReferencePanel /></TabsContent>
      </Tabs>
    </div>
  );
}
