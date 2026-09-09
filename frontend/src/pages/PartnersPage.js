import React from "react";
import { Banknote, Handshake, ListChecks, Scale, TrendingUp } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import EmptyState from "@/components/patterns/EmptyState";
import PartnersListTab from "@/components/partners/PartnersListTab";
import FeeRulesTab from "@/components/partners/FeeRulesTab";
import PartnerAnalyticsTab from "@/components/partners/PartnerAnalyticsTab";
import ConflictsTab from "@/components/partners/ConflictsTab";
import FeesPanel from "@/components/marketingFee/FeesPanel";
import { useAuth } from "@/context/AuthContext";
import { PARTNERS } from "@/constants/testIds";

/**
 * PartnersPage (`/partners`) — hub **Mitra &amp; Fee** (Fase 42).
 *
 * Menu ini sebelumnya berstatus “Segera Hadir” (terkunci, tanpa route) dan yang ada hanyalah
 * menu “Marketing Fee” berisi master agen + pengajuan fee manual. Sesuai peta navigasi
 * (`docs/v2/40_PETA_NAV_V2.md`), Marketing Fee kini menjadi tab **Tagihan Fee** di dalam hub
 * ini — rutenya (`/marketing-fee`) SENGAJA tetap hidup sebagai alias supaya notifikasi,
 * tugas, dan bookmark lama tidak rusak.
 *
 * Penanda tab memakai `?hub=` (bukan `?tab=`) agar tidak bertabrakan dengan tab di dalam
 * halaman anak.
 */
export default function PartnersPage() {
  const { can } = useAuth();
  // TAB hanya ditampilkan bila datanya boleh DIBACA peran ini. Dua resource berbeda bertemu
  // di hub ini: isi tab "Tagihan Fee" datang dari `marketing_fee`, sisanya dari `partners`.
  // Cacat nyata yang ditutup: Manajer Proyek punya `partners:view_all` tetapi TIDAK punya izin
  // `marketing_fee` sama sekali, jadi tab "Tagihan Fee" tampil lalu isinya dijawab 403
  // ("Akses ditolak") — TAB MATI, persis cacat yang sama dengan tombol mati. Sejak alias lama
  // `/marketing-fee` mengalihkan ke `?hub=tagihan`, bookmark Manajer Proyek mendarat tepat di
  // tab itu. `TabPage` memilih tab pertama yang tersedia bila kunci `?hub=` tidak ada di
  // daftar, jadi pemakai mendarat di tab yang benar-benar bisa ia buka.
  const seePartners = can("partners", "view");
  const seeFees = can("marketing_fee", "view");
  const tabs = [
    seePartners && { key: "mitra", label: "Master Mitra", icon: Handshake,
                     content: <PartnersListTab /> },
    seePartners && { key: "aturan", label: "Aturan Fee", icon: ListChecks,
                     content: <FeeRulesTab /> },
    seeFees && { key: "tagihan", label: "Tagihan Fee", icon: Banknote, content: <FeesPanel /> },
    seePartners && { key: "sengketa", label: "Sengketa Atribusi", icon: Scale,
                     content: <ConflictsTab /> },
    seePartners && { key: "analitik", label: "Analitik Mitra", icon: TrendingUp,
                     content: <PartnerAnalyticsTab /> },
  ].filter(Boolean);

  return (
    <div data-testid={PARTNERS.page} className="space-y-4">
      <div>
        <h1 className="page-title">Mitra &amp; Fee</h1>
        <p className="page-desc">
          Mitra eksternal (agen, broker, aggregator, referral): kontrak, aturan fee, tagihan
          fee, sengketa atribusi lead, dan kinerja tiap mitra. Utang fee dibukukan di akun
          2-1500, bebannya 6-1200, PPh dipotong ke 2-1300.
        </p>
      </div>
      {tabs.length ? (
        <TabPage paramKey="hub" testId={PARTNERS.hubTab} tabs={tabs} />
      ) : (
        <EmptyState icon={Handshake} title="Anda tidak punya akses ke data mitra & fee"
          description="Peran Anda tidak diberi izin melihat mitra maupun tagihan fee. Hubungi
            admin bila memang perlu — jangan sampai halaman ini menampilkan tabel kosong yang
            seolah-olah datanya tidak ada." />
      )}
    </div>
  );
}
