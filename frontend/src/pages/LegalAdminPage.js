import React from "react";
import { useSearchParams } from "react-router-dom";
import { Scale } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import LegalSettingsForm from "@/components/legal/LegalSettingsForm";
import DeletionRequestsTable from "@/components/legal/DeletionRequestsTable";
import LegalUrlsCard from "@/components/legal/LegalUrlsCard";
import { useAuth } from "@/context/AuthContext";
import { LEGAL } from "@/constants/testIds";

/** Legal & Privasi — identitas + teks halaman legal publik, antrean penghapusan data, URL untuk Meta. */
export default function LegalAdminPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "settings";
  const setTab = (v) => { const n = new URLSearchParams(params); n.set("tab", v); setParams(n, { replace: true }); };
  return (
    <div data-testid={LEGAL.adminPage} className="space-y-5">
      <div className="flex items-center gap-2">
        <Scale className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">Legal &amp; Privasi</h1>
          <p className="page-desc">Kebijakan Privasi, Syarat &amp; Ketentuan, dan Penghapusan Data (ID/EN) yang tayang publik — wajib untuk UU PDP dan Meta App Review WhatsApp.</p>
        </div>
      </div>
      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={LEGAL.tabSettings} value="settings">Identitas &amp; Teks</TabsTrigger>
          <TabsTrigger data-testid={LEGAL.tabRequests} value="requests">Permintaan Penghapusan</TabsTrigger>
          <TabsTrigger data-testid={LEGAL.tabUrls} value="urls">URL untuk Meta</TabsTrigger>
        </TabsList>
        <TabsContent value="settings"><LegalSettingsForm editable={can("legal", "manage")} /></TabsContent>
        <TabsContent value="requests"><DeletionRequestsTable editable={can("legal", "update")} /></TabsContent>
        <TabsContent value="urls"><LegalUrlsCard /></TabsContent>
      </Tabs>
    </div>
  );
}
