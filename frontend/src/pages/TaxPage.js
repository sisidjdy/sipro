import React from "react";
import { Landmark } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import TaxSummaryPanel from "@/components/tax/TaxSummaryPanel";
import FakturPanel from "@/components/tax/FakturPanel";
import TaxRecordsPanel from "@/components/tax/TaxRecordsPanel";
import FakturExportPanel from "@/components/tax/FakturExportPanel";
import WithholdingPanel from "@/components/tax/WithholdingPanel";
import VatReturnPanel from "@/components/tax/VatReturnPanel";
import { AccessDenied } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import useTabParam from "@/hooks/useTabParam";
import { TAX, P49 } from "@/constants/testIds";

// Satu route (/tax) dengan Tabs internal; tiap panel memuat datanya sendiri
// (loading/empty/error) agar file tetap ramping dan lulus guardrails. Tab aktif ikut URL
// supaya tautan dari layar lain (mis. "lengkapi NPWP dulu") mendarat di tab yang benar.
//
// Fase 49 (perbaikan UX RBAC): peran tanpa izin `tax:view` — mis. sales — dulu tetap
// melihat SELURUH deretan tab, lalu tiap panel memuntahkan pesan teknis backend
// ("tidak memiliki izin 'view' pada 'tax'"). Itu membocorkan nama izin internal dan
// membuat pengguna mengira sistemnya rusak. Sekarang halaman ini menjawab sekali, dengan
// bahasa manusia, dan tidak menampilkan tab yang memang tidak bisa dibuka.
export default function TaxPage() {
  const [tab, setTab] = useTabParam("summary");
  const { can, user, permsKnown } = useAuth();
  // `permsKnown` wajib ikut: sebelum perbaikan Fase 53, profil sesi hasil `/auth/login`
  // tidak membawa `permissions`, sehingga halaman ini memasang kartu AKSES DITOLAK kepada
  // pemakai yang izinnya justru `*` (super admin). "Belum diketahui" ≠ "tidak boleh".
  const denied = !!user && permsKnown && !can("tax", "view");

  if (denied) {
    return (
      <div data-testid={TAX.page} className="space-y-5">
        <div className="flex items-center gap-2">
          <Landmark className="h-5 w-5 text-primary" />
          <h1 className="page-title">Perpajakan &amp; Kepatuhan</h1>
        </div>
        <AccessDenied testId={TAX.denied}
          title="Perpajakan &amp; Kepatuhan hanya untuk tim Keuangan"
          description={"Halaman ini memuat faktur pajak keluaran, bukti potong PPh, dan rekap SPT Masa PPN "
            + "\u2014 dibuka untuk Keuangan, Manajer Keuangan, Direksi, dan Super Admin."}
          askWho="Bila Anda memang perlu melihat data pajak, mintakan hak akses ke admin sistem." />
      </div>
    );
  }

  return (
    <div data-testid={TAX.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Landmark className="h-5 w-5 text-primary" />
        <h1 className="page-title">Perpajakan &amp; Kepatuhan</h1>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={TAX.tabSummary} value="summary">Ringkasan &amp; SPT PPN</TabsTrigger>
          <TabsTrigger data-testid={TAX.tabFaktur} value="faktur">Faktur Pajak</TabsTrigger>
          <TabsTrigger data-testid={P49.fakturExportTab} value="faktur-export">e-Faktur &amp; Ekspor</TabsTrigger>
          <TabsTrigger data-testid={P49.bupotTab} value="bupot">Bukti Potong (e-Bupot)</TabsTrigger>
          <TabsTrigger data-testid={P49.vatTab} value="vat">Rekap SPT Masa PPN</TabsTrigger>
          <TabsTrigger data-testid={TAX.tabRecords} value="records">Catatan Pajak</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="mt-4"><TaxSummaryPanel /></TabsContent>
        <TabsContent value="faktur" className="mt-4"><FakturPanel /></TabsContent>
        <TabsContent value="faktur-export" className="mt-4"><FakturExportPanel /></TabsContent>
        <TabsContent value="bupot" className="mt-4"><WithholdingPanel /></TabsContent>
        <TabsContent value="vat" className="mt-4"><VatReturnPanel /></TabsContent>
        <TabsContent value="records" className="mt-4"><TaxRecordsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
