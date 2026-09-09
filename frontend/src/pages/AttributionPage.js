import React from "react";
import { PlugZap, Repeat, Target } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import EmptyState from "@/components/patterns/EmptyState";
import AttributionTab from "@/components/ads/AttributionTab";
import CapiEventsTab from "@/components/ads/CapiEventsTab";
import IntegrationHealthTab from "@/components/ads/IntegrationHealthTab";
import { useAuth } from "@/context/AuthContext";
import { ADS } from "@/constants/testIds";

/**
 * AttributionPage (`/attribution`) — hub **Atribusi &amp; CAPI** (Fase 43).
 *
 * Sebelumnya atribusi hanya berupa satu tab kecil di dalam “Automasi &amp; Channel” yang
 * mengelompokkan lead per sumber tanpa biaya sama sekali (“CPL tidak tersedia di mode
 * simulasi”). Tab itu DIHAPUS — satu urusan satu pintu, seperti yang dilakukan pada urusan
 * fee di Fase 42 — dan digantikan halaman ini: funnel bertingkat (kampanye → adset → iklan →
 * creative), campuran kanal (iklan berbayar vs mitra vs organik), audit event konversi yang
 * dikirim balik ke platform, dan kesiapan kredensial tiap integrasi.
 */
export default function AttributionPage() {
  const { can } = useAuth();
  const canView = can("ads", "view");

  return (
    <div data-testid={ADS.attrPage} className="space-y-4">
      <div>
        <h1 className="page-title">Atribusi &amp; CAPI</h1>
        <p className="page-desc">
          Dari mana lead benar-benar datang, dan apa yang sudah kita kirim balik ke platform
          iklan supaya optimasinya membaik. Semua angka lead di sini berasal dari pipeline
          yang sama dengan halaman Lead — tidak ada perhitungan kedua.
        </p>
      </div>
      {canView ? (
        <TabPage paramKey="hub" testId={ADS.hubTab} tabs={[
          { key: "funnel", label: "Funnel Atribusi", icon: Target, content: <AttributionTab /> },
          { key: "capi", label: "Event CAPI", icon: Repeat, content: <CapiEventsTab /> },
          { key: "integrasi", label: "Status Integrasi", icon: PlugZap,
            content: <IntegrationHealthTab /> },
        ]} />
      ) : (
        <EmptyState icon={Target} title="Anda tidak punya akses ke data atribusi"
          description="Peran Anda tidak diberi izin melihat atribusi lead maupun event konversi.
            Hubungi admin bila memang perlu." />
      )}
    </div>
  );
}
