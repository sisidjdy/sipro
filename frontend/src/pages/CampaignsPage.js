import React from "react";
import { BarChart3, FileSpreadsheet, History, Megaphone, Wallet } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import EmptyState from "@/components/patterns/EmptyState";
import CampaignsTab from "@/components/ads/CampaignsTab";
import SpendTab from "@/components/ads/SpendTab";
import PerformanceTab from "@/components/ads/PerformanceTab";
import ImportHistoryTab from "@/components/ads/ImportHistoryTab";
import { useAuth } from "@/context/AuthContext";
import { ADS } from "@/constants/testIds";

/**
 * CampaignsPage (`/campaigns`) — hub **Kampanye &amp; Biaya Iklan** (Fase 43).
 *
 * Menu ini sebelumnya berstatus “Segera Hadir”: biaya iklan tidak pernah masuk sistem, jadi
 * CPL/CAC/ROAS mustahil dihitung dan setiap keputusan anggaran iklan diambil dari ingatan
 * atau spreadsheet pribadi. Sekarang: master kampanye → biaya harian (manual atau impor CSV
 * yang idempoten) → kinerja dengan metrik yang JUJUR (tidak pernah menampilkan 0 untuk biaya
 * yang belum diinput) → riwayat impor yang bisa diaudit.
 *
 * Penanda tab memakai `?hub=` (bukan `?tab=`) agar tidak bertabrakan dengan tab di dalam
 * halaman anak.
 */
export default function CampaignsPage() {
  const { can } = useAuth();
  const canView = can("ads", "view");

  return (
    <div data-testid={ADS.page} className="space-y-4">
      <div>
        <h1 className="page-title">
          Kampanye &amp; Biaya Iklan
        </h1>
        <p className="page-desc">
          Master kampanye per platform, biaya iklan harian (input manual atau impor CSV
          idempoten), dan kinerja per kampanye: CPL, biaya per lead terkualifikasi, CAC, ROAS.
          Setiap angka biaya membawa <strong>label asal datanya</strong>; bila biaya sebuah
          kampanye belum diinput, metrik biayanya dinyatakan <em>belum lengkap</em> — bukan nol.
        </p>
      </div>
      {canView ? (
        <TabPage paramKey="hub" testId={ADS.hubTab} tabs={[
          { key: "kampanye", label: "Kampanye", icon: Megaphone, content: <CampaignsTab /> },
          { key: "biaya", label: "Biaya Iklan", icon: Wallet, content: <SpendTab /> },
          { key: "kinerja", label: "Kinerja", icon: BarChart3, content: <PerformanceTab /> },
          { key: "impor", label: "Riwayat Impor", icon: History,
            content: <ImportHistoryTab /> },
        ]} />
      ) : (
        <EmptyState icon={FileSpreadsheet} title="Anda tidak punya akses ke data biaya iklan"
          description="Peran Anda tidak diberi izin melihat kampanye maupun biaya iklan.
            Hubungi admin bila memang perlu — jangan sampai halaman ini menampilkan tabel
            kosong yang seolah-olah datanya tidak ada." />
      )}
    </div>
  );
}
