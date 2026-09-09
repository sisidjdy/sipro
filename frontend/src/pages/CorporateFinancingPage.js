import React from "react";
import { Banknote } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import LoansPanel from "@/components/loans/LoansPanel";
import LoanPaymentsPanel from "@/components/loans/LoanPaymentsPanel";
import { LOANS } from "@/constants/testIds";

/**
 * Pembiayaan Korporat (Fase 27) — kredit bank / leasing perusahaan.
 * Berbeda dari KPR pembeli (halaman Customer & KPR): ini UTANG PERUSAHAAN,
 * dibukukan di akun 2-2100 dengan bunga ke 6-1600.
 */
export default function CorporateFinancingPage() {
  return (
    <div data-testid={LOANS.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Banknote className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">Pembiayaan Korporat</h1>
          <p className="text-xs text-muted-foreground">
            Fasilitas kredit bank/leasing perusahaan · akun 2-2100 Utang Bank/Leasing,
            bunga & provisi ke 6-1600.
          </p>
        </div>
      </div>

      <Tabs defaultValue="facilities">
        <TabsList>
          <TabsTrigger data-testid={LOANS.tabFacilities} value="facilities">
            Fasilitas & Angsuran
          </TabsTrigger>
          <TabsTrigger data-testid={LOANS.tabPayments} value="payments">
            Riwayat Pembayaran
          </TabsTrigger>
        </TabsList>
        <TabsContent value="facilities" className="mt-4"><LoansPanel /></TabsContent>
        <TabsContent value="payments" className="mt-4"><LoanPaymentsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
