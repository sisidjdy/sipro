import React from "react";
import { FilePlus2, FileText, Stamp } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import DocumentsListTab from "@/components/documents/DocumentsListTab";
import DocumentIssueHub from "@/components/documents/DocumentIssueHub";
import PermitsPage from "@/pages/PermitsPage";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { DOCS } from "@/constants/testIds";

/**
 * DocumentsPage (`/documents`) — hub **Dokumen & Perizinan** (IA V2 §3).
 *
 * Menu “Perizinan & Dokumen” dilebur ke sini: daftar GLOBAL perizinan menjadi tab, sedangkan
 * perizinan per objek tetap muncul di Unit 360 & halaman Proyek. Rute `/permits` tetap hidup
 * (tautan lama & pintasan) — tidak ada fitur yang hilang, hanya pintu masuknya disatukan.
 *
 * Tab ditentukan oleh IZIN NYATA (`can()` dari `/auth/me`), bukan daftar peran yang ditulis
 * ulang di frontend: manajer proyek boleh melihat perizinan tetapi TIDAK punya izin dokumen
 * transaksi, jadi ia hanya melihat tab yang benar-benar bisa dibuka (bukan tab yang pasti
 * berakhir 403).
 */
export default function DocumentsPage() {
  const { can, permsKnown } = useAuth();
  const canDocs = can("documents", "view");
  const canPermits = can("permits", "view");

  const tabs = [
    ...(canDocs && can("contracts", "view") ? [{ key: "terbitkan", label: "Terbitkan Dokumen",
      icon: FilePlus2, content: <DocumentIssueHub /> }] : []),
    ...(canDocs ? [{ key: "dokumen", label: "Dokumen Transaksi", icon: FileText,
      content: <DocumentsListTab /> }] : []),
    ...(canPermits ? [{ key: "perizinan", label: "Perizinan", icon: Stamp,
      content: <PermitsPage /> }] : []),
  ];

  return (
    <div data-testid={DOCS.page} className="space-y-4">
      <div>
        <h1 className="page-title">
          Dokumen &amp; Perizinan
        </h1>
        <p className="page-desc">
          Dokumen transaksi (SPR/PPJB/AJB) dan daftar perizinan proyek/unit — sesuai hak akses
          Anda.
        </p>
      </div>
      {tabs.length ? <TabPage paramKey="hub" tabs={tabs} /> : permsKnown ? (
        <EmptyState icon={FileText} title="Tidak ada dokumen yang boleh Anda lihat"
          description="Akun Anda belum diberi izin `documents` maupun `permits`. Hubungi admin bila seharusnya punya akses." />
      ) : (
        // Izin belum diketahui ≠ tidak boleh. Sebelum perbaikan Fase 53, jawaban
        // `/auth/login` tidak membawa `permissions` sehingga halaman ini berkata "tidak ada
        // dokumen yang boleh Anda lihat" kepada SUPER ADMIN.
        <LoadingCards count={3} />
      )}
    </div>
  );
}
